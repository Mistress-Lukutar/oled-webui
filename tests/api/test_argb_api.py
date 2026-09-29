"""
File:   test_argb_api.py
Brief:  API tests for ARGB status, layout, preview and engine endpoints.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.1.0
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

VALID_LAYOUT: dict[str, Any] = {
    "fps": 30,
    "brightness": 100,
    "headers": [{"id": "h1", "name": "ARGB 1", "zone_index": 0, "devices": ["d1"]}],
    "devices": [
        {
            "id": "d1",
            "name": "Strip",
            "type": "strip",
            "header_id": "h1",
            "leds": 3,
            "x": 10,
            "y": 10,
        }
    ],
    "layers": [
        {"id": "l1", "name": "Fill", "effect": {"type": "fill", "color": "#FF0000"}}
    ],
}


def test_argb_status_defaults(client: TestClient) -> None:
    """A fresh server reports a disconnected, stopped ARGB subsystem."""
    response = client.get("/api/argb/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["connected"] is False
    assert data["running"] is False
    assert data["zones"] == []


def test_argb_layout_roundtrip(client: TestClient) -> None:
    """A stored layout is returned by GET and survives re-validation."""
    response = client.put("/api/argb/layout", json=VALID_LAYOUT)
    assert response.status_code == 200
    assert response.json()["success"] is True
    stored = client.get("/api/argb/layout").json()["data"]["layout"]
    assert stored["devices"][0]["id"] == "d1"
    assert stored["layers"][0]["effect"]["type"] == "fill"


def test_argb_layout_validation_error(client: TestClient) -> None:
    """An inconsistent layout is rejected with a 422 envelope."""
    bad = {
        **VALID_LAYOUT,
        "headers": [
            {"id": "h1", "zone_index": 0, "devices": ["missing"]}
        ],
    }
    response = client.put("/api/argb/layout", json=bad)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert "unknown device" in body["error"]


def test_argb_render_preview_is_deterministic(client: TestClient) -> None:
    """Fixed-time previews render identical buffers without hardware."""
    payload = dict(VALID_LAYOUT)
    first = client.post("/api/argb/render_preview", json=payload, params={"t": 1.0})
    second = client.post("/api/argb/render_preview", json=payload, params={"t": 1.0})
    assert first.status_code == 200
    buffers = first.json()["data"]["buffers"]
    assert buffers == second.json()["data"]["buffers"]
    assert buffers["h1"] == "ff0000ff0000ff0000"


def test_argb_connect_discovers_zones(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Connecting reports the controller and syncs header zone sizes."""
    client.put("/api/argb/layout", json=VALID_LAYOUT)
    response = client.post("/api/argb/connect")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["connected"] is True
    assert data["controller"] == "Fake Motherboard"
    assert len(data["zones"]) == 2
    stored = client.get("/api/argb/layout").json()["data"]["layout"]
    assert stored["headers"][0]["size"] == 64


def test_argb_apply_sends_zone_buffers(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Applying a layout starts the engine that drives OpenRGB zones."""
    client.post("/api/argb/connect")
    layout = {
        **VALID_LAYOUT,
        "headers": [
            {
                "id": "h1",
                "name": "ARGB 1",
                "zone_index": 0,
                "size": 64,
                "devices": ["d1"],
            }
        ],
    }
    response = client.post("/api/argb/apply", json=layout)
    assert response.status_code == 200
    assert response.json()["data"]["running"] is True

    deadline = time.monotonic() + 5.0
    while not fake_openrgb and time.monotonic() < deadline:
        time.sleep(0.02)
    assert fake_openrgb, "engine never sent a zone buffer"
    frame = fake_openrgb[0]
    assert frame["zone_index"] == 0
    assert len(frame["data"]) == 64 * 3
    # Static fill: only the first tick sends, subsequent ticks are skipped.
    stable = len(fake_openrgb)
    time.sleep(0.15)
    assert len(fake_openrgb) <= stable + 1

    stopped = client.post("/api/argb/stop").json()["data"]
    assert stopped["running"] is False


def test_argb_apply_without_connection_still_runs(client: TestClient) -> None:
    """The engine runs headless; sends simply do not happen."""
    response = client.post("/api/argb/apply", json=VALID_LAYOUT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["running"] is True
    assert data["connected"] is False
    stopped = client.post("/api/argb/stop").json()["data"]
    assert stopped["running"] is False


def test_argb_disconnect_stops_engine(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Disconnecting stops the engine and closes the session."""
    client.post("/api/argb/connect")
    client.post("/api/argb/apply", json=VALID_LAYOUT)
    data = client.post("/api/argb/disconnect").json()["data"]
    assert data["connected"] is False
    assert data["running"] is False
