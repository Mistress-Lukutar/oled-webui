"""
File:   test_display_service_resume.py
Brief:  Unit tests for restoring scene playback after panel blanking.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from oled_webui.config import get_settings
from oled_webui.exceptions import OledWebUIError
from oled_webui.scene.loader import load_scene
from oled_webui.scene.schema import ScreenDocument
from oled_webui.services.display_service import DisplayService
from oled_webui.services.event_bus import EventBus


@pytest.fixture
async def service(fake_lcd: list[dict[str, Any]]) -> AsyncIterator[DisplayService]:
    """Connected display service backed by the fake LCD."""
    display = DisplayService(get_settings(), EventBus())
    await display.connect()
    yield display
    await display.shutdown()


@pytest.fixture
def scene_file(tmp_path: Path) -> Path:
    """Minimal scene YAML exercising the standard sources."""
    path = tmp_path / "scene.yaml"
    path.write_text(
        """
        screen:
          refresh: 10.0
          max_fps: 30
          widgets:
            - type: text
              source: time.hms
              rect: [20, 20, 160, 40]
        """,
        encoding="utf-8",
    )
    return path


def _load_screen(path: Path) -> ScreenDocument:
    """Load a scene file and unwrap its screen section."""
    document = load_scene(path)
    assert document.screen is not None
    return document.screen


async def test_power_off_captures_scene_and_power_on_restarts_it(
    service: DisplayService, scene_file: Path
) -> None:
    """Blanking stops the scene; waking starts it again from its document."""
    document = _load_screen(scene_file)
    await service.start_scene(document, "demo", "Demo")
    assert service._scene_state["running"] is True

    await service.power_off()
    assert service._scene_state["running"] is False
    assert service._resume_content is not None
    assert service._resume_content["type"] == "scene"
    assert service._resume_content["scene_id"] == "demo"
    assert service._resume_content["name"] == "Demo"
    assert service._resume_content["document"] is document

    await service.power_on()
    assert service._scene_state["running"] is True
    assert service._scene_state["scene_id"] == "demo"
    await service.stop_scene()


async def test_power_on_falls_back_to_static_frame_when_resume_fails(
    service: DisplayService, scene_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the scene cannot restart, the cached frame is restored instead."""
    await service.start_scene(_load_screen(scene_file), "demo", "Demo")
    await service.power_off()
    assert service._resume_content is not None

    def broken_restart(*_args: Any, **_kwargs: Any) -> None:
        raise OledWebUIError("scene source vanished")

    monkeypatch.setattr(service, "start_scene", broken_restart)
    await service.power_on()

    assert service._resume_content is None
    assert service._last_content is not None
    assert service._last_content["type"] == "color"  # transient blank record


async def test_new_scene_clears_pending_resume(
    service: DisplayService, scene_file: Path
) -> None:
    """Explicit content replaces the pending resume of the stopped scene."""
    await service.start_scene(_load_screen(scene_file), "demo", "Demo")
    await service.power_off()
    assert service._resume_content is not None

    await service.start_scene(_load_screen(scene_file), "other", "Other")
    assert service._resume_content is None

    await service.power_on()
    assert service._scene_state["running"] is True
    assert service._scene_state["scene_id"] == "other"
    await service.stop_scene()
