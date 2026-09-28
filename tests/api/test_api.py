"""
File:   test_api.py
Brief:  API smoke tests over the full FastAPI app with a fake LCD.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.3.0
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
    """Status contains device, settings, video and frame info."""
    body = client.get("/api/device/status").json()
    assert body["success"] is True
    data = body["data"]
    assert data["connected"] is True
    assert data["device"]["resolution"] == {"width": 1600, "height": 720}
    assert "settings" in data and "video" in data
    settings = data["settings"]
    assert settings["keepalive_enabled"] is False  # from OLED_KEEPALIVE_ENABLED
    assert 0 <= settings["brightness"] <= 200
    assert 1 <= settings["quality"] <= 100


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
        data={"fit": "stretch"},
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
    """Off sends a black frame; on restores the pre-blank content frame."""
    client.post("/api/frame/color", data={"color": "0000ff"})
    content_payload = sent_frames[-1]["payload"]
    assert client.post("/api/frame/off").status_code == 200
    assert client.post("/api/frame/on").status_code == 200
    assert len(sent_frames) == 3
    assert sent_frames[1]["payload"] != content_payload  # blanked to black
    assert sent_frames[2]["payload"] == content_payload  # restored


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

    from oled_webui.main import create_app

    with TestClient(create_app()) as restarted:
        settings = restarted.get("/api/device/settings").json()["data"]
        assert settings["brightness"] == 40
        assert settings["blank_on_display_off"] is True
        assert settings["quality"] == 95


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


def test_settings_change_reapplies_preset_image(
    client: TestClient, sent_frames: list[dict]
) -> None:
    """Brightness changes re-render content applied via an image preset.

    Regression: preset-applied images live in the preset assets folder,
    but the settings refresh only looked in the uploads directory and
    silently skipped the re-render (content_refresh_missing_file).
    """
    client.post(
        "/api/frame/image",
        files={"file": ("pic.png", _png_bytes(color="red"), "image/png")},
    )
    saved = client.post("/api/presets/save-current", json={"name": "Pic"})
    preset_id = saved.json()["data"]["id"]

    client.post(f"/api/presets/{preset_id}/apply")
    frames_after_apply = len(sent_frames)

    updated = client.post("/api/device/settings", json={"brightness": 40})
    assert updated.status_code == 200
    assert len(sent_frames) == frames_after_apply + 1
    assert sent_frames[-1]["payload"] != sent_frames[-2]["payload"]


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
