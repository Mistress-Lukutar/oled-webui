"""
File:   scene_service.py
Brief:  File-backed scene storage: YAML sources, metadata and assets.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO

import structlog
import yaml
from pydantic import BaseModel, Field

from oled_webui.exceptions import SceneNotFoundError, ValidationError
from oled_webui.scene.loader import load_scene, load_scene_from_text
from oled_webui.scene.schema import SceneDocument

if TYPE_CHECKING:
    from oled_webui.config import Settings

logger = structlog.get_logger(__name__)

# Default template offered when a scene is created without YAML content:
# a screen section with live widgets plus a commented ARGB example.
SCENE_TEMPLATE: str = """\
# Scene: the appearance of the whole computer, one section per device.
# Screen sources: cpu.percent, ram.percent, disk.percent, net.kbps,
# temp.cpu, gpu.percent, time.hms, time.date

screen:
  refresh: 1.0            # data polling rate (Hz)
  max_fps: 20             # animation frame rate cap
  keepalive_interval: 2.0 # resend interval for unchanged frames
  # Brightness and JPEG quality are global display settings
  # (Settings dialog in the web UI), not per-scene values.

  widgets:
    - type: text
      source: time.hms
      rect: [40, 40, 400, 80]
      align: center
      style:
        size: 56
        fill_color: "#FFFFFF"
    - type: bar
      source: cpu
      rect: [40, 160, 400, 24]
      style:
        progress_color: "#7CFC00"
        fill_color: "#1a1a1a"
        radius: 6

