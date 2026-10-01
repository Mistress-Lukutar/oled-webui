"""
File:   test_scene_service.py
Brief:  Unit tests for file-backed scene storage.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from luminaflowui.config import Settings
from luminaflowui.exceptions import SceneError, SceneNotFoundError
from luminaflowui.services.scene_service import SceneService

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path: Path) -> SceneService:
    """Scene service rooted in a temp data directory."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    return SceneService(settings)


def test_create_list_and_delete_scene(service: SceneService) -> None:
    meta = service.create_scene("Test", "screen: {}\n")
    assert meta.widget_count == 0

    listed = service.list_scenes()
    assert [item.id for item in listed] == [meta.id]

    assert service.read_yaml(meta.id) == "screen: {}\n"

    service.delete_scene(meta.id)
    assert service.list_scenes() == []
    with pytest.raises(SceneNotFoundError):
        service.read_yaml(meta.id)


def test_save_yaml_validates(service: SceneService) -> None:
    meta = service.create_scene("Test")
    with pytest.raises(SceneError):
        service.save_yaml(meta.id, "bogus_setting: true\n")

    updated = service.save_yaml(meta.id, "screen:\n  refresh: 5.0\n")
    assert updated.widget_count == 0
    assert "refresh: 5.0" in service.read_yaml(meta.id)


def test_create_scene_template_validates(service: SceneService) -> None:
    """The starter template must pass validation out of the box."""
    meta = service.create_scene("Template")
    document = service.load_document(meta.id)
    assert document.screen is not None
    assert len(document.screen.widgets) == 2


def test_asset_crud_and_safe_names(service: SceneService) -> None:
    meta = service.create_scene("Assets", "screen: {}\n")
    stream = io.BytesIO(b"png")
    stored = service.add_assets(meta.id, [("../evil.png", stream)])
    # Path traversal is normalized away; the name stays a flat file name.
    assert stored == ["evil.png"]
    assert service.list_assets(meta.id) == ["evil.png"]

    service.delete_asset(meta.id, "evil.png")
    assert service.list_assets(meta.id) == []

    with pytest.raises(SceneNotFoundError):
        service.delete_asset(meta.id, "missing.png")


def test_seed_example_from_repo(service: SceneService) -> None:
    example = PROJECT_ROOT / "examples" / "scenes" / "dashboard"
    meta = service.seed_example(example)
    document = service.load_document(meta.id)
    assert document.screen is not None
    assert len(document.screen.widgets) >= 5
    assert (service._scene_dir(meta.id) / "components" / "ring-counter.yaml").is_file()
