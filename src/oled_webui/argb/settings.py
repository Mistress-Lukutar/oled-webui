"""
File:   settings.py
Brief:  Persistent ARGB settings (display-power behaviour).
Author: Mistress-Lukutar
Date:   2026-10-01
Version: v0.5.2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

# JSON file stored inside the ARGB data directory.
SETTINGS_FILENAME: str = "settings.json"


class ArgbSettings(BaseModel):
    """User-adjustable ARGB settings persisted across restarts.

    Attributes:
        off_on_display_off: Turn the lighting off (black zones, engine
            stopped) when the Windows display powers off, and restore it
            when the display turns back on.
    """

    off_on_display_off: bool = Field(
        False, description="Turn lighting off when the Windows display powers off"
    )


def settings_path(settings: Settings) -> Path:
    """Return the JSON file path for persisted ARGB settings.

    Args:
        settings: Application settings providing the ARGB directory.

    Returns:
        Path to the ARGB settings file.
    """
    return settings.argb_dir / SETTINGS_FILENAME


def resolve_argb_settings(settings: Settings) -> ArgbSettings:
    """Load persisted settings, returning defaults on the first run.

    Args:
        settings: Application settings providing the ARGB directory.

    Returns:
        The effective ARGB settings.
    """
    path = settings_path(settings)
    if not path.is_file():
        return ArgbSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ArgbSettings.model_validate(data)
    except (OSError, ValueError) as exc:
        logger.warning("argb_settings_load_failed", file=str(path), error=str(exc))
        return ArgbSettings()


def save_argb_settings(values: ArgbSettings, path: Path) -> None:
    """Atomically persist settings to JSON; failures are logged only.

    Args:
        values: Settings snapshot to persist.
        path: Destination JSON file path.
    """
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(values.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("argb_settings_save_failed", file=str(path), error=str(exc))
