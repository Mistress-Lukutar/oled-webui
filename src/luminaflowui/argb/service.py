"""
File:   service.py
Brief:  ARGB orchestration: scene-driven effect loop, OpenRGB output.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

import structlog

from luminaflowui.argb.devices import (
    DeviceLibrary,
    validate_with_library,
)
from luminaflowui.argb.engine import apply_brightness, render_layout
from luminaflowui.argb.schema import ArgbLayout
from luminaflowui.argb.settings import (
    ArgbSettings,
    resolve_argb_settings,
    save_argb_settings,
    settings_path,
)
from luminaflowui.exceptions import ArgbError, DeviceNotConnectedError
from luminaflowui.infrastructure.openrgb_transport import OpenRgbClient
from luminaflowui.scene.providers import DataSources
from luminaflowui.services.event_bus import EventBus
from luminaflowui.services.frame_builder import brightness_lut

if TYPE_CHECKING:
    from luminaflowui.config import Settings
    from luminaflowui.infrastructure.openrgb_process import OpenRgbProcessManager

logger = structlog.get_logger(__name__)

# Meter source polling interval in seconds.
_SAMPLE_INTERVAL: float = 1.0

# Minimum seconds between automatic OpenRGB recovery attempts.
_RECOVER_INTERVAL: float = 5.0


def _consume_future(future: Any) -> None:
    """Retrieve a cross-thread future's outcome to surface errors once.

    Args:
        future: Future returned by ``run_coroutine_threadsafe``.
    """
    error = future.exception()
    if error is not None:
        logger.warning("monitor_power_action_failed", error=str(error))


class ArgbService:
    """Single owner of the OpenRGB connection and the effect engine loop.

    Layouts are not persisted here: the applied layout comes from the
    active scene's ``argb`` section, and the scene file is the only
    storage. The engine is hardware-independent: :meth:`render_preview`
    renders any layout without a device, which is what the web editor
    previews through. While the engine runs, each tick also pushes
    changed zone buffers to OpenRGB (when connected) after
    gamma-corrected brightness scaling.
    """

    def __init__(
        self,
        settings: Settings,
        bus: EventBus,
        process_manager: OpenRgbProcessManager | None = None,
    ) -> None:
        self._settings = settings
        self._bus = bus
        self._proc = process_manager
        self._client = OpenRgbClient(settings.openrgb_host, settings.openrgb_port)
        self._lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()
        self._argb_settings: ArgbSettings = resolve_argb_settings(settings)
        self._settings_file = settings_path(settings)
        # True while the engine was stopped and zones blacked by the
        # Windows display-power hook, so the restore only undoes our own
        # blanking, not a user-initiated stop.
        self._display_blanked = False
        # The library is loaded first: scene layout sections reference
        # device definitions, and seeding must happen before validation.
        self._library = DeviceLibrary(settings.argb_dir / "devices")
        self._layout: ArgbLayout = ArgbLayout()
        self._run_task: asyncio.Task[None] | None = None
        self._run_layout: ArgbLayout | None = None
        self._run_counts: dict[str, int] = {}
        self._last_sent: dict[str, bytes] = {}
        self._frames_sent = 0
        self._last_poll = float("-inf")
        self._last_recover = float("-inf")
        self._sources = DataSources()
        self._samples: dict[str, float | str] = self._sources.snapshot()

    # ------------------------------------------------------------------
    # Layout access
    # ------------------------------------------------------------------

    @property
    def layout(self) -> ArgbLayout:
        """The last applied layout (runtime state; scenes are the storage)."""
        return self._layout

    def validate_layout(self, layout: ArgbLayout) -> dict[str, int]:
        """Check the layout against the device definition library.

        Args:
            layout: Layout to validate.

        Returns:
            Resolved LED counts per device instance id.

        Raises:
            ArgbError: If a definition is unknown, a chain overflows or a
                mask run leaves the device's LED range.
        """
        return validate_with_library(layout, self._library)

    # ------------------------------------------------------------------
    # Device definition library
    # ------------------------------------------------------------------

    @property
    def library(self) -> DeviceLibrary:
        """The device definition library."""
        return self._library

    def list_device_definitions(self) -> list[dict[str, Any]]:
        """Summaries of every installed definition plus layout usage."""
        used: dict[str, list[str]] = {}
        for device in self._layout.devices:
            used.setdefault(device.device, []).append(device.id)
        return [
            {
                "id": definition.id,
                "name": definition.name,
                "leds": definition.led_count,
                "used_by": used.get(definition.id, []),
                "definition": definition.model_dump(mode="json"),
            }
            for definition in self._library.list()
        ]

    def get_device_definition(self, device_id: str) -> dict[str, Any]:
        """Raw YAML text and parsed form of one definition.

        Raises:
            ArgbError: If the id is unknown.
        """
        definition = self._library.get(device_id)
        if definition is None:
            raise ArgbError(f"Unknown device definition: {device_id!r}")
        return {
            "yaml": self._library.source(device_id),
            "definition": definition.model_dump(mode="json"),
        }

    async def save_device_definition(
        self, yaml_text: str, expected_id: str | None = None
    ) -> dict[str, Any]:
        """Validate and store a definition, then re-check the layout.

        Args:
            yaml_text: Raw YAML source of the definition.
            expected_id: When given, the definition id must match it.

        Returns:
            The stored definition as a plain dict.

        Raises:
            ArgbError: On invalid YAML or id mismatch.
        """
        definition = self._library.save_yaml(yaml_text, expected_id)
        await self._after_library_change()
        return definition.model_dump(mode="json")

    async def delete_device_definition(self, device_id: str) -> None:
        """Remove a definition unless layout instances still reference it.

        Raises:
            ArgbError: If the definition is unknown or still in use.
        """
        used_by = [
            device.id for device in self._layout.devices if device.device == device_id
        ]
        if used_by:
            raise ArgbError(
                f"Device definition {device_id!r} is used by layout devices: "
                + ", ".join(used_by)
            )
        self._library.delete(device_id)
        await self._after_library_change()

    async def _after_library_change(self) -> None:
        """Re-validate the stored layout after a definition changed.

        A definition edit can change LED counts, so a running engine is
        restarted with fresh counts; if the layout no longer validates,
        the engine is stopped and the error surfaced on the bus.
        """
        try:
            counts = validate_with_library(self._layout, self._library)
        except ArgbError as exc:
            if self.is_running:
                await self.stop()
                await self._bus.publish("error", {"source": "argb", "error": str(exc)})
            await self._publish_status()
            return
        if self.is_running:
            await self._restart_engine(counts)
        await self._publish_status()

    # ------------------------------------------------------------------
    # OpenRGB connection
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when the OpenRGB SDK session is open."""
        return self._client.is_connected

    def require_connection(self) -> None:
        """Raise unless the OpenRGB SDK session is open.

        Raises:
            DeviceNotConnectedError: If OpenRGB is not connected.
        """
        if not self._client.is_connected:
            raise DeviceNotConnectedError("OpenRGB is not connected")

    async def connect(self) -> dict[str, Any]:
        """Open the OpenRGB SDK session and sync header zone sizes.

        When a process manager is configured, the OpenRGB application is
        spawned first if nothing serves the SDK port yet.

        Returns:
            Status snapshot after connection.
        """
        if self._proc is not None:
            await self._proc.ensure_running()
        async with self._lock:
            zones = await asyncio.to_thread(self._client.connect)
            await self._sync_header_sizes(zones)
        self._last_sent = {}
        await self._publish_status()
        return self.status()

    async def disconnect(self) -> dict[str, Any]:
        """Stop the engine and close the OpenRGB SDK session.

        Returns:
            Status snapshot after the disconnect.
        """
        await self.stop()
        async with self._lock:
            await asyncio.to_thread(self._client.disconnect)
        await self._publish_status()
        return self.status()

    async def _sync_header_sizes(self, zones: list[Any]) -> None:
        """Reconcile layout header sizes with discovered zone capacities.

        The layout is the source of truth: a header with an explicit size
        is pushed into the zone (ITE-style ARGB zones report 0 LEDs until
        resized), while unsized headers adopt the zone capacity.

        Args:
            zones: Zone snapshots from the last connect.
        """
        by_index = {zone.index: zone for zone in zones}
        for header in self._layout.headers:
            zone = by_index.get(header.zone_index)
            if zone is None:
                continue
            if header.size is None:
                # Adopt the discovered capacity for this run only; the
                # scene file stays the untouched source of truth.
                header.size = zone.leds
            elif header.size != zone.leds:
                try:
                    await asyncio.to_thread(
                        self._client.resize_zone, header.zone_index, header.size
                    )
                except DeviceNotConnectedError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "argb_zone_resize_failed",
                        header=header.id,
                        error=str(exc),
                    )
                    header.size = zone.leds

    async def _sync_zone_sizes_if_connected(self) -> None:
        """Push explicit header sizes into the zones when connected.

        Called on every engine apply: without it, an edited channel LED
        count would make each send a size mismatch until reconnect.
        """
        if not self._client.is_connected:
            return
        async with self._lock:
            zones = await asyncio.to_thread(self._client.list_zones)
            await asyncio.to_thread(self._sync_header_sizes, zones)
        self._last_sent = {}

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while the effect engine loop is scheduled."""
        return self._run_task is not None and not self._run_task.done()

    async def apply(self, layout: ArgbLayout) -> dict[str, Any]:
        """Adopt a layout and (re)start the effect engine.

        The layout becomes the runtime state; persisting it is the scene
        service's job (it lives in the scene's ``argb`` section).

        The engine runs even without an OpenRGB connection; zone sends
        simply resume once a connection exists. While connected, explicit
        header sizes are pushed into the zones first so LED-count edits
        don't make every send a size mismatch.

        Args:
            layout: The validated layout to run.

        Returns:
            Status snapshot after the restart.

        Raises:
            ArgbError: If the layout does not match the device library.
        """
        counts = validate_with_library(layout, self._library)
        self._layout = layout
        await self._sync_zone_sizes_if_connected()
        await self._restart_engine(counts)
        await self._publish_status()
        return self.status()

    async def stop(self) -> dict[str, Any]:
        """Stop the running engine, if any.

        Returns:
            Status snapshot after the stop.
        """
        task = self._run_task
        self._run_task = None
        self._run_layout = None
        self._last_sent = {}
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._publish_status()
        return self.status()

    async def shutdown(self) -> None:
        """Stop everything; called from the app lifespan."""
        await self.disconnect()

    # ------------------------------------------------------------------
    # Settings and display power
    # ------------------------------------------------------------------

    def argb_settings(self) -> dict[str, Any]:
        """Return the ARGB settings snapshot."""
        return self._argb_settings.model_dump()

    async def set_argb_settings(
        self, *, off_on_display_off: bool | None = None
    ) -> dict[str, Any]:
        """Update and persist the ARGB settings.

        Args:
            off_on_display_off: Turn the lighting off with the Windows
                display and restore it when the display turns back on.

        Returns:
            The updated settings snapshot.
        """
        update: dict[str, Any] = {
            key: value
            for key, value in (("off_on_display_off", off_on_display_off),)
            if value is not None
        }
        self._argb_settings = self._argb_settings.model_copy(update=update)
        save_argb_settings(self._argb_settings, self._settings_file)
        logger.info("argb_settings_changed", **update)
        return self.argb_settings()

    def on_monitor_power(self, monitor_on: bool) -> None:
        """React to a Windows monitor power event (watcher thread).

        Marshals the action onto the event loop; no-ops unless the
        ``off_on_display_off`` setting is enabled.

        Args:
            monitor_on: True when the Windows display turned on.
        """
        if self._loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            self.apply_display_power(monitor_on), self._loop
        )
        future.add_done_callback(_consume_future)

    async def apply_display_power(self, monitor_on: bool) -> None:
        """Apply the lighting state matching the Windows display power.

        On display off: stop the engine and black every known zone once.
        On display on: restart the engine from the last applied layout,
        but only when this service did the blanking.

        Args:
            monitor_on: True when the Windows display turned on.
        """
        if monitor_on:
            if not self._display_blanked:
                return
            self._display_blanked = False
            if self._layout.devices and not self.is_running:
                await self._restart_engine()
                await self._publish_status()
            return
        if not self._argb_settings.off_on_display_off:
            return
        if self._display_blanked or not self.is_running:
            return
        self._display_blanked = True
        task = self._run_task
        self._run_task = None
        self._run_layout = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._send_black()
        await self._publish_status()
        logger.info("argb_blanked_for_display_off")

    async def _send_black(self) -> None:
        """Push zeroed buffers to every zone with a known capacity."""
        if not self._client.is_connected:
            return
        async with self._lock:
            for header in self._layout.headers:
                if header.size is None:
                    continue
                await asyncio.to_thread(
                    self._client.send_zone, header.zone_index, bytes(header.size * 3)
                )
        self._last_sent = {}

    async def _restart_engine(self, counts: dict[str, int] | None = None) -> None:
        """Cancel any current loop and start a fresh one.

        Args:
            counts: Resolved LED counts; resolved from the library when
                omitted.

        Raises:
            ArgbError: If counts were not given and the stored layout no
                longer matches the device library.
        """
        if counts is None:
            counts = validate_with_library(self._layout, self._library)
        old = self._run_task
        self._run_task = None
        if old is not None and not old.done():
            old.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old
        self._run_layout = self._layout
        self._run_counts = counts
        self._last_sent = {}
        self._run_task = asyncio.get_running_loop().create_task(
            self._engine_loop(self._layout, counts)
        )

    async def _engine_loop(
        self, layout: ArgbLayout, counts: dict[str, int]
    ) -> None:
        """Render the layout at its fps and push changed buffers to OpenRGB.

        Args:
            layout: Frozen layout snapshot for this run.
            counts: Frozen LED counts matching this run's definitions.
        """
        interval = 1.0 / layout.fps
        lut = brightness_lut(layout.brightness)
        t0 = time.perf_counter()
        logger.info("argb_engine_started", fps=layout.fps)
        try:
            while True:
                start = time.perf_counter()
                elapsed = start - t0
                if elapsed - self._last_poll >= _SAMPLE_INTERVAL:
                    self._last_poll = elapsed
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(self._sources.poll)
                        self._samples = self._sources.snapshot()
                buffers = await asyncio.to_thread(
                    render_layout, layout, elapsed, self._samples, counts
                )
                await self._dispatch(buffers, lut)
                sleep_time = interval - (time.perf_counter() - start)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("argb_engine_failed", error=str(exc))
            self._run_task = None
            await self._bus.publish("error", {"source": "argb", "error": str(exc)})

    async def _dispatch(self, buffers: dict[str, bytearray], lut: list[int]) -> None:
        """Send changed, brightness-scaled zone buffers to OpenRGB.

        While disconnected, an automatic recovery runs throttled in the
        background so a restarted OpenRGB picks the stream back up.

        Args:
            buffers: Per-header raw RGB buffers from the engine.
            lut: Brightness lookup table to apply before sending.
        """
        run_layout = self._run_layout
        if run_layout is None:
            return
        for header in run_layout.headers:
            buf = buffers.get(header.id)
            if buf is None:
                continue
            out = bytearray(buf)
            apply_brightness(out, lut)
            raw = bytes(out)
            if not self._client.is_connected:
                if await self._recover_output():
                    # Buffers were rendered against stale zone sizes; the
                    # next tick re-renders with the synced capacities.
                    return
                continue
            if header.size is None:
                continue
            if self._last_sent.get(header.id) == raw:
                continue
            self._last_sent[header.id] = raw
            async with self._lock:
                await asyncio.to_thread(self._client.send_zone, header.zone_index, raw)
            self._frames_sent += 1

    async def _recover_output(self) -> bool:
        """Throttled OpenRGB process + session (re)establishment.

        Returns:
            True when the SDK session became connected.
        """
        now = time.monotonic()
        if now - self._last_recover < _RECOVER_INTERVAL:
            return False
        self._last_recover = now
        try:
            if self._proc is not None:
                await self._proc.ensure_running()
            async with self._lock:
                zones = await asyncio.to_thread(self._client.connect)
                await self._sync_header_sizes(zones)
            self._last_sent = {}
            await self._publish_status()
            logger.info("argb_output_recovered")
            return True
        except Exception as exc:
            logger.debug("argb_output_recover_failed", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # Preview and status
    # ------------------------------------------------------------------

    def render_preview(
        self, layout: ArgbLayout, t: float | None = None
    ) -> dict[str, str]:
        """Render one frame of any layout as hex buffers, hardware-free.

        Args:
            layout: Layout to render (typically the editor's draft).
            t: Effect time; None uses the current wall clock.

        Returns:
            Mapping of header id to a packed ``RGBRGB...`` hex string.

        Raises:
            ArgbError: If the layout does not match the device library.
        """
        if t is None:
            t = time.monotonic() % 3600.0
        counts = validate_with_library(layout, self._library)
        buffers = render_layout(layout, t, self._samples, counts)
        return {header_id: bytes(buf).hex() for header_id, buf in buffers.items()}

    def status(self) -> dict[str, Any]:
        """Return the ARGB subsystem status snapshot."""
        return {
            "connected": self._client.is_connected,
            "controller": self._client.controller_name(),
            "zones": [zone.as_dict() for zone in self._client.list_zones()],
            "running": self.is_running,
            "fps": self._layout.fps,
            "brightness": self._layout.brightness,
            "frames_sent": self._frames_sent,
            "process": self._proc.status() if self._proc is not None else None,
        }

    async def _publish_status(self) -> None:
        """Broadcast the status snapshot on the ``argb`` SSE topic."""
        await self._bus.publish("argb", {"type": "status", **self.status()})
