"""
File:   display_settings.py
Brief:  Persistent display settings: keepalive, brightness, quality, power.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from oled_webui.core.constants import DEFAULT_BRIGHTNESS, DEFAULT_JPEG_QUALITY

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

# JSON file stored inside the data directory.
SETTINGS_FILENAME: str = "display_settings.json"


class DisplaySettings(BaseModel):
    """User-adjustable display settings persisted across restarts.

    Attributes:
        keepalive_enabled: Whether the keepalive resend loop runs.
        keepalive_interval: Seconds between keepalive frame resends.
        brightness: Global software brightness percent (0-200) applied to
            every content type sent to the panel.
        quality: Global JPEG encoding quality (1-100).
        blank_on_display_off: Blank the panel when the Windows display
            powers off (power saving) and restore it when it turns on.
    """

    keepalive_enabled: bool = Field(True, description="Run the keepalive loop")
    keepalive_interval: float = Field(1.5, ge=0.1, description="Keepalive seconds")
    brightness: int = Field(
        DEFAULT_BRIGHTNESS, ge=0, le=200, description="Global brightness percent"
    )
    quality: int = Field(
        DEFAULT_JPEG_QUALITY, ge=1, le=100, description="Global JPEG quality"
    )
    blank_on_display_off: bool = Field(
        False, description="Blank panel when the Windows display powers off"
    )


def settings_path(settings: Settings) -> Path:
    """Return the JSON file path for persisted display settings.

    Args:
        settings: Application settings providing the data directory.

    Returns:
        Path to the display settings file.
    """
    return settings.data_dir / SETTINGS_FILENAME


def resolve_display_settings(settings: Settings) -> DisplaySettings:
    """Load persisted settings, seeding from env config on the first run.

    A stored file always wins over environment defaults: it represents the
    user's explicit choices made in the settings dialog.

    Args:
        settings: Application settings providing defaults and the data dir.

    Returns:
        The effective display settings.
    """
    path = settings_path(settings)
    if not path.is_file():
        return DisplaySettings(
            keepalive_enabled=settings.keepalive_enabled,
            keepalive_interval=settings.keepalive_interval,
            brightness=settings.brightness,
            quality=settings.jpeg_quality,
            blank_on_display_off=settings.blank_on_display_off,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DisplaySettings.model_validate(data)
    except (OSError, ValueError) as exc:
        logger.warning("display_settings_load_failed", file=str(path), error=str(exc))
        return DisplaySettings()


def save_display_settings(values: DisplaySettings, path: Path) -> None:
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
        logger.warning("display_settings_save_failed", file=str(path), error=str(exc))
