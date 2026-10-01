"""
File:   test_api.py
Brief:  API smoke tests over the full FastAPI app with a fake LCD.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

STATIC_SCENE_YAML = """\
screen:
  widgets:
    - type: text
      value: "Hello"
      rect: [10, 10, 200, 60]
"""


def _wait_for_frames(sent_frames: list[dict], count: int, timeout: float = 5.0) -> None:
    """Block until the fake LCD has recorded at least `count` frames."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(sent_frames) >= count:
            return
        time.sleep(0.02)
    pytest.fail(f"expected {count} frames, got {len(sent_frames)}")


def _apply_scene(client: TestClient, yaml: str = STATIC_SCENE_YAML) -> str:
    """Create a scene, store the given YAML and apply it to the display."""
    created = client.post("/api/scenes", data={"name": "Demo"})
    assert created.status_code == 200, created.text
    scene_id = created.json()["data"]["scene"]["id"]
    saved = client.put(f"/api/scenes/{scene_id}", json={"yaml": yaml, "name": "Demo"})
    assert saved.status_code == 200, saved.text
    applied = client.post(f"/api/scenes/{scene_id}/apply")
    assert applied.status_code == 200, applied.text
    return scene_id


def test_health(client: TestClient) -> None:
    """Health endpoint reports connectivity state."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["connected"] is True


def test_status_shape(client: TestClient) -> None:
    """Status contains device, settings, scene and frame info."""
    body = client.get("/api/device/status").json()
    assert body["success"] is True
    data = body["data"]
    assert data["connected"] is True
    assert data["device"]["resolution"] == {"width": 1600, "height": 720}
    assert "settings" in data and "scene" in data
    settings = data["settings"]
    assert settings["keepalive_enabled"] is False  # from LUMINA_KEEPALIVE_ENABLED
    assert 0 <= settings["brightness"] <= 200
    assert 1 <= settings["quality"] <= 100


def test_apply_scene_sends_frame(client: TestClient, sent_frames: list[dict]) -> None:
    """An applied scene renders through the pipeline and reaches the LCD."""
    scene_id = _apply_scene(client)
    _wait_for_frames(sent_frames, 1)
    frame = sent_frames[0]
    assert (frame["width"], frame["height"]) == (1600, 720)
    assert frame["payload"][:2] == b"\xff\xd8"  # JPEG SOI

    stopped = client.post("/api/scenes/stop")
    assert stopped.status_code == 200
    assert stopped.json()["data"]["running"] is False


def test_display_settings_roundtrip(client: TestClient) -> None:
    """Settings can be read and updated; omitted fields keep their value."""
    current = client.get("/api/device/settings").json()["data"]
    assert current["quality"] == 95

    updated = client.post("/api/device/settings", json={"brightness": 40})
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["brightness"] == 40
    assert data["quality"] == 95  # untouched
    assert data["keepalive_enabled"] == current["keepalive_enabled"]

    status = client.get("/api/device/status").json()["data"]
    assert status["settings"]["brightness"] == 40


def test_display_settings_validation(client: TestClient) -> None:
    """Out-of-range settings are rejected with 422."""
    response = client.post("/api/device/settings", json={"brightness": 999})
    assert response.status_code == 422
    response = client.post("/api/device/settings", json={"quality": 0})
    assert response.status_code == 422
    response = client.post("/api/device/settings", json={"keepalive_interval": 0.01})
    assert response.status_code == 422


def test_display_settings_persist_across_restart(client: TestClient) -> None:
    """Saved settings survive a full app restart in the same data dir."""
    client.post(
        "/api/device/settings",
        json={"brightness": 40, "blank_on_display_off": True},
    )

    from luminaflowui.main import create_app

    with TestClient(create_app()) as restarted:
        settings = restarted.get("/api/device/settings").json()["data"]
        assert settings["brightness"] == 40
        assert settings["blank_on_display_off"] is True
        assert settings["quality"] == 95


def test_preview_returns_jpeg(client: TestClient, sent_frames: list[dict]) -> None:
    """Preview streams the last sent frame as JPEG."""
    _apply_scene(client)
    _wait_for_frames(sent_frames, 1)
    response = client.get("/api/frame/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_font_library_upload_serve_delete(client: TestClient) -> None:
    """Shared font library round-trips: upload, list, serve, delete."""
    response = client.post(
        "/api/frame/fonts",
        files={"files": ("Demo Font.ttf", b"font-bytes", "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["data"]["fonts"] == ["Demo_Font.ttf"]

    served = client.get("/api/frame/fonts/Demo_Font.ttf")
    assert served.status_code == 200
    assert served.content == b"font-bytes"

    deleted = client.delete("/api/frame/fonts/Demo_Font.ttf")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["fonts"] == []
    assert client.get("/api/frame/fonts/Demo_Font.ttf").status_code == 404


def test_font_upload_rejects_bad_extension(client: TestClient) -> None:
    """Only TTF/OTF files may enter the font library."""
    response = client.post(
        "/api/frame/fonts",
        files={"files": ("payload.exe", b"x", "application/octet-stream")},
    )
    assert response.status_code == 422


def test_font_upload_uniquifies_collisions(client: TestClient) -> None:
    """Re-uploading the same name stores a numbered copy, not an overwrite."""
    for _ in range(2):
        response = client.post(
            "/api/frame/fonts",
            files={"files": ("Same.ttf", b"x", "application/octet-stream")},
        )
        assert response.status_code == 200
    assert client.get("/api/frame/fonts").json()["data"]["fonts"] == [
        "Same-1.ttf",
        "Same.ttf",
    ]
