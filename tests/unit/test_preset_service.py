"""
File:   test_preset_service.py
Brief:  Unit tests for file-backed preset storage.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from oled_webui.config import Settings
from oled_webui.exceptions import PresetNotFoundError, ValidationError
from oled_webui.services.preset_service import PresetService


@pytest.fixture
def service(tmp_path: Path) -> PresetService:
    """Preset service rooted in a temp data directory."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    return PresetService(settings)


def test_save_and_list_color_preset(service: PresetService) -> None:
    """Color presets persist as JSON and round-trip."""
    preset = service.save_from_content(
        "Red",
        {"type": "color", "params": {"brightness": 80}, "payload": {"color": "ff0000"}},
    )
    listed = service.list_presets()
    assert len(listed) == 1
    assert listed[0].name == "Red"
    assert listed[0].payload["color"] == "ff0000"
    assert listed[0].has_asset is False
    assert preset.id


def test_save_image_preset_copies_asset(service: PresetService, tmp_path: Path) -> None:
    """Image presets copy the referenced upload into the assets directory."""
    uploads = service.assets_dir.parent.parent / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    source = uploads / "photo.png"
    Image.new("RGB", (10, 10), (0, 255, 0)).save(source)

    content = {
        "type": "image",
        "params": {"rotation": 0, "brightness": 100, "fit": "contain", "quality": 95},
        "payload": {"file": "photo.png"},
    }
    preset = service.save_from_content("Photo", content)

    assert preset.has_asset is True
    asset = service.asset_path(preset)
    assert asset is not None and asset.is_file()
    assert asset.parent == service.assets_dir


def test_save_image_preset_missing_source(service: PresetService) -> None:
    """Saving an image preset without its upload fails cleanly."""
    content = {"type": "image", "params": {}, "payload": {"file": "gone.png"}}
    with pytest.raises(ValidationError):
        service.save_from_content("Gone", content)


def test_save_empty_content_rejected(service: PresetService) -> None:
    """Saving with no applied content raises ValidationError."""
    with pytest.raises(ValidationError):
        service.save_from_content("Empty", {})


def test_get_and_delete_preset(service: PresetService, tmp_path: Path) -> None:
    """Deleting removes both the JSON file and the asset."""
    uploads = service.assets_dir.parent.parent / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    source = uploads / "img.jpg"
    Image.new("RGB", (8, 8)).save(source)
    preset = service.save_from_content(
        "Img", {"type": "image", "params": {}, "payload": {"file": "img.jpg"}}
    )

    fetched = service.get_preset(preset.id)
    assert fetched.name == "Img"

    service.delete_preset(preset.id)
    with pytest.raises(PresetNotFoundError):
        service.get_preset(preset.id)
    assert service.list_presets() == []
    assert list(service.assets_dir.glob(f"{preset.id}.*")) == []


def test_invalid_preset_id_rejected(service: PresetService) -> None:
    """Path traversal in preset ids is rejected."""
    with pytest.raises(ValidationError):
        service.get_preset("../evil")
