"""
File:   openrgb_transport.py
Brief:  Synchronous OpenRGB SDK client wrapper for ARGB header output.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.5.1
"""

from __future__ import annotations

import contextlib
from typing import Any

import structlog

from oled_webui.exceptions import OpenRgbError

logger = structlog.get_logger(__name__)

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 6742


class ZoneInfo:
    """Snapshot of one OpenRGB zone (an ARGB header on the controller)."""

    __slots__ = ("index", "leds", "name")

    def __init__(self, index: int, name: str, leds: int) -> None:
        self.index = index
        self.name = name
        self.leds = leds

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {"index": self.index, "name": self.name, "leds": self.leds}


class OpenRgbClient:
    """Blocking OpenRGB SDK client bound to one controller device.

    All methods are synchronous and must be called off the event loop
    (``asyncio.to_thread``). The ARGB service is the single owner.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._client: Any | None = None
        self._controller: Any | None = None
        self._zone_objects: list[Any] = []
        self._zones: list[ZoneInfo] = []

    @property
    def is_connected(self) -> bool:
        """True when the SDK session is open."""
        return self._client is not None

    def connect(self) -> list[ZoneInfo]:
        """Open the SDK session and bind the RGB controller.

        The controller is the first motherboard-type device reported by
        OpenRGB (any device type is accepted as a fallback so USB ARGB
        controllers work too). A ``Direct`` mode is requested when the
        controller offers one, enabling per-LED updates.

        Returns:
            Discovered zones as :class:`ZoneInfo` snapshots.

        Raises:
            OpenRgbError: If the server is unreachable or reports no device.
        """
        if self._client is not None:
            return self.list_zones()
        try:
            from openrgb import OpenRGBClient
            from openrgb.utils import DeviceType
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise OpenRgbError("openrgb-python is not installed") from exc
        try:
            client = OpenRGBClient(address=self._host, port=self._port)
        except Exception as exc:
            raise OpenRgbError(
                f"Cannot reach OpenRGB SDK server at {self._host}:{self._port}: {exc}"
            ) from exc
        try:
            devices = list(client.devices)
            controller = next(
                (d for d in devices if d.type == DeviceType.MOTHERBOARD), None
            )
            if controller is None:
                controller = devices[0] if devices else None
            if controller is None:
                client.disconnect()
                raise OpenRgbError("OpenRGB reports no RGB devices")
            for mode in ("Direct", "Static"):
                if any(getattr(m, "name", "") == mode for m in controller.modes):
                    controller.set_mode(mode)
                    break
            self._client = client
            self._controller = controller
            self._zone_objects = list(controller.zones)
            self._zones = [
                ZoneInfo(index, str(zone.name), len(zone.leds))
                for index, zone in enumerate(self._zone_objects)
            ]
        except OpenRgbError:
            raise
        except Exception as exc:
            self._close_quietly()
            raise OpenRgbError(f"OpenRGB session failed: {exc}") from exc
        logger.info(
            "openrgb_connected",
            controller=getattr(self._controller, "name", "?"),
            zones=len(self._zones),
        )
        return self.list_zones()

    def list_zones(self) -> list[ZoneInfo]:
        """Return the discovered zone snapshots."""
        return list(self._zones)

    def controller_name(self) -> str | None:
        """Return the bound controller name, if connected."""
        if self._controller is None:
            return None
        return str(getattr(self._controller, "name", None))

    def send_zone(self, zone_index: int, data: bytes) -> None:
        """Push one zone's colors as a packed RGBRGB... byte string.

        Args:
            zone_index: Zone index as reported by :meth:`connect`.
            data: Exactly ``leds * 3`` bytes of RGB values.

        Raises:
            OpenRgbError: If not connected or the buffer size mismatches.
        """
        if self._client is None or zone_index >= len(self._zone_objects):
            raise OpenRgbError("OpenRGB is not connected")
        zone = self._zone_objects[zone_index]
        leds = len(zone.leds)
        if len(data) != leds * 3:
            raise OpenRgbError(
                f"Zone {zone_index} expects {leds * 3} bytes, got {len(data)}"
            )
        try:
            from openrgb.utils import RGBColor

            colors = [
                RGBColor(data[i], data[i + 1], data[i + 2])
                for i in range(0, len(data), 3)
            ]
            zone.set_colors(colors, fast=True)
        except Exception as exc:
            raise OpenRgbError(f"Zone update failed: {exc}") from exc

    def disconnect(self) -> None:
        """Close the SDK session, ignoring errors."""
        self._close_quietly()
        logger.info("openrgb_disconnected")

    def _close_quietly(self) -> None:
        """Tear down client state without letting exceptions escape."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.disconnect()
        self._client = None
        self._controller = None
        self._zone_objects = []
        self._zones = []
