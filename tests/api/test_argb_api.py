"""
File:   test_argb_api.py
Brief:  API tests for ARGB status, scene-driven layouts and the library.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import time
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

# A tiny three-LED definition so previews and buffers stay small.
TINY_DEF_YAML = """\
id: tiny
name: Tiny Bar
size: [30, 4]
leds:
  - {type: rect, rect: [0, 0, 2, 2]}
  - {type: rect, rect: [10, 0, 2, 2]}
  - {type: rect, rect: [20, 0, 2, 2]}
"""


def _install_tiny(client: TestClient) -> None:
    """Install the tiny definition used by the layout fixtures."""
    response = client.post("/api/argb/devices", json={"yaml": TINY_DEF_YAML})
    assert response.status_code == 200, response.text


VALID_ARGB: dict[str, Any] = {
    "fps": 30,
    "brightness": 100,
    "headers": [{"id": "h1", "name": "ARGB 1", "zone_index": 0, "devices": ["d1"]}],
    "devices": [
        {
            "id": "d1",
            "name": "Strip",
            "device": "tiny",
            "header_id": "h1",
            "x": 10,
            "y": 10,
        }
    ],
    "layers": [
        {"id": "l1", "name": "Fill", "effect": {"type": "fill", "color": "#FF0000"}}
    ],
}


def _create_argb_scene(client: TestClient, argb: dict[str, Any]) -> str:
    """Store a scene whose only section is the given argb layout."""
    scene_yaml = yaml.safe_dump({"argb": argb}, sort_keys=False)
    created = client.post("/api/scenes", data={"name": "Lights"})
    assert created.status_code == 200, created.text
    scene_id = created.json()["data"]["scene"]["id"]
    saved = client.put(f"/api/scenes/{scene_id}", json={"yaml": scene_yaml})
    assert saved.status_code == 200, saved.text
    return scene_id


def test_argb_status_defaults(client: TestClient) -> None:
    """A fresh server reports a disconnected, stopped ARGB subsystem."""
    response = client.get("/api/argb/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["connected"] is False
    assert data["running"] is False
    assert data["zones"] == []


def test_argb_active_endpoint_defaults(client: TestClient) -> None:
    """Without an applied scene the active layout is empty and stopped."""
    response = client.get("/api/argb/active")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["running"] is False
    assert data["layout"]["headers"] == []


def test_argb_layout_roundtrip_through_scene(client: TestClient) -> None:
    """A scene's argb section validates, applies and feeds GET /active."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["devices"]["argb"] == "started"

    active = client.get("/api/argb/active").json()["data"]
    assert active["running"] is True
    assert active["layout"]["devices"][0]["id"] == "d1"
    assert active["layout"]["devices"][0]["device"] == "tiny"
    assert active["layout"]["layers"][0]["effect"]["type"] == "fill"


def test_argb_unknown_definition_fails_scene_apply(client: TestClient) -> None:
    """A layout referencing a missing definition reports a device error."""
    scene_id = _create_argb_scene(client, VALID_ARGB)
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200
    devices = applied.json()["data"]["devices"]
    assert devices["argb"].startswith("error:")


def test_argb_device_library_crud(client: TestClient) -> None:
    """Definitions can be listed, fetched, updated and deleted."""
    _install_tiny(client)
    listing = client.get("/api/argb/devices").json()["data"]["devices"]
    ids = {item["id"] for item in listing}
    assert {"strip", "ring", "dual-ring-fan", "tiny"} <= ids
    assert next(item for item in listing if item["id"] == "tiny")["leds"] == 3

    fetched = client.get("/api/argb/devices/tiny").json()["data"]
    assert "id: tiny" in fetched["yaml"]
    assert len(fetched["definition"]["leds"]) == 3

    updated = TINY_DEF_YAML.replace("name: Tiny Bar", "name: Tiny v2")
    response = client.put("/api/argb/devices/tiny", json={"yaml": updated})
    assert response.status_code == 200
    assert client.get("/api/argb/devices/tiny").json()["data"]["definition"][
        "name"
    ] == "Tiny v2"

    response = client.delete("/api/argb/devices/tiny")
    assert response.status_code == 200
    listing = client.get("/api/argb/devices").json()["data"]["devices"]
    assert "tiny" not in {item["id"] for item in listing}


