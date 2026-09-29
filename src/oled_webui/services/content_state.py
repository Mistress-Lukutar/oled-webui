"""
File:   content_state.py
Brief:  Persistent last-screen snapshot: save, load and restore panel content.
Author: Mistress-Lukutar
Date:   2026-09-28
Version: v0.4.0
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from oled_webui.config import Settings
    from oled_webui.services.display_service import DisplayService
    from oled_webui.services.scene_service import SceneService

logger = structlog.get_logger(__name__)

# JSON file stored inside the data directory.
CONTENT_STATE_FILENAME: str = "last_content.json"


def content_state_path(settings: Settings) -> Path:
    """Return the JSON file path for the persisted last-screen snapshot.

    Args:
        settings: Application settings providing the data directory.

    Returns:
        Path to the content state file.
    """
    return settings.data_dir / CONTENT_STATE_FILENAME


def load_content_state(path: Path) -> dict[str, Any] | None:
    """Load the persisted content snapshot.

    Args:
        path: JSON file previously written by :func:`save_content_state`.

    Returns:
        The snapshot dict, or None when missing, corrupt or malformed.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("content_state_load_failed", file=str(path), error=str(exc))
        return None
    if not isinstance(data, dict) or "type" not in data:
        logger.warning("content_state_invalid", file=str(path))
        return None
    return data


def save_content_state(path: Path, content: dict[str, Any] | None) -> None:
    """Atomically persist the content snapshot; failures are logged only.

    Args:
        path: Destination JSON file path.
        content: Content snapshot to persist, or None to remove the file.
    """
    try:
        if content is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(content, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("content_state_save_failed", file=str(path), error=str(exc))


async def restore_last_content(
    display: DisplayService,
    scenes: SceneService,
    settings: Settings,
) -> bool:
    """Reapply the persisted last-screen snapshot after a fresh connect.

    A persisted scene is restarted from its YAML source. Snapshots of
    removed content types (image/color/text from older versions) are
    ignored. Any failure (deleted scene, render error) is logged and
    reported as "not restored", so callers never break startup.

    Args:
        display: Connected display service receiving the content.
        scenes: Scene service used to load a persisted scene document.
        settings: Application settings providing the data directory.

    Returns:
        True when content was restored, False otherwise.
    """
    content = load_content_state(content_state_path(settings))
    if content is None:
        return False
    if content.get("type") != "scene":
        logger.warning(
            "content_state_legacy_ignored", type=str(content.get("type"))
        )
        return False
    try:
        payload = content.get("payload") or {}
        scene_id = str(payload.get("scene_id", ""))
        meta = scenes.get_meta(scene_id)
        document = scenes.load_document(scene_id)
        await display.start_scene(document, scene_id, meta.name)
    # Best-effort restore: any storage or renderer problem must not break
    # the surrounding connect flow or server startup.
    except Exception as exc:
        logger.warning("content_restore_failed", error=str(exc))
        return False
    logger.info("last_screen_restored", type=str(content.get("type")))
    return True
