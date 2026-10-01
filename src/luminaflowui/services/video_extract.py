"""
File:   video_extract.py
Brief:  ffmpeg-backed video frame extraction (shared by the scene video widget).
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import structlog

from luminaflowui.core.constants import (
    DEFAULT_BASE_ROTATION,
    FIT_CONTAIN,
    FIT_HEIGHT,
    FIT_STRETCH,
    FIT_WIDTH,
)
from luminaflowui.exceptions import VideoError
from luminaflowui.services.frame_builder import brightness_scale

logger = structlog.get_logger(__name__)

_FRAME_PATTERN = "frame_%06d.jpg"

# JPEG quality 1-100 mapped onto ffmpeg's qscale 2 (best) - 31 (worst).
_QSCALE_MIN = 2
_QSCALE_MAX = 31


def ensure_ffmpeg() -> None:
    """Verify that ffmpeg is available on PATH.

    Raises:
        VideoError: If ffmpeg is not installed.
    """
    if shutil.which("ffmpeg") is None:
        raise VideoError("ffmpeg not found in PATH")


def quality_to_qscale(quality: int) -> int:
    """Map a 1-100 JPEG quality onto ffmpeg's inverse qscale range.

    Args:
        quality: JPEG quality 1-100 (higher is better).

    Returns:
        ffmpeg ``-qscale:v`` value, 2 (best) to 31 (worst).
    """
    span = _QSCALE_MAX - _QSCALE_MIN
    qscale = _QSCALE_MIN + round((100 - quality) * span / 100)
    return max(_QSCALE_MIN, min(_QSCALE_MAX, qscale))


def build_fit_filter(fit: str, width: int, height: int) -> str:
    """Build the ffmpeg filter that fits content into the panel canvas.

    Mirrors the image pipeline fit modes: contain letterboxes, stretch
    distorts, width/height fill and center-crop the overflow.

    Args:
        fit: One of contain, stretch, width, height.
        width: Panel width.
        height: Panel height.

    Returns:
        ffmpeg filter chain fragment.

    Raises:
        VideoError: If the fit mode is unsupported.
    """
    if fit == FIT_CONTAIN:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
    if fit == FIT_STRETCH:
        return f"scale={width}:{height}"
    if fit in (FIT_WIDTH, FIT_HEIGHT):
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    raise VideoError(f"Unsupported fit mode: {fit!r}")


def build_rotation_filter(rotation: int) -> str:
    """Build the ffmpeg filter for the user-requested rotation.

    PIL's ``rotate`` is counter-clockwise and the image pipeline already
    uses that convention, so the filters here match it to keep video and
    image rotations visually consistent.

    Args:
        rotation: User rotation in degrees.

    Returns:
        ffmpeg filter chain fragment (empty string for 0 degrees).
    """
    angle = rotation % 360
    if angle == 0:
        return ""
    if angle == 90:
        return "transpose=2"
    if angle == 180:
        return "hflip,vflip"
    if angle == 270:
        return "transpose=1"
    # ffmpeg rotate is clockwise, hence the negated angle.
    return f"rotate={-angle}*PI/180:c=black"


def build_brightness_filter(brightness: int) -> str:
    """Build the ffmpeg filter matching the PIL brightness LUT.

    Uses the same gamma-correct scaling as :func:`brightness_lut`
    (multiply sRGB-encoded values by the gamma root of the fraction and
    round to the nearest level) so video frames match static content.

    Args:
        brightness: Software brightness 0-200 percent.

    Returns:
        ffmpeg filter chain fragment (empty string at 100 percent).
    """
    scale = brightness_scale(brightness)
    if scale == 1.0:
        return ""
    expr = f"trunc(val*{scale:.6f}+0.5)"
    return f"lutrgb=r={expr}:g={expr}:b={expr}"


def build_filter_chain(
    fit: str,
    width: int,
    height: int,
    rotation: int | None,
    brightness: int | None,
) -> str:
    """Build the complete ffmpeg ``-vf`` chain for frame extraction.

    Order matters: user rotation, then the fixed 180° base panel rotation
    (the panel is natively mounted upside-down, matching the image
    pipeline), then fit, then brightness. The chain always ends with an
    explicit ``format=yuvj420p``: brightness processing forces a rgb24
    path, which would otherwise make the mjpeg encoder emit 4:4:4 JPEGs
    the panel decoder cannot display (the browser preview can, so the bug
    only shows on hardware).

    The base rotation and brightness steps apply to whole-panel playback;
    a scene video widget omits both (``None``) because the scene renderer
    applies rotation and brightness to the composed frame itself.

    Args:
        fit: Fit mode: contain, stretch, width or height.
        width: Target width.
        height: Target height.
        rotation: User rotation in degrees, or None to skip.
        brightness: Software brightness 0-200 percent, or None to skip.

    Returns:
        Full ffmpeg filter chain string.

    Raises:
        VideoError: If the fit mode is unsupported.
    """
    filters = [
        f
        for f in (
            build_rotation_filter(rotation) if rotation is not None else "",
            build_rotation_filter(DEFAULT_BASE_ROTATION) if rotation is not None else "",
            build_fit_filter(fit, width, height),
            build_brightness_filter(brightness) if brightness is not None else "",
        )
        if f
    ]
    filters.append("format=yuvj420p")
    return ",".join(filters)


def extract_video_frames(
    path: Path,
    out_dir: Path,
    fps: int,
    width: int,
    height: int,
    fit: str,
    rotation: int | None,
    brightness: int | None,
    quality: int,
    stop_event: threading.Event | None = None,
    start: float = 0.0,
) -> list[Path]:
    """Decode a video once into JPEG frames on disk.

    Scaling, fit, rotation, brightness and JPEG encoding all happen inside
    a single ffmpeg pass; playback then only reads the finished files, so
    the streaming loop spends no CPU on image processing.

    Args:
        path: Video file readable by ffmpeg.
        out_dir: Directory the ``frame_NNNNNN.jpg`` files are written to.
        fps: Output frames per second (1-60).
        width: Target width.
        height: Target height.
        fit: Fit mode: contain, stretch, width or height.
        rotation: User rotation in degrees, or None to skip (scene widget).
        brightness: Software brightness 0-200 percent, or None to skip.
        quality: JPEG quality 1-100.
        stop_event: Optional object with ``is_set()`` used to abort early.
        start: Seconds into the video to begin extraction from.

    Returns:
        Sorted list of extracted frame paths.

    Raises:
        VideoError: If ffmpeg fails or produces no frames.
    """
    ensure_ffmpeg()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-vf",
        build_filter_chain(fit, width, height, rotation, brightness),
        "-r",
        str(fps),
        "-qscale:v",
        str(quality_to_qscale(quality)),
        "-start_number",
        "0",
        str(out_dir / _FRAME_PATTERN),
    ]

    try:
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    except OSError as exc:
        raise VideoError(f"Failed to start ffmpeg: {exc}") from exc

    while proc.poll() is None:
        if stop_event is not None and stop_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise VideoError("Video preparation cancelled")
        try:
            proc.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue

    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise VideoError(f"ffmpeg exited with {proc.returncode}: {stderr.strip()}")

    frames = sorted(out_dir.glob(_FRAME_PATTERN.replace("%06d", "*")))
    if not frames:
        raise VideoError(f"ffmpeg produced no frames for {path.name}")
    logger.info("video_frames_extracted", file=path.name, frames=len(frames))
    return frames