def test_argb_device_used_definition_delete_rejected(client: TestClient) -> None:
    """A definition referenced by the applied layout cannot be deleted."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["devices"]["argb"] == "started"

    response = client.delete("/api/argb/devices/tiny")
    assert response.status_code == 422
    assert "d1" in response.json()["error"]


def test_argb_device_invalid_yaml_rejected(client: TestClient) -> None:
    """Broken definition YAML fails with a 422 envelope."""
    response = client.post("/api/argb/devices", json={"yaml": "id: [bad\n"})
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_argb_render_preview_is_deterministic(client: TestClient) -> None:
    """Fixed-time previews render identical buffers without hardware."""
    _install_tiny(client)
    payload = dict(VALID_ARGB)
    first = client.post("/api/argb/render_preview", json=payload, params={"t": 1.0})
    second = client.post("/api/argb/render_preview", json=payload, params={"t": 1.0})
    assert first.status_code == 200
    buffers = first.json()["data"]["buffers"]
    assert buffers == second.json()["data"]["buffers"]
    assert buffers["h1"] == "ff0000ff0000ff0000"


def test_argb_scene_apply_sends_zone_buffers(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Applying a scene starts the engine that drives OpenRGB zones."""
    _install_tiny(client)
    argb = {
        **VALID_ARGB,
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
    scene_id = _create_argb_scene(client, argb)
    response = client.post(f"/api/scenes/{scene_id}/apply")
    assert response.status_code == 200, response.text

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

    stopped = client.post("/api/scenes/stop")
    assert stopped.status_code == 200
    status = client.get("/api/argb/status").json()["data"]
    assert status["running"] is False


def test_argb_engine_self_heals_transport(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """The engine self-heals: it opens the transport on its own."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    response = client.post(f"/api/scenes/{scene_id}/apply")
    assert response.status_code == 200, response.text

    deadline = time.monotonic() + 10.0
    connected = False
    while time.monotonic() < deadline:
        connected = client.get("/api/argb/status").json()["data"]["connected"]
        if connected:
            break
        time.sleep(0.05)
    assert connected is True, "engine never recovered the OpenRGB transport"

    # The next engine tick re-renders with synced zone sizes and sends.
    deadline = time.monotonic() + 5.0
    while not fake_openrgb and time.monotonic() < deadline:
        time.sleep(0.05)
    assert fake_openrgb, "recovered engine never sent a zone buffer"

    stopped = client.post("/api/scenes/stop")
    assert stopped.status_code == 200


def test_argb_disconnect_stops_engine(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Disconnecting stops the engine and closes the session."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200, applied.text

    data = client.post("/api/argb/disconnect").json()["data"]
    assert data["connected"] is False
    assert data["running"] is False


@pytest.mark.usefixtures("fake_openrgb")
def test_argb_scene_apply_syncs_header_sizes(client: TestClient) -> None:
    """Applying adopts missing zone capacities into the runtime layout."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200, applied.text

    size: int | None = None
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        active = client.get("/api/argb/active").json()["data"]
        size = active["layout"]["headers"][0]["size"]
        if size is not None:
            break
        time.sleep(0.05)
    assert size == 64


def test_argb_settings_roundtrip(client: TestClient) -> None:
    """ARGB settings can be read and updated; omitted fields keep values."""
    data = client.get("/api/argb/settings").json()["data"]
    assert data["off_on_display_off"] is False

    updated = client.put("/api/argb/settings", json={"off_on_display_off": True})
    assert updated.status_code == 200
    assert updated.json()["data"]["off_on_display_off"] is True

    kept = client.put("/api/argb/settings", json={})
    assert kept.status_code == 200
    assert kept.json()["data"]["off_on_display_off"] is True

    # The running service echoes the stored snapshot on the next read.
    reloaded = client.get("/api/argb/settings").json()["data"]
    assert reloaded["off_on_display_off"] is True


@pytest.mark.usefixtures("fake_openrgb")
def test_argb_display_power_blanking(
    client: TestClient, fake_openrgb: list[dict[str, Any]]
) -> None:
    """Display off blanks the lighting; display on restarts the engine."""
    _install_tiny(client)
    scene_id = _create_argb_scene(client, VALID_ARGB)
    assert client.post(f"/api/scenes/{scene_id}/apply").status_code == 200
    assert (
        client.put("/api/argb/settings", json={"off_on_display_off": True}).status_code
        == 200
    )

    argb = client.app.state.argb  # type: ignore[attr-defined]
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not (argb.is_running and argb.is_connected):
        time.sleep(0.05)
    assert argb.is_running
    assert argb.is_connected

    argb.on_monitor_power(False)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and argb.is_running:
        time.sleep(0.05)
    assert argb.is_running is False
    last_zone0 = [f for f in fake_openrgb if f["zone_index"] == 0][-1]
    assert set(last_zone0["data"]) == {0}  # blacked out

    argb.on_monitor_power(True)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not argb.is_running:
        time.sleep(0.05)
    assert argb.is_running is True
