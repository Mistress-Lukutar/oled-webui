"""
File:   video_cache.py
Brief:  Per-widget video frame cache: extract once, reuse across restarts.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.1.0
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import structlog

from oled_webui.exceptions import SceneError
from oled_webui.scene.schema import VideoWidget
from oled_webui.services.video_extract import extract_video_frames

logger = structlog.get_logger(__name__)

# Extracted frames live under <cache_root>/<prefix>-<hash>/frame_NNNNNN.jpg;
# the prefix pins the source file, the hash covers every extraction input.
_FRAME_GLOB = "frame_*.jpg"


def _source_key(path: Path) -> str:
    """Stable short key of the source file path itself."""
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]


def _full_key(
    path: Path,
    fps: int,
    width: int,
    height: int,
    fit: str,
    start: float,
) -> str:
    """Cache key over the source file and every extraction parameter."""
    try:
        stat = path.stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "missing"
    raw = f"{path}|{stamp}|{fps}|{width}|{height}|{fit}|{start}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def cached_frames_dir(widget: VideoWidget, cache_root: Path) -> Path | None:
    """Return the existing cache directory for the widget, if valid.

    Args:
        widget: Video widget with a resolved absolute ``path``.
        cache_root: Root directory holding per-clip frame folders.

    Returns:
        The cache directory when the exact parameter folder exists, else
        None (caller should extract).
    """
    source = Path(widget.path)
    key = _full_key(
        source, widget.fps, widget.rect[2], widget.rect[3], widget.fit, widget.start
    )
    candidate = cache_root / f"{_source_key(source)}-{key}"
    if candidate.is_dir() and any(candidate.glob(_FRAME_GLOB)):
        return candidate
    return None


def ensure_video_frames(
    widget: VideoWidget,
    cache_root: Path | None,
) -> list[Path]:
    """Return the JPEG frame list for a video widget, extracting if needed.

    Frames are pre-extracted at the widget box size (no base rotation or
    brightness: the scene renderer applies those to the composed frame).
    A stale parameter folder for the same source file is removed so the
    cache does not grow with every edit.

    Args:
        widget: Video widget with a resolved absolute ``path``.
        cache_root: Cache root; when None a temp directory is used and the
            extraction repeats per process.

    Returns:
        Sorted frame paths.

    Raises:
        SceneError: If the video file is missing or ffmpeg fails.
    """
    source = Path(widget.path)
    if not source.is_file():
        raise SceneError(f"Video file not found: {widget.path}")

    if cache_root is None:
        import tempfile

        frames_dir = Path(tempfile.mkdtemp(prefix="oled_video_widget_"))
    else:
        prefix = _source_key(source)
        key = _full_key(
            source, widget.fps, widget.rect[2], widget.rect[3], widget.fit, widget.start
        )
        frames_dir = cache_root / f"{prefix}-{key}"
        # Drop sibling caches of the same file extracted with other
        # parameters (or from an older file version).
        if cache_root.is_dir():
            for sibling in cache_root.glob(f"{prefix}-*"):
                if sibling != frames_dir:
                    shutil.rmtree(sibling, ignore_errors=True)

    if frames_dir.is_dir() and any(frames_dir.glob(_FRAME_GLOB)):
        return sorted(frames_dir.glob(_FRAME_GLOB))

    try:
        frames_dir.mkdir(parents=True, exist_ok=True)
        frames = extract_video_frames(
            source,
            frames_dir,
            widget.fps,
            widget.rect[2],
            widget.rect[3],
            widget.fit,
            None,
            None,
            90,
            None,
            widget.start,
        )
    except SceneError:
        shutil.rmtree(frames_dir, ignore_errors=True)
        raise
    except Exception as exc:  # VideoError or filesystem problems
        shutil.rmtree(frames_dir, ignore_errors=True)
        raise SceneError(f"Video extraction failed for {source.name}: {exc}") from exc
    logger.info(
        "scene_video_cached",
        file=source.name,
        frames=len(frames),
        dir=str(frames_dir),
    )
    return frames