# Uncomment to drive ARGB lighting from this scene. Headers map OpenRGB
# zones; devices reference definitions from the device library; layers
# stack effects bottom-first. A scene without an "argb:" section stops
# the lighting engine when applied.
# argb:
#   fps: 30
#   brightness: 100
#   headers:
#     - id: h1
#       name: ARGB 1
#       zone_index: 0
#       devices: [d1]
#   devices:
#     - id: d1
#       name: Strip 1
#       device: strip
#       header_id: h1
#       x: 200
#       y: 250
#   layers:
#     - id: l1
#       name: Fill
#       effect:
#         type: fill
#         color: "#2244CC"
"""


class SceneMeta(BaseModel):
    """Stored scene metadata.

    Attributes:
        id: Unique scene identifier.
        name: Human-readable scene name.
        created_at: Unix timestamp of creation.
        updated_at: Unix timestamp of the last YAML edit.
    """

    id: str = Field(..., description="Unique scene identifier")
    name: str = Field(..., min_length=1, max_length=100)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    widget_count: int = Field(default=0, ge=0, description="Number of widgets")


class SceneService:
    """CRUD for scenes stored as directories with YAML, meta and assets.

    Layout::

        <scenes_dir>/<id>/scene.yaml    scene source
        <scenes_dir>/<id>/scene.json    metadata
        <scenes_dir>/<id>/assets/*      referenced images and fonts
        <scenes_dir>/<id>/components/*  component definitions used by ``use:``
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scenes_dir = settings.scenes_dir
        self._scenes_dir.mkdir(parents=True, exist_ok=True)

    @property
    def scenes_dir(self) -> Path:
        """Directory holding all scene folders."""
        return self._scenes_dir

    @property
    def font_library_dir(self) -> Path:
        """Directory of the shared font library used by ``fonts/`` paths."""
        return self._settings.fonts_dir

    def list_scenes(self) -> list[SceneMeta]:
        """Return all scenes sorted by update time, newest first."""
        scenes: list[SceneMeta] = []
        for meta_path in self._scenes_dir.glob("*/scene.json"):
            meta = self._read_meta(meta_path)
            if meta is not None:
                scenes.append(meta)
        return sorted(scenes, key=lambda s: s.updated_at, reverse=True)

    def get_meta(self, scene_id: str) -> SceneMeta:
        """Load scene metadata by id.

        Args:
            scene_id: Unique scene identifier.

        Returns:
            The loaded metadata.

        Raises:
            SceneNotFoundError: If no scene with this id exists.
        """
        meta = self._read_meta(self._meta_path(scene_id))
        if meta is None:
            raise SceneNotFoundError(f"Scene not found: {scene_id}")
        return meta

    def read_yaml(self, scene_id: str) -> str:
        """Return the YAML source of a scene.

        Args:
            scene_id: Unique scene identifier.

        Returns:
            Scene YAML text.

        Raises:
            SceneNotFoundError: If the scene or its YAML file is missing.
        """
        self.get_meta(scene_id)
        yaml_path = self._yaml_path(scene_id)
        try:
            return yaml_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SceneNotFoundError(f"Scene YAML missing: {scene_id}") from exc

    def create_scene(
        self, name: str, yaml_text: str | None = None
    ) -> SceneMeta:
        """Create a scene from a name and optional YAML source.

        Args:
            name: Human-readable scene name.
            yaml_text: Validated YAML source; a starter template is used
                when omitted.

        Returns:
            The new scene metadata.

        Raises:
            SceneError: If the provided YAML does not validate.
        """
        meta = SceneMeta(id=uuid.uuid4().hex[:12], name=name)
        self._scene_dir(meta.id).mkdir(parents=True, exist_ok=True)
        self._write_yaml(
            meta.id, yaml_text if yaml_text is not None else SCENE_TEMPLATE
        )
        self._write_meta(meta)
        logger.info("scene_created", id=meta.id, name=name)
        return meta

    def save_yaml(
        self, scene_id: str, yaml_text: str, name: str | None = None
    ) -> SceneMeta:
        """Validate and persist a scene's YAML source.

        Args:
            scene_id: Unique scene identifier.
            yaml_text: New YAML source; must validate against the schema.
            name: Optional new display name.

        Returns:
            The updated scene metadata.

        Raises:
            SceneNotFoundError: If the scene does not exist.
            SceneError: If the YAML does not validate.
        """
        meta = self.get_meta(scene_id)
        document = load_scene_from_text(
            yaml_text,
            self._scene_dir(scene_id),
            source_name="scene.yaml",
            fonts_dir=self._settings.fonts_dir,
        )
        self._write_yaml(scene_id, yaml_text)
        meta.updated_at = time.time()
        meta.widget_count = len(document.screen.widgets) if document.screen else 0
        if name is not None:
            meta.name = name
        self._write_meta(meta)
        logger.info(
            "scene_saved",
            id=scene_id,
            widgets=meta.widget_count,
        )
        return meta

    def load_document(self, scene_id: str) -> SceneDocument:
        """Load and resolve the validated scene document for a scene id.

        Args:
            scene_id: Unique scene identifier.

        Returns:
            Validated scene document (one section per device) with
            resolved asset paths.

        Raises:
            SceneNotFoundError: If the scene does not exist.
            SceneError: If the YAML does not validate.
        """
        self.get_meta(scene_id)
        return load_scene(
            self._yaml_path(scene_id), fonts_dir=self._settings.fonts_dir
        )

    def add_assets(self, scene_id: str, files: list[tuple[str, BinaryIO]]) -> list[str]:
        """Store uploaded asset files for a scene.

        Args:
            scene_id: Unique scene identifier.
            files: (original filename, binary stream) pairs.

        Returns:
            Stored asset file names.

        Raises:
            SceneNotFoundError: If the scene does not exist.
        """
        self.get_meta(scene_id)
        assets_dir = self._assets_dir(scene_id)
        assets_dir.mkdir(parents=True, exist_ok=True)
        stored: list[str] = []
        for filename, stream in files:
            safe = _safe_name(filename)
            if not safe:
                continue
            dest = assets_dir / safe
            with dest.open("wb") as out:
                shutil.copyfileobj(stream, out)
            stored.append(safe)
        logger.info("scene_assets_added", id=scene_id, count=len(stored))
        return stored

    def list_assets(self, scene_id: str) -> list[str]:
        """List asset file names stored for a scene.

        Args:
            scene_id: Unique scene identifier.

        Returns:
            Asset file names sorted alphabetically.

        Raises:
            SceneNotFoundError: If the scene does not exist.
        """
        self.get_meta(scene_id)
        assets_dir = self._assets_dir(scene_id)
        if not assets_dir.is_dir():
            return []
        return sorted(path.name for path in assets_dir.iterdir() if path.is_file())

    def read_asset_path(self, scene_id: str, asset_name: str) -> Path:
        """Resolve a stored asset file path for reading.

        Args:
            scene_id: Unique scene identifier.
            asset_name: Stored asset file name as returned by
                :meth:`list_assets`.

        Returns:
            Path to the asset file inside the scene's assets directory.

        Raises:
            SceneNotFoundError: If the scene or asset does not exist.
            ValidationError: If the name is not a safe flat file name.
        """
        self.get_meta(scene_id)
        safe = _safe_name(asset_name)
        if not safe or safe != asset_name:
            raise ValidationError(f"Invalid asset name: {asset_name!r}")
        path = self._assets_dir(scene_id) / safe
        if not path.is_file():
            raise SceneNotFoundError(f"Asset not found: {asset_name}")
        return path

    def list_components(self, scene_id: str) -> dict[str, str]:
        """Return component YAML sources keyed by component name.

        Args:
            scene_id: Unique scene identifier.

        Returns:
            Mapping of component name (file stem) to its YAML source;
            empty when the scene defines no components.

        Raises:
            SceneNotFoundError: If the scene does not exist.
        """
        self.get_meta(scene_id)
        components_dir = self._scene_dir(scene_id) / "components"
        if not components_dir.is_dir():
            return {}
        sources: dict[str, str] = {}
        for path in sorted(components_dir.iterdir()):
            if path.suffix.lower() not in (".yaml", ".yml") or not path.is_file():
                continue
            try:
                sources[path.stem] = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "scene_component_read_failed", file=str(path), error=str(exc)
                )
        return sources

    def delete_asset(self, scene_id: str, asset_name: str) -> None:
        """Delete one stored asset file.

        Args:
            scene_id: Unique scene identifier.
            asset_name: Stored asset file name.

        Raises:
            SceneNotFoundError: If the scene or asset does not exist.
        """
        self.get_meta(scene_id)
        path = self._assets_dir(scene_id) / _safe_name(asset_name)
        if not path.is_file():
            raise SceneNotFoundError(f"Asset not found: {asset_name}")
        path.unlink()
        logger.info("scene_asset_deleted", id=scene_id, asset=path.name)

    def delete_scene(self, scene_id: str) -> None:
        """Delete a scene with its YAML, metadata and assets.

        Args:
            scene_id: Unique scene identifier.

        Raises:
            SceneNotFoundError: If the scene does not exist.
        """
        self.get_meta(scene_id)
        shutil.rmtree(self._scene_dir(scene_id))
        logger.info("scene_deleted", id=scene_id)

    def seed_example(self, source_dir: Path) -> SceneMeta:
        """Create a new scene from the bundled example files.

        Copies the example ``scene.yaml`` plus its ``components/`` and
        ``assets/`` directories into a fresh scene folder.

        Args:
            source_dir: Directory with the example scene files.

        Returns:
            The new scene metadata.

        Raises:
            ValidationError: If the example directory is incomplete.
        """
        yaml_path = source_dir / "scene.yaml"
        if not yaml_path.is_file():
            raise ValidationError(f"Example scene missing: {source_dir}")
        meta = self.create_scene("Dashboard Example", yaml_path.read_text("utf-8"))
        for sub in ("components", "assets"):
            src = source_dir / sub
            if src.is_dir():
                shutil.copytree(src, self._scene_dir(meta.id) / sub)
        return meta

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _scene_dir(self, scene_id: str) -> Path:
        """Build and validate the directory path for a scene id."""
        _validate_id(scene_id)
        return self._scenes_dir / scene_id

    def _yaml_path(self, scene_id: str) -> Path:
        """Build the YAML path for a scene id."""
        return self._scene_dir(scene_id) / "scene.yaml"

    def _meta_path(self, scene_id: str) -> Path:
        """Build the metadata path for a scene id."""
        return self._scene_dir(scene_id) / "scene.json"

    def _assets_dir(self, scene_id: str) -> Path:
        """Build the assets path for a scene id."""
        return self._scene_dir(scene_id) / "assets"

    def _read_meta(self, path: Path) -> SceneMeta | None:
        """Load one metadata file, returning None on any error."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = SceneMeta.model_validate(data)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning("scene_meta_read_failed", file=str(path), error=str(exc))
            return None
        meta.widget_count = _widget_count(self._scenes_dir / meta.id / "scene.yaml")
        return meta

    def _write_meta(self, meta: SceneMeta) -> None:
        """Atomically persist scene metadata."""
        path = self._meta_path(meta.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def _write_yaml(self, scene_id: str, yaml_text: str) -> None:
        """Atomically persist scene YAML source."""
        path = self._yaml_path(scene_id)
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml_text, encoding="utf-8")
        tmp.replace(path)


def _validate_id(scene_id: str) -> None:
    """Reject scene ids that could escape the scenes directory.

    Args:
        scene_id: Identifier to check.

    Raises:
        ValidationError: If the id contains path separators or dots.
    """
    if not scene_id or any(c in scene_id for c in "/\\.:"):
        raise ValidationError(f"Invalid scene id: {scene_id!r}")


def _safe_name(filename: str) -> str:
    """Normalize an uploaded file name to a safe flat file name.

    Args:
        filename: Original client-provided file name.

    Returns:
        Sanitized name, possibly empty when nothing usable remains.
    """
    stem = Path(filename).stem or "asset"
    suffix = Path(filename).suffix.lower()[:10]
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:60]
    return f"{safe_stem}{suffix}"


def _widget_count(yaml_path: Path) -> int:
    """Best-effort widget count for listings; 0 when the YAML is invalid."""
    try:
        document: Any = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return 0
    if isinstance(document, dict):
        screen = document.get("screen")
        if isinstance(screen, dict):
            widgets = screen.get("widgets")
            return len(widgets) if isinstance(widgets, list) else 0
    return 0
