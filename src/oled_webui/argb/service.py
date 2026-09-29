"""
File:   service.py
Brief:  ARGB orchestration: layout persistence, effect loop, OpenRGB output.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.5.1
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import TYPE_CHECKING, Any

import structlog

from oled_webui.argb.engine import apply_brightness, render_layout
from oled_webui.argb.schema import ArgbLayout, default_layout
from oled_webui.exceptions import ArgbError, DeviceNotConnectedError
from oled_webui.infrastructure.openrgb_transport import OpenRgbClient
from oled_webui.scene.providers import DataSources
from oled_webui.services.event_bus import EventBus
from oled_webui.services.frame_builder import brightness_lut

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

# Meter source polling interval in seconds.
_SAMPLE_INTERVAL: float = 1.0


class ArgbService:
    """Single owner of the OpenRGB connection and the effect engine loop.

    The engine is hardware-independent: :meth:`render_preview` renders any
    layout without a device, which is what the web editor previews through.
    While the engine runs, each tick also pushes changed zone buffers to
    OpenRGB (when connected) after gamma-corrected brightness scaling.
    """

    def __init__(self, settings: Settings, bus: EventBus) -> None:
        self._settings = settings
        self._bus = bus
        self._client = OpenRgbClient(settings.openrgb_host, settings.openrgb_port)
        self._lock = asyncio.Lock()
        self._layout_file = settings.argb_dir / "layout.json"
        self._layout: ArgbLayout = self._load_layout()
        self._run_task: asyncio.Task[None] | None = None
        self._run_layout: ArgbLayout | None = None
        self._last_sent: dict[str, bytes] = {}
        self._frames_sent = 0
        self._last_poll = float("-inf")
        self._sources = DataSources()
        self._samples: dict[str, float | str] = self._sources.snapshot()

    # ------------------------------------------------------------------
    # Layout access and persistence
    # ------------------------------------------------------------------

    @property
    def layout(self) -> ArgbLayout:
        """The stored (last saved/applied) layout."""
        return self._layout

    def save_layout(self, layout: ArgbLayout) -> ArgbLayout:
        """Validate and persist a layout atomically.

        Args:
            layout: Layout to store.

        Returns:
            The stored layout.

        Raises:
            ArgbError: If the layout cannot be written to disk.
        """
        try:
            payload = json.dumps(layout.model_dump(), indent=2)
            tmp = self._layout_file.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._layout_file)
        except OSError as exc:
            raise ArgbError(f"Failed to save ARGB layout: {exc}") from exc
        self._layout = layout
        return layout

    def _load_layout(self) -> ArgbLayout:
        """Load the persisted layout, falling back to the default.

        Returns:
            The loaded layout, or a starter layout when nothing valid
            exists on disk.
        """
        try:
            text = self._layout_file.read_text(encoding="utf-8")
            return ArgbLayout.model_validate_json(text)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("argb_layout_load_failed", error=str(exc))
        return default_layout()

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

        Returns:
            Status snapshot after connection.
        """
        async with self._lock:
            zones = await asyncio.to_thread(self._client.connect)
        self._last_sent = {}
        self._sync_header_sizes(zones)
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

    def _sync_header_sizes(self, zones: list[Any]) -> None:
        """Persist discovered zone capacities into matching headers."""
        by_index = {zone.index: zone for zone in zones}
        changed = False
        for header in self._layout.headers:
            zone = by_index.get(header.zone_index)
            if zone is not None and header.size != zone.leds:
                header.size = zone.leds
                changed = True
        if changed:
            self.save_layout(self._layout)

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True while the effect engine loop is scheduled."""
        return self._run_task is not None and not self._run_task.done()

    async def apply(self, layout: ArgbLayout) -> dict[str, Any]:
        """Store a layout and (re)start the effect engine.

        The engine runs even without an OpenRGB connection; zone sends
        simply resume once a connection exists.

        Args:
            layout: The validated layout to run.

        Returns:
            Status snapshot after the restart.
        """
        self.save_layout(layout)
        await self._restart_engine()
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

    async def _restart_engine(self) -> None:
        """Cancel any current loop and start a fresh one."""
        old = self._run_task
        self._run_task = None
        if old is not None and not old.done():
            old.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old
        self._run_layout = self._layout
        self._last_sent = {}
        self._run_task = asyncio.get_running_loop().create_task(
            self._engine_loop(self._layout)
        )

    async def _engine_loop(self, layout: ArgbLayout) -> None:
        """Render the layout at its fps and push changed buffers to OpenRGB.

        Args:
            layout: Frozen layout snapshot for this run.
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
                    render_layout, layout, elapsed, self._samples
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
            if not self._client.is_connected or header.size is None:
                continue
            if self._last_sent.get(header.id) == raw:
                continue
            self._last_sent[header.id] = raw
            async with self._lock:
                await asyncio.to_thread(self._client.send_zone, header.zone_index, raw)
            self._frames_sent += 1

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
        """
        if t is None:
            t = time.monotonic() % 3600.0
        buffers = render_layout(layout, t, self._samples)
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
            "autostart": self._layout.autostart,
            "frames_sent": self._frames_sent,
        }

    async def _publish_status(self) -> None:
        """Broadcast the status snapshot on the ``argb`` SSE topic."""
        await self._bus.publish("argb", {"type": "status", **self.status()})
