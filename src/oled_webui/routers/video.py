"""
File:   video.py
Brief:  Video upload, playback control and status endpoints.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile

from oled_webui.dependencies import ConnectedDisplayDep, SettingsDep
from oled_webui.exceptions import ValidationError
from oled_webui.models.schemas import StatusResponse

router = APIRouter(prefix="/api/video", tags=["video"])

ALLOWED_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".avi", ".mkv", ".mov", ".webm", ".gif"}
)


@router.post("", response_model=StatusResponse)
async def start_video(
    display: ConnectedDisplayDep,
    settings: SettingsDep,
    file: UploadFile,
    fps: int = Form(default=30, ge=1, le=60),
    loop: bool = Form(default=False),
    rotation: int = Form(default=0),
    brightness: int = Form(default=100, ge=0, le=200),
    fit: str = Form(default="contain"),
    quality: int = Form(default=95, ge=1, le=100),
) -> StatusResponse:
    """Upload a video and start streaming it to the display."""
    original = Path(file.filename or "")
    suffix = original.suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValidationError(f"Unsupported video extension: {suffix or '(none)'}")
    stem = original.stem or "video"
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:60]
    dest = settings.uploads_dir / f"{uuid.uuid4().hex[:8]}_{safe_stem}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    await display.play_video(
        dest,
        fps=fps,
        loop=loop,
        rotation=rotation,
        brightness=brightness,
        fit=fit,
        quality=quality,
    )
    return StatusResponse(data=display.status()["video"])


@router.post("/stop", response_model=StatusResponse)
async def stop_video(display: ConnectedDisplayDep) -> StatusResponse:
    """Stop the running video playback."""
    await display.stop_video()
    return StatusResponse(data=display.status()["video"])


@router.get("/status", response_model=StatusResponse)
async def video_status(display: ConnectedDisplayDep) -> StatusResponse:
    """Return the current video playback state."""
    return StatusResponse(data=display.status()["video"])
