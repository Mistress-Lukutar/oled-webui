"""
File:   video_player.py
Brief:  ffmpeg-backed video frame decoding for display streaming.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import structlog
from PIL import Image

from oled_webui.exceptions import VideoError

logger = structlog.get_logger(__name__)


def ensure_ffmpeg() -> None:
    """Verify that ffmpeg is available on PATH.

    Raises:
        VideoError: If ffmpeg is not installed.
    """
    if shutil.which("ffmpeg") is None:
        raise VideoError("ffmpeg not found in PATH")


def iter_video_frames(
    path: Path,
    width: int,
    height: int,
    stop_event: threading.Event,
) -> Iterator[Image.Image]:
    """Decode a video file into RGB frames at panel resolution.

    Scaling and letterboxing happen inside ffmpeg so Python receives exact
    panel-sized raw frames.

    Args:
        path: Video file readable by ffmpeg.
        width: Target frame width.
        height: Target frame height.
        stop_event: Set to abort decoding early.

    Yields:
        PIL RGB images of exactly ``width`` x ``height``.

    Raises:
        VideoError: If ffmpeg fails to start or decode.
    """
    frame_size = width * height * 3
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vf",
        (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise VideoError(f"Failed to start ffmpeg: {exc}") from exc

    if proc.stdout is None:
        proc.kill()
        raise VideoError("Failed to open ffmpeg stdout pipe")

    try:
        while not stop_event.is_set():
            raw_frame = proc.stdout.read(frame_size)
            if len(raw_frame) < frame_size:
                break
            yield Image.frombytes("RGB", (width, height), raw_frame)

        if proc.returncode not in (None, 0) and not stop_event.is_set():
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise VideoError(f"ffmpeg exited with {proc.returncode}: {stderr.strip()}")
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
