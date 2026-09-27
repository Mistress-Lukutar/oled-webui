"""
File:   display_service.py
Brief:  Central display orchestrator: USB serialization, keepalive, video.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from oled_webui.core.constants import DEFAULT_RESOLUTION
from oled_webui.core.models import HandshakeResult
from oled_webui.exceptions import (
    DeviceNotConnectedError,
    TransportError,
    ValidationError,
)
from oled_webui.scene.runner import SceneRenderer
from oled_webui.scene.schema import SceneDocument
from oled_webui.services.bulk_device import BulkLcd
from oled_webui.services.frame_builder import (
    FrameBuilder,
    build_black_frame,
    parse_hex_color,
)
from oled_webui.services.video_player import ensure_ffmpeg, extract_video_frames

if TYPE_CHECKING:
    from oled_webui.config import Settings
    from oled_webui.services.event_bus import EventBus

logger = structlog.get_logger(__name__)

# Colors cycled by the hardware test pattern.
TEST_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (0, 0, 0),
)


class DisplayService:
    """Single owner of the USB display for the whole application.

    All USB traffic is serialized through one asyncio.Lock: without it,
    concurrent requests (e.g. keepalive resend vs. image upload) would
    interleave bulk writes and corrupt frames. Blocking USB and Pillow work
    runs in worker threads via asyncio.to_thread so the event loop stays
    responsive.
    """

    def __init__(self, settings: Settings, bus: EventBus) -> None:
        self._settings = settings
        self._bus = bus
        self._lcd = BulkLcd()
        self._lock = asyncio.Lock()
        self._handshake: HandshakeResult | None = None

        self._keepalive_task: asyncio.Task[None] | None = None
        self._keepalive_stop = asyncio.Event()
        self._keepalive_enabled = settings.keepalive_enabled
        self._keepalive_interval = settings.keepalive_interval

        self._video_task: asyncio.Task[None] | None = None
        self._video_stop = threading.Event()
        self._video_state: dict[str, Any] = {
            "playing": False,
            "preparing": False,
            "file": None,
            "loop": False,
            "fps": 0,
            "frames_sent": 0,
        }

        self._scene_task: asyncio.Task[None] | None = None
        self._scene_state: dict[str, Any] = {
            "running": False,
            "scene_id": None,
            "name": None,
            "refresh": 0,
            "max_fps": 0,
            "frames_sent": 0,
        }

        self._last_frame: bytes | None = None
        self._last_frame_size: tuple[int, int] | None = None
        self._last_content: dict[str, Any] | None = None
        self._last_preview_emit: float = 0.0

        self._bg_tasks: set[asyncio.Task[Any]] = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when the display handshake has completed."""
        return self._lcd.is_connected and self._handshake is not None

    async def connect(self) -> HandshakeResult:
        """Open the USB device and perform the handshake.

        Returns:
            Handshake result with resolution and device IDs.
        """
        async with self._lock:
            result = await asyncio.to_thread(self._lcd.connect)
        self._handshake = result
        logger.info(
            "display_connected",
            device=result.device_key,
            resolution=str(result.resolution),
        )
        await self._bus.publish(
            "connection", {"connected": True, "device": result.model_dump()}
        )
        if self._keepalive_enabled:
            await self._start_keepalive()
        return result

    async def disconnect(self) -> None:
        """Stop background tasks and close the USB device."""
        await self.stop_video()
        await self.stop_scene()
        await self._stop_keepalive()
        async with self._lock:
            await asyncio.to_thread(self._lcd.disconnect)
        self._handshake = None
        logger.info("display_disconnected")
        await self._bus.publish("connection", {"connected": False})

    async def shutdown(self) -> None:
        """Cleanly stop everything; called from the app lifespan."""
        await self.disconnect()

    def require_connection(self) -> HandshakeResult:
        """Return the handshake result or raise if not connected.

        Raises:
            DeviceNotConnectedError: If the display is not connected.
        """
        if not self.is_connected or self._handshake is None:
            raise DeviceNotConnectedError("Display is not connected")
        return self._handshake

    # ------------------------------------------------------------------
    # Frame sending
    # ------------------------------------------------------------------

    def _builder(
        self,
        rotation: int = 0,
        brightness: int = 100,
        fit: str = "contain",
        quality: int = 95,
    ) -> FrameBuilder:
        handshake = self.require_connection()
        return FrameBuilder(
            width=handshake.resolution.width,
            height=handshake.resolution.height,
            rotation=rotation,
            brightness=brightness,
            fit=fit,
            quality=quality,
        )

    async def _send_payload(
        self, payload: bytes, width: int, height: int, *, throttle_preview: bool = False
    ) -> None:
        """Send an encoded frame under the USB lock and update preview state."""
        async with self._lock:
            await asyncio.to_thread(self._lcd.send, payload, width, height)
        self._last_frame = payload
        self._last_frame_size = (width, height)
        await asyncio.to_thread(self._persist_last_frame, payload)

        now = time.monotonic()
        if throttle_preview and now - self._last_preview_emit < (
            self._settings.preview_throttle
        ):
            return
        self._last_preview_emit = now
        self._bus.publish_soon(
            "frame_updated", {"width": width, "height": height, "ts": now}
        )

    def _persist_last_frame(self, payload: bytes) -> None:
        """Write the last frame to disk so preview survives a restart."""
        try:
            self._settings.last_frame_path.write_bytes(payload)
        except OSError as exc:
            logger.warning("last_frame_persist_failed", error=str(exc))

    async def send_image(
        self,
        image_path: Path,
        rotation: int = 0,
        brightness: int = 100,
        fit: str = "contain",
        quality: int = 95,
    ) -> dict[str, Any]:
        """Render and send an image file to the display.

        Args:
            image_path: Path to the source image (already saved on disk).
            rotation: Extra rotation in degrees on top of the panel base.
            brightness: Software brightness 0-200 percent.
            fit: Fit mode: contain, stretch, width or height.
            quality: JPEG quality 1-100.

        Returns:
            Summary dict with frame size and payload length.
        """
        await self.stop_scene()
        builder = self._builder(rotation, brightness, fit, quality)
        frame = await asyncio.to_thread(builder.build_frame, image_path)
        payload = await asyncio.to_thread(builder.encode_jpeg, frame)
        await self._send_payload(payload, builder.width, builder.height)
        self._last_content = {
            "type": "image",
            "params": {
                "rotation": rotation,
                "brightness": brightness,
                "fit": fit,
                "quality": quality,
            },
            "payload": {"file": image_path.name},
        }
        logger.info("image_sent", file=image_path.name, bytes=len(payload))
        return {"width": builder.width, "height": builder.height, "bytes": len(payload)}

    async def send_color(self, color: str, brightness: int = 100) -> dict[str, Any]:
        """Fill the display with a solid color.

        Args:
            color: Hex color string (``#RRGGBB`` or ``RRGGBB``).
            brightness: Software brightness 0-200 percent.

        Returns:
            Summary dict with frame size and payload length.
        """
        await self.stop_scene()
        rgb = parse_hex_color(color)
        builder = self._builder(brightness=brightness)
        image = builder.build_color_image(rgb)
        payload = await asyncio.to_thread(builder.encode_jpeg, image)
        await self._send_payload(payload, builder.width, builder.height)
        self._last_content = {
            "type": "color",
            "params": {"brightness": brightness},
            "payload": {"color": color.lstrip("#")},
        }
        logger.info("color_sent", color=color, bytes=len(payload))
        return {"width": builder.width, "height": builder.height, "bytes": len(payload)}

    async def send_text(
        self,
        text: str,
        font_size: int = 48,
        color: str = "#ffffff",
        background: str = "#000000",
        align: str = "center",
        valign: str = "middle",
        padding: int = 20,
        rotation: int = 0,
        brightness: int = 100,
        quality: int = 95,
        font_name: str | None = None,
    ) -> dict[str, Any]:
        """Render text and send it to the display.

        Args:
            text: Multi-line text content.
            font_size: Font size in pixels.
            color: Text color hex string.
            background: Background color hex string.
            align: Horizontal alignment: left, center or right.
            valign: Vertical alignment: top, middle or bottom.
            padding: Margin around the text block in pixels.
            rotation: Extra rotation in degrees.
            brightness: Software brightness 0-200 percent.
            quality: JPEG quality 1-100.
            font_name: Optional TTF/OTF file name inside the fonts directory.

        Returns:
            Summary dict with frame size and payload length.
        """
        await self.stop_scene()
        font_path: Path | None = None
        if font_name:
            font_path = self._settings.fonts_dir / font_name
            if not font_path.is_file():
                raise ValidationError(f"Font not found: {font_name}")

        builder = self._builder(
            rotation=rotation, brightness=brightness, quality=quality
        )
        fg = parse_hex_color(color)
        bg = parse_hex_color(background)
        frame = await asyncio.to_thread(
            builder.render_text_frame,
            text,
            font_size,
            fg,
            bg,
            align,
            valign,
            padding,
            font_path,
        )
        frame = await asyncio.to_thread(builder.apply_user_rotation, frame)
        frame = await asyncio.to_thread(builder.apply_base_rotation, frame)
        frame = await asyncio.to_thread(builder.apply_brightness, frame)
        payload = await asyncio.to_thread(builder.encode_jpeg, frame)
        await self._send_payload(payload, builder.width, builder.height)
        self._last_content = {
            "type": "text",
            "params": {
                "rotation": rotation,
                "brightness": brightness,
                "quality": quality,
            },
            "payload": {
                "text": text,
                "font_size": font_size,
                "color": color.lstrip("#"),
                "background": background.lstrip("#"),
                "align": align,
                "valign": valign,
                "padding": padding,
                "font_name": font_name,
            },
        }
        logger.info("text_sent", chars=len(text), bytes=len(payload))
        return {"width": builder.width, "height": builder.height, "bytes": len(payload)}

    async def power_off(self) -> None:
        """Blank the display with a black frame (kept alive by keepalive)."""
        handshake = self.require_connection()
        await self.stop_scene()
        builder = self._builder()
        image = build_black_frame(
            handshake.resolution.width, handshake.resolution.height
        )
        payload = await asyncio.to_thread(builder.encode_jpeg, image)
        await self._send_payload(
            payload, handshake.resolution.width, handshake.resolution.height
        )
        self._last_content = {
            "type": "color",
            "params": {"brightness": 100},
            "payload": {"color": "000000"},
        }
        logger.info("display_blanked")

    async def power_on(self) -> None:
        """Re-send the last frame, restoring content after a blank.

        Raises:
            ValidationError: If no frame has been sent yet.
        """
        if self._last_frame is None or self._last_frame_size is None:
            raise ValidationError("No cached frame to restore")
        width, height = self._last_frame_size
        async with self._lock:
            await asyncio.to_thread(self._lcd.send, self._last_frame, width, height)
        self._bus.publish_soon(
            "frame_updated", {"width": width, "height": height, "ts": time.monotonic()}
        )
        logger.info("display_restored")

    async def run_test(self, delay: float = 1.0) -> None:
        """Cycle red, green, blue and black frames across the display.

        Args:
            delay: Seconds between color steps.
        """
        handshake = self.require_connection()
        await self.stop_scene()
        builder = self._builder()
        for rgb in TEST_COLORS:
            image = builder.build_color_image(rgb)
            payload = await asyncio.to_thread(builder.encode_jpeg, image)
            await self._send_payload(
                payload, handshake.resolution.width, handshake.resolution.height
            )
            await asyncio.sleep(delay)
        self._last_content = {
            "type": "color",
            "params": {"brightness": 100},
            "payload": {"color": "000000"},
        }
        logger.info("test_pattern_done")

    # ------------------------------------------------------------------
    # Keepalive
    # ------------------------------------------------------------------

    async def set_keepalive(self, enabled: bool, interval: float | None = None) -> None:
        """Enable or disable the keepalive loop.

        Args:
            enabled: Whether the panel refresh loop should run.
            interval: Optional new resend interval in seconds.
        """
        if interval is not None:
            if interval < 0.1:
                raise ValidationError("Keepalive interval must be >= 0.1 seconds")
            self._keepalive_interval = interval
        self._keepalive_enabled = enabled

        if enabled and self.is_connected:
            await self._start_keepalive()
        else:
            await self._stop_keepalive()

        await self._bus.publish(
            "keepalive",
            {"enabled": enabled, "interval": self._keepalive_interval},
        )
        logger.info("keepalive_changed", enabled=enabled)

    async def _start_keepalive(self) -> None:
        if self._keepalive_task is not None and not self._keepalive_task.done():
            return
        self._keepalive_stop.clear()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        self._bg_tasks.add(self._keepalive_task)
        self._keepalive_task.add_done_callback(self._bg_tasks.discard)

    async def _stop_keepalive(self) -> None:
        self._keepalive_stop.set()
        task = self._keepalive_task
        self._keepalive_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _keepalive_loop(self) -> None:
        """Periodically resend the last frame so the panel keeps showing it.

        The panel falls back to its built-in logo after ~2-3 seconds without
        frames; video playback refreshes the panel by itself, so resends are
        skipped while a video is playing.
        """
        while not self._keepalive_stop.is_set():
            try:
                await asyncio.wait_for(
                    self._keepalive_stop.wait(), timeout=self._keepalive_interval
                )
                break
            except TimeoutError:
                pass

            if self._video_state["playing"] or self._scene_state["running"]:
                continue
            if self._last_frame is None or self._last_frame_size is None:
                continue
            try:
                width, height = self._last_frame_size
                async with self._lock:
                    await asyncio.to_thread(
                        self._lcd.send, self._last_frame, width, height
                    )
            except (TransportError, DeviceNotConnectedError) as exc:
                logger.warning("keepalive_send_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Video playback
    # ------------------------------------------------------------------

    async def play_video(
        self,
        video_path: Path,
        fps: int = 30,
        loop: bool = False,
        rotation: int = 0,
        brightness: int = 100,
        fit: str = "contain",
        quality: int = 95,
    ) -> None:
        """Start streaming a video file to the display in the background.

        Args:
            video_path: Video file readable by ffmpeg.
            fps: Target frames per second (1-60).
            loop: Restart playback when the file ends.
            rotation: Extra rotation in degrees.
            brightness: Software brightness 0-200 percent.
            fit: Fit mode (applied before encoding).
            quality: JPEG quality 1-100.

        Raises:
            ValidationError: If a video is already playing.
        """
        self.require_connection()
        await self.stop_scene()
        ensure_ffmpeg()
        if self._video_task is not None and not self._video_task.done():
            raise ValidationError("A video is already playing")

        self._video_stop.clear()
        self._video_state = {
            "playing": True,
            "preparing": True,
            "file": video_path.name,
            "loop": loop,
            "fps": fps,
            "frames_sent": 0,
        }
        self._video_task = asyncio.create_task(
            self._video_loop(video_path, fps, loop, rotation, brightness, fit, quality)
        )
        self._bg_tasks.add(self._video_task)
        self._video_task.add_done_callback(self._bg_tasks.discard)
        await self._bus.publish(
            "video", {"playing": True, "file": video_path.name, "loop": loop}
        )
        logger.info("video_started", file=video_path.name, fps=fps, loop=loop)

    async def stop_video(self) -> None:
        """Stop the running video playback, if any."""
        task = self._video_task
        if task is None or task.done():
            return
        self._video_stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._video_state["playing"] = False
        await self._bus.publish("video", {"playing": False})
        logger.info("video_stopped")

    async def _video_loop(
        self,
        path: Path,
        fps: int,
        loop: bool,
        rotation: int,
        brightness: int,
        fit: str,
        quality: int,
    ) -> None:
        """Prepare panel-ready JPEG frames once, then stream the files.

        All image processing (fit, rotation, brightness, JPEG encoding)
        happens in a single ffmpeg pass before playback starts; the
        streaming loop only reads encoded files and pushes them over USB,
        keeping per-frame CPU cost near zero.

        Args:
            path: Video file readable by ffmpeg.
            fps: Target frames per second.
            loop: Restart playback when the file ends.
            rotation: User rotation in degrees.
            brightness: Software brightness 0-200 percent.
            fit: Fit mode applied during extraction.
            quality: JPEG quality applied during extraction.
        """
        handshake = self.require_connection()
        width = handshake.resolution.width
        height = handshake.resolution.height
        frame_interval = 1.0 / fps
        frames_dir = Path(tempfile.mkdtemp(prefix="oled_video_"))
        try:
            frames = await asyncio.to_thread(
                extract_video_frames,
                path,
                frames_dir,
                fps,
                width,
                height,
                fit,
                rotation,
                brightness,
                quality,
                self._video_stop,
            )
            self._video_state["preparing"] = False
            self._bus.publish_soon("video", dict(self._video_state))
            last_progress = time.monotonic()
            while not self._video_stop.is_set():
                for frame_path in frames:
                    if self._video_stop.is_set():
                        break
                    start = time.perf_counter()
                    payload = await asyncio.to_thread(frame_path.read_bytes)
                    await self._send_payload(
                        payload, width, height, throttle_preview=True
                    )
                    self._video_state["frames_sent"] += 1

                    # Periodic state push so the UI keeps the playback
                    # status and frame counter current.
                    now = time.monotonic()
                    if now - last_progress >= 1.0:
                        last_progress = now
                        self._bus.publish_soon("video", dict(self._video_state))

                    elapsed = time.perf_counter() - start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                if not loop:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("video_failed", error=str(exc))
            await self._bus.publish("error", {"source": "video", "error": str(exc)})
        finally:
            self._video_state["playing"] = False
            self._video_state["preparing"] = False
            await self._bus.publish(
                "video",
                {
                    "playing": False,
                    "file": path.name,
                    "frames_sent": self._video_state["frames_sent"],
                },
            )
            await asyncio.to_thread(shutil.rmtree, frames_dir, True)

    # ------------------------------------------------------------------
    # Scene playback
    # ------------------------------------------------------------------

    async def start_scene(
        self,
        document: SceneDocument,
        scene_id: str,
        scene_name: str,
    ) -> dict[str, Any]:
        """Start rendering a scene to the display in the background.

        Starts a fresh scene, replacing any previously running one; video
        playback is stopped first.

        Args:
            document: Validated scene document with resolved asset paths.
            scene_id: Scene identifier for state and preset saving.
            scene_name: Human-readable scene name.

        Returns:
            The scene state snapshot.
        """
        handshake = self.require_connection()
        await self.stop_video()
        await self._stop_scene_task()

        renderer = SceneRenderer(
            document,
            handshake.resolution,
        )
        self._scene_state = {
            "running": True,
            "scene_id": scene_id,
            "name": scene_name,
            "refresh": renderer.refresh,
            "max_fps": renderer.max_fps,
            "frames_sent": 0,
        }
        self._scene_task = asyncio.create_task(self._scene_loop(renderer))
        self._bg_tasks.add(self._scene_task)
        self._scene_task.add_done_callback(self._bg_tasks.discard)
        self._last_content = {
            "type": "scene",
            "params": {
                "brightness": document.brightness,
                "quality": document.quality,
            },
            "payload": {"scene_id": scene_id, "name": scene_name},
        }
        await self._bus.publish(
            "scene",
            {"running": True, "scene_id": scene_id, "name": scene_name},
        )
        logger.info(
            "scene_started",
            scene_id=scene_id,
            widgets=len(document.widgets),
            refresh=renderer.refresh,
        )
        return dict(self._scene_state)

    async def stop_scene(self) -> None:
        """Stop the running scene, if any, and publish the state change."""
        if not self._scene_state["running"]:
            return
        await self._stop_scene_task()
        await self._bus.publish(
            "scene",
            {"running": False, "scene_id": self._scene_state["scene_id"]},
        )
        logger.info("scene_stopped", scene_id=self._scene_state["scene_id"])

    async def _stop_scene_task(self) -> None:
        """Cancel the scene loop task without publishing."""
        task = self._scene_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._scene_state["running"] = False

    async def _scene_loop(self, renderer: SceneRenderer) -> None:
        """Tick the renderer and send frames until cancelled or failure."""
        frame_interval = 1.0 / renderer.max_fps
        width, height = renderer.size
        try:
            while True:
                start = time.perf_counter()
                payload = await asyncio.to_thread(renderer.tick)
                if payload is not None:
                    await self._send_payload(
                        payload, width, height, throttle_preview=True
                    )
                    self._scene_state["frames_sent"] += 1
                elapsed = time.perf_counter() - start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("scene_failed", error=str(exc))
            self._scene_state["running"] = False
            await self._bus.publish("error", {"source": "scene", "error": str(exc)})

    # ------------------------------------------------------------------
    # Status and preview
    # ------------------------------------------------------------------

    def get_preview(self) -> bytes | None:
        """Return the last sent JPEG frame, falling back to the disk copy."""
        if self._last_frame is not None:
            return self._last_frame
        path = self._settings.last_frame_path
        if path.is_file():
            try:
                return path.read_bytes()
            except OSError:
                return None
        return None

    @property
    def last_content(self) -> dict[str, Any] | None:
        """Description of the last applied content, for preset saving."""
        return self._last_content

    def status(self) -> dict[str, Any]:
        """Build the full status snapshot for the API and SSE."""
        device = self._handshake.model_dump() if self._handshake else None
        return {
            "connected": self.is_connected,
            "device": device,
            "keepalive": {
                "enabled": self._keepalive_enabled,
                "interval": self._keepalive_interval,
            },
            "video": dict(self._video_state),
            "scene": dict(self._scene_state),
            "has_frame": self.get_preview() is not None,
            "last_content": self._last_content,
        }

    def panel_resolution(self) -> tuple[int, int]:
        """Return the panel size, or the default fallback when disconnected.

        Used by render-only paths (scene preview) that must work without
        hardware.

        Returns:
            (width, height) tuple.
        """
        if self._handshake is not None:
            return (self._handshake.resolution.width, self._handshake.resolution.height)
        return (DEFAULT_RESOLUTION.width, DEFAULT_RESOLUTION.height)
