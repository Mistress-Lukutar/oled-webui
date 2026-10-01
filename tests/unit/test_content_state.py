"""
File:   test_content_state.py
Brief:  Unit tests for the persisted last-screen snapshot.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from luminaflowui.argb.service import ArgbService
from luminaflowui.config import Settings
from luminaflowui.services.content_state import (
    content_state_path,
    load_content_state,
    restore_last_content,
    save_content_state,
)
from luminaflowui.services.display_service import DisplayService
from luminaflowui.services.event_bus import EventBus
from luminaflowui.services.scene_runtime import SceneRuntime
from luminaflowui.services.scene_service import SceneService


def _snapshot(content_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal content snapshot as recorded by DisplayService."""
    return {"type": content_type, "params": {}, "payload": payload}


async def _connected_display(settings: Settings) -> DisplayService:
    """Create a DisplayService and connect it to the fake LCD."""
    display = DisplayService(settings, EventBus())
    await display.connect()
    return display


def _runtime(
    settings: Settings, display: DisplayService, scenes: SceneService
) -> SceneRuntime:
    """Build a scene runtime over the given services."""
    return SceneRuntime(scenes, display, ArgbService(settings, EventBus()))


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    """A saved snapshot loads back unchanged."""
    path = tmp_path / "data" / "last_content.json"
    content = _snapshot("color", {"color": "ff0000"})

    save_content_state(path, content)

    assert load_content_state(path) == content


def test_load_missing_returns_none(tmp_path: Path) -> None:
    """A missing file loads as None."""
    assert load_content_state(tmp_path / "data" / "last_content.json") is None


def test_load_corrupt_returns_none(tmp_path: Path) -> None:
    """A corrupt file loads as None instead of raising."""
    path = tmp_path / "data" / "last_content.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert load_content_state(path) is None


def test_save_none_removes_file(tmp_path: Path) -> None:
    """Saving None deletes the persisted snapshot."""
    path = tmp_path / "data" / "last_content.json"
    save_content_state(path, _snapshot("color", {"color": "ff0000"}))

    save_content_state(path, None)

    assert not path.exists()


async def test_restore_legacy_snapshot_returns_false(
    tmp_path: Path, fake_lcd: list
) -> None:
    """Snapshots of removed content types are ignored, not restored."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    save_content_state(
        content_state_path(settings), _snapshot("color", {"color": "ff0000"})
    )
    display = await _connected_display(settings)
    scenes = SceneService(settings)

    restored = await restore_last_content(
        _runtime(settings, display, scenes), scenes, settings
    )
    state = display.status()["scene"]
    await display.shutdown()

    assert restored is False
    assert state["running"] is False


async def test_restore_scene_restarts_scene(tmp_path: Path, fake_lcd: list) -> None:
    """A persisted scene snapshot is restarted from its YAML source."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    scenes = SceneService(settings)
    meta = scenes.create_scene("Dash")
    save_content_state(
        content_state_path(settings),
        {
            "type": "scene",
            "params": {},
            "payload": {"scene_id": meta.id, "name": meta.name},
        },
    )
    display = await _connected_display(settings)

    restored = await restore_last_content(
        _runtime(settings, display, scenes), scenes, settings
    )
    state = display.status()["scene"]
    await display.shutdown()

    assert restored is True
    assert state["running"] is True
    assert state["scene_id"] == meta.id


async def test_restore_missing_scene_returns_false(
    tmp_path: Path, fake_lcd: list
) -> None:
    """A snapshot pointing to a deleted scene restores nothing."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    save_content_state(
        content_state_path(settings),
        _snapshot("scene", {"scene_id": "nope", "name": "gone"}),
    )
    display = await _connected_display(settings)
    scenes = SceneService(settings)

    restored = await restore_last_content(
        _runtime(settings, display, scenes), scenes, settings
    )
    await display.shutdown()

    assert restored is False


async def test_restore_without_snapshot_returns_false(
    tmp_path: Path, fake_lcd: list
) -> None:
    """No persisted snapshot means nothing to restore."""
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    display = await _connected_display(settings)
    scenes = SceneService(settings)

    restored = await restore_last_content(
        _runtime(settings, display, scenes), scenes, settings
    )
    await display.shutdown()

    assert restored is False
