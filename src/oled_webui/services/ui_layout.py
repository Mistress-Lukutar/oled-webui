"""
File:   ui_layout.py
Brief:  Persistent dashboard panel layout: default, load and save.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.1.0
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from oled_webui.models.schemas import PanelConfig, PanelLayout

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

# JSON file stored inside the data directory.
PANELS_FILENAME: str = "panels.json"

def default_panels() -> PanelLayout:
    """Return a fresh copy of the default dashboard layout.

    Returns:
        A new PanelLayout instance so callers cannot mutate the constant.
    """
    return default_panels_instance.model_copy(deep=True)


default_panels_instance: PanelLayout = PanelLayout(
    panels=[
        PanelConfig(id="status", type="status", aspect=2.4),
        PanelConfig(id="display-preview", type="display-preview", device="display:0", aspect=1.6),
        PanelConfig(id="display-settings", type="display-settings", device="display:0", aspect=0.75),
        PanelConfig(id="scenes", type="scenes", device="display:0", aspect=0.85),
        PanelConfig(id="argb-preview", type="argb-preview", device="argb:openrgb", aspect=1.0),
        PanelConfig(id="argb-settings", type="argb-settings", device="argb:openrgb", aspect=0.7),
    ]
)


def panels_path(settings: Settings) -> Path:
    """Return the JSON file path for the persisted panel layout."""
    return settings.data_dir / "ui" / PANELS_FILENAME


def load_panels(path: Path) -> PanelLayout | None:
    """Load the persisted panel layout.

    Args:
        path: JSON file previously written by :func:`save_panels`.

    Returns:
        The layout, or None when missing, corrupt or invalid.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PanelLayout.model_validate(data)
    except (OSError, ValueError) as exc:
        logger.warning("panels_load_failed", file=str(path), error=str(exc))
        return None


def save_panels(path: Path, layout: PanelLayout) -> None:
    """Atomically persist the panel layout; failures are logged only.

    Args:
        path: Destination JSON file path.
        layout: Layout to persist.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(layout.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("panels_save_failed", file=str(path), error=str(exc))
