"""
File:   test_display_service_resume.py
Brief:  Unit tests for restoring scene/video playback after panel blanking.
Author: Mistress-Lukutar
Date:   2026-09-28
Version: v0.5.0
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from oled_webui.config import get_settings
from oled_webui.exceptions import TransportError
from oled_webui.scene.loader import load_scene
from oled_webui.services import display_service as display_service_module
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


def _patch_video(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Bypass ffmpeg with dummy frame files for playback.

    Args:
        monkeypatch: Patching helper.
        tmp_path: Directory receiving the dummy frame files.

    Returns:
        Path of the fake video file to play.
    """
    monkeypatch.setattr(display_service_module, "ensure_ffmpeg", lambda: None)
    frames = []
    for index in range(2):
        frame = tmp_path / f"frame{index}.jpg"
        frame.write_bytes(b"frame")
        frames.append(frame)
    monkeypatch.setattr(
        display_service_module, "extract_video_frames", lambda *args, **kwargs: frames
    )
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake video")
    return video


async def test_power_off_captures_video_config_and_power_on_restarts_it(
    service: DisplayService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blanking stops the video; waking restarts it with the same config."""
    video = _patch_video(monkeypatch, tmp_path)
    await service.play_video(video, fps=24, loop=True, rotation=90, fit="stretch")
    assert service._video_state["playing"] is True

    await service.power_off()
    assert service._video_state["playing"] is False
    assert service._resume_content == {
        "type": "video",
        "path": str(video),
        "fps": 24,
        "loop": True,
        "rotation": 90,
        "fit": "stretch",
    }

    await service.power_on()
    assert service._video_state["playing"] is True
    assert service._video_params is not None
    assert service._video_params["rotation"] == 90
    await service.stop_video()


async def test_power_off_captures_scene_and_power_on_restarts_it(
    service: DisplayService, scene_file: Path
) -> None:
    """Blanking stops the scene; waking starts it again from its document."""
    document = load_scene(scene_file)
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
    service: DisplayService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If playback cannot restart, the cached frame is restored instead."""
    await service.send_color("#112233")
    video = _patch_video(monkeypatch, tmp_path)
    await service.play_video(video, fps=10, loop=False)
    await service.power_off()
    assert service._resume_content is not None

    def missing_ffmpeg() -> None:
        raise TransportError("ffmpeg disappeared")

    monkeypatch.setattr(display_service_module, "ensure_ffmpeg", missing_ffmpeg)
    await service.power_on()

    assert service._resume_content is None
    assert service._video_state["playing"] is False
    assert service._last_content is not None
    assert service._last_content["type"] == "color"


async def test_new_content_clears_pending_resume(
    service: DisplayService, scene_file: Path
) -> None:
    """Explicit content replaces the pending resume of the stopped scene."""
    await service.start_scene(load_scene(scene_file), "demo", "Demo")
    await service.power_off()
    assert service._resume_content is not None

    await service.send_color("#445566")
    assert service._resume_content is None

    await service.power_on()
    assert service._scene_state["running"] is False
    assert service._last_content is not None
    assert service._last_content["type"] == "color"
