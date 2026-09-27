"""
File:   test_scenes_api.py
Brief:  API tests for the scene CRUD, preview and status endpoints.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

VALID_YAML = """\
widgets:
  - type: text
    value: "hello"
    rect: [10, 10, 200, 60]
"""


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """App client with a temp data dir and hardware autostart disabled."""
    monkeypatch.setenv("OLED_DATA_DIR", str(tmp_path / "data"))  # type: ignore[operator]
    monkeypatch.setenv("OLED_AUTO_CONNECT", "false")
    from oled_webui.config import get_settings

    get_settings.cache_clear()
    from oled_webui.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def _create_scene(client: TestClient, name: str = "Demo") -> str:
    response = client.post("/api/scenes", data={"name": name})
    assert response.status_code == 200, response.text
    scene_id = response.json()["data"]["scene"]["id"]
    assert scene_id
    return scene_id


def test_scene_crud_roundtrip(client: TestClient) -> None:
    scene_id = _create_scene(client)

    listed = client.get("/api/scenes").json()["data"]["scenes"]
    assert [item["id"] for item in listed] == [scene_id]

    saved = client.put(
        f"/api/scenes/{scene_id}", json={"yaml": VALID_YAML, "name": "Renamed"}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["scene"]["widget_count"] == 1

    detail = client.get(f"/api/scenes/{scene_id}").json()["data"]
    assert detail["yaml"] == VALID_YAML
    assert detail["scene"]["name"] == "Renamed"

    assert client.delete(f"/api/scenes/{scene_id}").status_code == 200
    assert client.get(f"/api/scenes/{scene_id}").status_code == 404


def test_save_invalid_yaml_returns_422(client: TestClient) -> None:
    scene_id = _create_scene(client)
    response = client.put(
        f"/api/scenes/{scene_id}", json={"yaml": "bogus_setting: true\n"}
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_preview_renders_jpeg(client: TestClient) -> None:
    scene_id = _create_scene(client)
    client.put(f"/api/scenes/{scene_id}", json={"yaml": VALID_YAML})

    response = client.post(f"/api/scenes/{scene_id}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"

    yaml_response = client.post(
        "/api/scenes/preview",
        files={"file": ("edit.yaml", VALID_YAML.encode("utf-8"), "application/yaml")},
        data={"scene_id": scene_id},
    )
    assert yaml_response.status_code == 200
    assert yaml_response.content[:2] == b"\xff\xd8"


def test_apply_requires_connection(client: TestClient) -> None:
    scene_id = _create_scene(client)
    client.put(f"/api/scenes/{scene_id}", json={"yaml": VALID_YAML})
    response = client.post(f"/api/scenes/{scene_id}/apply")
    assert response.status_code == 409


def test_asset_serving(client: TestClient) -> None:
    scene_id = _create_scene(client)
    upload = client.post(
        f"/api/scenes/{scene_id}/assets",
        files=[("files", ("mascot.png", b"\x89PNG-fake-bytes", "image/png"))],
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["data"]["assets"] == ["mascot.png"]

    served = client.get(f"/api/scenes/{scene_id}/assets/mascot.png")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == b"\x89PNG-fake-bytes"

    assert (
        client.get(f"/api/scenes/{scene_id}/assets/missing.png").status_code == 404
    )
    assert (
        client.get(f"/api/scenes/{scene_id}/assets/../../scene.yaml").status_code
        == 422
    )


def test_detail_includes_components(client: TestClient) -> None:
    response = client.post("/api/scenes/seed-example")
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert "ring-counter" in detail["components"]
    assert "params:" in detail["components"]["ring-counter"]
    assert "render:" in detail["components"]["ring-counter"]


def test_seed_example_and_status_shape(client: TestClient) -> None:
    response = client.post("/api/scenes/seed-example")
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert len(detail["yaml"]) > 100
    assert "ring-counter" in detail["assets"] or detail["assets"] == []

    status = client.get("/api/device/status").json()["data"]
    assert "scene" in status
    assert status["scene"]["running"] is False
