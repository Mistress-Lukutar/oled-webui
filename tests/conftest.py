"""
File:   conftest.py
Brief:  Shared pytest fixtures: isolated settings, fake LCD, API client.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oled_webui.core.models import HandshakeResult, Resolution
from oled_webui.services import bulk_device


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point settings at a temp data dir and disable auto-connect."""
    monkeypatch.setenv("OLED_AUTO_CONNECT", "false")
    monkeypatch.setenv("OLED_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OLED_KEEPALIVE_ENABLED", "false")
    from oled_webui.config import get_settings

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
def client(fake_lcd: list[dict[str, Any]]) -> Iterator[TestClient]:
    """TestClient with a fresh app and connected display."""
    from oled_webui.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        response = test_client.post("/api/device/connect")
        assert response.status_code == 200
        yield test_client
