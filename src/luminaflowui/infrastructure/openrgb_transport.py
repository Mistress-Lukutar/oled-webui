"""
File:   openrgb_transport.py
Brief:  Synchronous OpenRGB SDK client wrapper for ARGB channel output.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.3
"""

from __future__ import annotations

import contextlib
from typing import Any

import structlog

from luminaflowui.exceptions import OpenRgbError

logger = structlog.get_logger(__name__)

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 6742


def _device_type_name(device: Any) -> str:
    """Human-readable OpenRGB device type ('motherboard', 'gpu', ...)."""
    raw = getattr(getattr(device, "type", None), "name", None)
    return str(raw) if raw else "unknown"


class ZoneInfo:
    """Snapshot of one OpenRGB zone (a hardware channel on any device).

    ``index`` is the session-wide flat enumeration across every OpenRGB
    device: motherboard ARGB headers, GPU and peripheral zones all share
    one index space, which is what layouts reference.
    """

    __slots__ = ("index", "leds", "name", "device_name", "device_type")

    def __init__(
        self,
        index: int,
        name: str,
        leds: int,
        device_name: str = "",
        device_type: str = "",
    ) -> None:
        self.index = index
        self.name = name
        self.leds = leds
        self.device_name = device_name
        self.device_type = device_type

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view."""
        return {
            "index": self.index,
            "name": self.name,
            "leds": self.leds,
            "device_name": self.device_name,
            "device_type": self.device_type,
        }


class OpenRgbClient:
    """Blocking OpenRGB SDK client covering every reported RGB device.

    All methods are synchronous and must be called off the event loop
    (``asyncio.to_thread``). The ARGB service is the single owner. Zones
    from all devices (motherboard, GPU, mice, ...) are enumerated into
    one flat index space used by layouts and by :meth:`send_zone` /
    :meth:`resize_zone`.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._client: Any | None = None
        self._devices: list[Any] = []
        self._zone_objects: list[Any] = []
        self._zones: list[ZoneInfo] = []

    @property
    def is_connected(self) -> bool:
        """True when the SDK session is open."""
        return self._client is not None

    def connect(self) -> list[ZoneInfo]:
        """Open the SDK session and enumerate every device's zones.

        Devices offering a ``Direct`` mode are switched to it (needed for
        per-LED control on ITE-style ARGB zones); devices without one are
        left untouched so their own effect modes survive.

        Returns:
            Discovered zones as flat-indexed :class:`ZoneInfo` snapshots.

        Raises:
            OpenRgbError: If the server is unreachable or reports no device.
        """
        if self._client is not None:
            return self.list_zones()
        try:
            from openrgb import OpenRGBClient
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
            if not devices:
                client.disconnect()
                raise OpenRgbError("OpenRGB reports no RGB devices")
            for device in devices:
                self._request_direct_mode(device)
            self._client = client
            self._devices = devices
            self._zone_objects = [
                zone for device in devices for zone in device.zones
            ]
            self._zones = []
            for index, (device, zone) in enumerate(
                (device, zone)
                for device in devices
                for zone in device.zones
            ):
                self._zones.append(
                    ZoneInfo(
                        index,
                        str(zone.name),
                        len(zone.leds),
                        str(getattr(device, "name", "?")),
                        _device_type_name(device),
                    )
                )
        except OpenRgbError:
            raise
        except Exception as exc:
            self._close_quietly()
            raise OpenRgbError(f"OpenRGB session failed: {exc}") from exc
        logger.info(
            "openrgb_connected",
            devices=len(self._devices),
            zones=len(self._zones),
        )
        return self.list_zones()

    def list_zones(self) -> list[ZoneInfo]:
        """Return the discovered zone snapshots."""
        return list(self._zones)

    @staticmethod
    def _request_direct_mode(device: Any) -> None:
        """Best-effort switch to a per-LED ``Direct`` mode.

        ITE-style ARGB zones need it; devices without the mode (or that
        reject the switch) keep their current mode.
        """
        try:
            if any(getattr(m, "name", "") == "Direct" for m in device.modes):
                device.set_mode("Direct")
        except Exception as exc:
            logger.debug(
                "openrgb_direct_mode_failed",
                device=getattr(device, "name", "?"),
                error=str(exc),
            )

    def controller_name(self) -> str | None:
        """Summary of the bound devices, e.g. ``AORUS ELITE +3 more``."""
        if not self._devices:
            return None
        first = str(getattr(self._devices[0], "name", None) or "?")
        extra = len(self._devices) - 1
        return first if extra == 0 else f"{first} +{extra} more"

    def send_zone(self, zone_index: int, data: bytes) -> None:
        """Push one zone's colors as a packed RGBRGB... byte string.

        Args:
            zone_index: Flat zone index as reported by :meth:`connect`.
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

    def resize_zone(self, zone_index: int, leds: int) -> None:
        """Resize a zone to the layout's chain length.

        ITE-style ARGB zones report 0 LEDs until resized, so the layout
        is the source of truth for channel capacity. The zone object is
        refreshed by the underlying library call.

        Args:
            zone_index: Flat zone index as reported by :meth:`connect`.
            leds: Target LED count.

        Raises:
            OpenRgbError: If not connected or the resize fails.
        """
        if self._client is None or zone_index >= len(self._zone_objects):
            raise OpenRgbError("OpenRGB is not connected")
        zone = self._zone_objects[zone_index]
        if len(zone.leds) == leds:
            return
        try:
            zone.resize(leds)
        except Exception as exc:
            raise OpenRgbError(f"Zone resize failed: {exc}") from exc
        previous = self._zones[zone_index]
        self._zones[zone_index] = ZoneInfo(
            zone_index,
            str(zone.name),
            len(zone.leds),
            previous.device_name,
            previous.device_type,
        )
        logger.info(
            "openrgb_zone_resized", zone=zone.name, leds=len(zone.leds)
        )

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
        self._devices = []
        self._zone_objects = []
        self._zones = []
