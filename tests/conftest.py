"""
File:   conftest.py
Brief:  Shared pytest fixtures: isolated settings, fake LCD, API client.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from luminaflowui.core.models import HandshakeResult, Resolution
from luminaflowui.services import bulk_device


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point settings at a temp data dir and disable auto-connect."""
    monkeypatch.setenv("LUMINA_AUTO_CONNECT", "false")
    monkeypatch.setenv("LUMINA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LUMINA_KEEPALIVE_ENABLED", "false")
    from luminaflowui.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sent_frames(fake_lcd: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alias for the recorded frames list (readability in tests)."""
    return fake_lcd


@pytest.fixture
def fake_lcd(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch BulkLcd with a fake that records sent frames.

    Returns:
        List that accumulates one dict per sent frame.
    """
    sent: list[dict[str, Any]] = []

    def fake_connect(self: bulk_device.BulkLcd) -> HandshakeResult:
        return HandshakeResult(
            vid=0x87AD,
            pid=0x70DB,
            pm=63,
            sub=0,
            resolution=Resolution(width=1600, height=720),
        )

    def fake_send(
        self: bulk_device.BulkLcd,
        payload: bytes,
        width: int,
        height: int,
        cmd: int = 2,
    ) -> int:
        sent.append({"payload": payload, "width": width, "height": height, "cmd": cmd})
        return len(payload) + 64

    monkeypatch.setattr(bulk_device.BulkLcd, "connect", fake_connect)
    monkeypatch.setattr(bulk_device.BulkLcd, "send", fake_send)
    monkeypatch.setattr(bulk_device.BulkLcd, "disconnect", lambda self: None)
    monkeypatch.setattr(
        bulk_device.BulkLcd, "is_connected", property(lambda self: True)
    )
    return sent


@pytest.fixture
def fake_openrgb(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch OpenRgbClient with a fake that records zone sends.

    Returns:
        List that accumulates one dict per sent zone buffer.
    """
    from luminaflowui.infrastructure import openrgb_transport

    sent: list[dict[str, Any]] = []

    def fake_connect(self: openrgb_transport.OpenRgbClient) -> list:
        self._fake_zones = [  # type: ignore[attr-defined]
            openrgb_transport.ZoneInfo(0, "D_LED1", 64),
            openrgb_transport.ZoneInfo(1, "D_LED2", 64),
        ]
        return list(self._fake_zones)  # type: ignore[attr-defined]

    def fake_list_zones(self: openrgb_transport.OpenRgbClient) -> list:
        return list(getattr(self, "_fake_zones", []))

    def fake_send_zone(
        self: openrgb_transport.OpenRgbClient, zone_index: int, data: bytes
    ) -> None:
        zones = getattr(self, "_fake_zones", [])
        if not zones or zone_index >= len(zones):
            from luminaflowui.exceptions import OpenRgbError

            raise OpenRgbError("OpenRGB is not connected")
        if len(data) != zones[zone_index].leds * 3:
            from luminaflowui.exceptions import OpenRgbError

            raise OpenRgbError("Zone buffer size mismatch")
        sent.append({"zone_index": zone_index, "data": data})

    def fake_disconnect(self: openrgb_transport.OpenRgbClient) -> None:
        self._fake_zones = []  # type: ignore[attr-defined]

    def fake_resize_zone(
        self: openrgb_transport.OpenRgbClient, zone_index: int, leds: int
    ) -> None:
        zones = getattr(self, "_fake_zones", [])
        if not zones or zone_index >= len(zones):
            from luminaflowui.exceptions import OpenRgbError

            raise OpenRgbError("OpenRGB is not connected")
        zones[zone_index] = openrgb_transport.ZoneInfo(
            zone_index, zones[zone_index].name, leds
        )

    monkeypatch.setattr(openrgb_transport.OpenRgbClient, "connect", fake_connect)
    monkeypatch.setattr(openrgb_transport.OpenRgbClient, "list_zones", fake_list_zones)
    monkeypatch.setattr(openrgb_transport.OpenRgbClient, "send_zone", fake_send_zone)
    monkeypatch.setattr(
        openrgb_transport.OpenRgbClient, "resize_zone", fake_resize_zone
    )
    monkeypatch.setattr(
        openrgb_transport.OpenRgbClient, "disconnect", fake_disconnect
    )
    monkeypatch.setattr(
        openrgb_transport.OpenRgbClient,
        "is_connected",
        property(lambda self: bool(getattr(self, "_fake_zones", []))),
    )
    monkeypatch.setattr(
        openrgb_transport.OpenRgbClient,
        "controller_name",
        lambda self: "Fake Motherboard" if fake_list_zones(self) else None,
    )
    return sent


@pytest.fixture
def client(fake_lcd: list[dict[str, Any]]) -> Iterator[TestClient]:
    """TestClient with a fresh app and connected display."""
    from luminaflowui.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        response = test_client.post("/api/device/connect")
        assert response.status_code == 200
        yield test_client
