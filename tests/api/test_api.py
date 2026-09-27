"""
File:   test_api.py
Brief:  API smoke tests over the full FastAPI app with a fake LCD.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image


def _png_bytes(size: tuple[int, int] = (64, 32), color: str = "blue") -> bytes:
    """Build a small in-memory PNG for upload tests."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_health(client: TestClient) -> None:
    """Health endpoint reports connectivity state."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["connected"] is True


def test_status_shape(client: TestClient) -> None:
    """Status contains device, keepalive, video and frame info."""
    body = client.get("/api/device/status").json()
    assert body["success"] is True
    data = body["data"]
    assert data["connected"] is True
    assert data["device"]["resolution"] == {"width": 1600, "height": 720}
    assert "keepalive" in data and "video" in data


def test_connect_without_hardware_409(client: TestClient) -> None:
    """Frame ops fail with 409 when the display is disconnected."""
    client.post("/api/device/disconnect")
    response = client.post("/api/frame/color", data={"color": "ff0000"})
    assert response.status_code == 409
    assert response.json()["success"] is False


def test_send_color(client: TestClient, sent_frames: list[dict]) -> None:
    """Solid color frames reach the fake LCD at panel resolution."""
    response = client.post("/api/frame/color", data={"color": "#ff0000"})
    assert response.status_code == 200
    assert len(sent_frames) == 1
    frame = sent_frames[0]
    assert (frame["width"], frame["height"]) == (1600, 720)
    assert frame["payload"][:2] == b"\xff\xd8"  # JPEG SOI


def test_send_color_invalid(client: TestClient) -> None:
    """Malformed color values are rejected with 422."""
    response = client.post("/api/frame/color", data={"color": "nothex"})
    assert response.status_code == 422


def test_send_image_upload(client: TestClient, sent_frames: list[dict]) -> None:
    """Uploaded images are stored, rendered and sent."""
    response = client.post(
        "/api/frame/image",
        files={"file": ("test.png", _png_bytes(), "image/png")},
        data={"brightness": "120", "fit": "stretch"},
    )
    assert response.status_code == 200
    assert len(sent_frames) == 1
    data = response.json()["data"]
    assert data["width"] == 1600


def test_send_text(client: TestClient, sent_frames: list[dict]) -> None:
    """Text requests render through the pipeline and send."""
    response = client.post(
        "/api/frame/text",
        json={"text": "Hello, OLED!", "font_size": 32, "color": "00ff00"},
    )
    assert response.status_code == 200
    assert len(sent_frames) == 1


def test_off_on(client: TestClient, sent_frames: list[dict]) -> None:
    """Off sends a black frame; on re-sends the cached frame."""
    client.post("/api/frame/color", data={"color": "0000ff"})
    before = len(sent_frames)
    assert client.post("/api/frame/off").status_code == 200
    assert client.post("/api/frame/on").status_code == 200
    assert len(sent_frames) == before + 2


def test_preview_returns_jpeg(client: TestClient) -> None:
    """Preview streams the last sent frame as JPEG."""
    client.post("/api/frame/color", data={"color": "00ff00"})
    response = client.get("/api/frame/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"


def test_preset_flow(client: TestClient) -> None:
    """Save current content as preset, list, apply, delete."""
    client.post("/api/frame/color", data={"color": "ff00ff"})

    saved = client.post("/api/presets/save-current", json={"name": "Magenta"})
    assert saved.status_code == 200
    preset_id = saved.json()["data"]["id"]

    listed = client.get("/api/presets").json()["data"]["presets"]
    assert len(listed) == 1 and listed[0]["name"] == "Magenta"

    applied = client.post(f"/api/presets/{preset_id}/apply")
    assert applied.status_code == 200

    deleted = client.delete(f"/api/presets/{preset_id}")
    assert deleted.status_code == 200
    assert client.get("/api/presets").json()["data"]["presets"] == []


def test_preset_not_found(client: TestClient) -> None:
    """Unknown preset ids return 404 with the error envelope."""
    response = client.post("/api/presets/deadbeef/apply")
    assert response.status_code == 404
    assert response.json()["success"] is False


def test_image_preset_roundtrip(client: TestClient) -> None:
    """An uploaded image preset re-applies from the stored asset."""
    client.post(
        "/api/frame/image",
        files={"file": ("pic.png", _png_bytes(color="red"), "image/png")},
    )
    saved = client.post("/api/presets/save-current", json={"name": "Pic"})
    preset_id = saved.json()["data"]["id"]
    assert saved.json()["data"]["has_asset"] is True

    applied = client.post(f"/api/presets/{preset_id}/apply")
    assert applied.status_code == 200
