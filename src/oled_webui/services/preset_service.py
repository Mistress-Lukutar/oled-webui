"""
File:   preset_service.py
Brief:  File-backed preset storage with binary asset handling.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.3.0
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

from oled_webui.exceptions import PresetNotFoundError, ValidationError

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

PRESET_TYPES: tuple[str, ...] = ("image", "color", "text", "scene")


class Preset(BaseModel):
    """A stored display content snapshot.

    Attributes:
        id: Unique preset identifier.
        name: Human-readable preset name.
        type: Content type: image, color or text.
        params: Render parameters (rotation, fit); brightness and quality
            come from the global display settings at apply time.
        payload: Content payload (color, text fields or image file name).
        created_at: Unix timestamp of creation.
        has_asset: True when a binary asset file is stored alongside.
    """

    id: str = Field(..., description="Unique preset identifier")
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Content type: image, color or text")
    params: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    has_asset: bool = False


class PresetService:
    """CRUD for presets stored as JSON files with optional binary assets.

    Layout::

        <presets_dir>/<id>.json       preset metadata
        <presets_dir>/assets/<id>.<ext>  binary asset (image)
    """

    def __init__(self, settings: Settings) -> None:
        self._presets_dir = settings.presets_dir
        self._uploads_dir = settings.uploads_dir
        self._assets_dir = self._presets_dir / "assets"
        self._presets_dir.mkdir(parents=True, exist_ok=True)
        self._assets_dir.mkdir(parents=True, exist_ok=True)

    @property
    def assets_dir(self) -> Path:
        """Directory holding preset binary assets."""
        return self._assets_dir

    def list_presets(self) -> list[Preset]:
        """Return all presets sorted by creation time, newest first."""
        presets: list[Preset] = []
        for path in self._presets_dir.glob("*.json"):
            preset = self._read(path)
            if preset is not None:
                presets.append(preset)
        return sorted(presets, key=lambda p: p.created_at, reverse=True)

    def get_preset(self, preset_id: str) -> Preset:
        """Load a preset by id.

        Args:
            preset_id: Unique preset identifier.

        Returns:
            The loaded preset.

        Raises:
            PresetNotFoundError: If no preset with this id exists.
        """
        path = self._preset_path(preset_id)
        preset = self._read(path)
        if preset is None:
            raise PresetNotFoundError(f"Preset not found: {preset_id}")
        return preset

    def asset_path(self, preset: Preset) -> Path | None:
        """Return the binary asset path for a preset, if present.

        Args:
            preset: The preset to inspect.

        Returns:
            Path to the asset file, or None when the preset has no asset.
        """
        if not preset.has_asset:
            return None
        for path in self._assets_dir.glob(f"{preset.id}.*"):
            return path
        return None

    def save_from_content(self, name: str, content: dict[str, Any]) -> Preset:
        """Create a preset from the last applied display content.

        For image content the referenced upload file is copied into the
        preset assets directory so the preset stays self-contained.

        Args:
            name: Display name for the new preset.
            content: The ``last_content`` snapshot from DisplayService.

        Returns:
            The newly created preset.

        Raises:
            ValidationError: If the content snapshot is empty or invalid.
        """
        preset_type = content.get("type")
        if preset_type not in PRESET_TYPES:
            raise ValidationError("Nothing to save yet; apply some content first")

        preset = Preset(
            id=uuid.uuid4().hex[:12],
            name=name,
            type=preset_type,
            params=dict(content.get("params", {})),
            payload=dict(content.get("payload", {})),
        )

        if preset_type == "image":
            upload_name = str(preset.payload.get("file", ""))
            stored_path = preset.payload.get("path")
            source = (
                Path(str(stored_path))
                if stored_path
                else self._uploads_dir / upload_name
            )
            if not source.is_file():
                raise ValidationError(
                    f"Source image no longer available: {upload_name}"
                )
            dest = self._assets_dir / f"{preset.id}{source.suffix.lower()}"
            shutil.copy2(source, dest)
            preset.payload["file"] = dest.name
            preset.has_asset = True

        self._write(preset)
        logger.info("preset_saved", id=preset.id, name=name, type=preset_type)
        return preset

    def delete_preset(self, preset_id: str) -> None:
        """Delete a preset and its asset.

        Args:
            preset_id: Unique preset identifier.

        Raises:
            PresetNotFoundError: If no preset with this id exists.
        """
        preset = self.get_preset(preset_id)
        self._preset_path(preset_id).unlink(missing_ok=True)
        if preset.has_asset:
            for path in self._assets_dir.glob(f"{preset_id}.*"):
                path.unlink(missing_ok=True)
        logger.info("preset_deleted", id=preset_id)

    def _preset_path(self, preset_id: str) -> Path:
        """Build the JSON path for a preset id, validating the id format."""
        if not preset_id or any(c in preset_id for c in "/\\.:"):
            raise ValidationError(f"Invalid preset id: {preset_id!r}")
        return self._presets_dir / f"{preset_id}.json"

    def _read(self, path: Path) -> Preset | None:
        """Load one preset JSON file, returning None on any error."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Preset.model_validate(data)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning("preset_read_failed", file=path.name, error=str(exc))
            return None

    def _write(self, preset: Preset) -> None:
        """Atomically persist a preset JSON file."""
        path = self._preset_path(preset.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(preset.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
