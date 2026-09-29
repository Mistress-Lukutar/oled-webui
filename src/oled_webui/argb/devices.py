"""
File:   devices.py
Brief:  ARGB device definitions: YAML shape library, validation, seeds.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.6.0
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from oled_webui.argb.schema import ArgbLayout, COLOR_PATTERN
from oled_webui.exceptions import ArgbError

logger = structlog.get_logger(__name__)

# Definition ids are file-name-safe slugs; the id must match the file stem.
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Directory holding the bundled YAML seeds copied into a fresh library.
BUILTIN_DIR = Path(__file__).parent / "builtin_devices"


class _Strict(BaseModel):
    """Base for ARGB device models: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Shape models. A definition lists exactly one LED shape per LED (list order
# is the LED index); the fill of an LED shape is the effect color, so LED
# shapes only carry an optional outline. Decor shapes paint themselves.
# ---------------------------------------------------------------------------


class _LedStroke(_Strict):
    """Optional outline shared by LED shapes (fill is the LED color)."""

    stroke_color: str | None = Field(
        None, pattern=COLOR_PATTERN, description="Outline color; None = no outline"
    )
    stroke_width: float = Field(0.0, ge=0, le=64, description="Outline thickness")


class LedRect(_LedStroke):
    """A rectangular LED, optionally with rounded corners."""

    type: Literal["rect"]
    rect: tuple[float, float, float, float] = Field(
        ..., description="Shape rect as [x, y, w, h] in definition coordinates"
    )
    radius: float = Field(0.0, ge=0, description="Corner radius")

    @model_validator(mode="after")
    def _validate_rect(self) -> LedRect:
        """Reject degenerate rects.

        Raises:
            ValueError: If width or height is not positive.
        """
        if self.rect[2] <= 0 or self.rect[3] <= 0:
            raise ValueError(f"LED rect needs positive w/h, got {self.rect!r}")
        return self


class LedCircle(_LedStroke):
    """A round LED (dot)."""

    type: Literal["circle"]
    center: tuple[float, float] = Field(..., description="Dot center [x, y]")
    radius: float = Field(..., gt=0, description="Dot radius")


class LedPolygon(_LedStroke):
    """A polygonal LED (any custom shape)."""

    type: Literal["polygon"]
    points: list[tuple[float, float]] = Field(
        ..., min_length=3, max_length=64, description="Polygon vertices"
    )


LedShape = Annotated[
    LedRect | LedCircle | LedPolygon,
    Field(discriminator="type"),
]


class DecorPaint(_Strict):
    """Self-painting decor block: fill + stroke, mirroring scene styles.

    Colors are validated against the shared hex pattern so bad values fail
    at save time instead of at draw time.
    """

    fill: bool = Field(True, description="Draw the fill")
    fill_color: str = Field(
        "#222222", pattern=COLOR_PATTERN, description="Fill color as #RRGGBB"
    )
    stroke_color: str = Field(
        "#888888", pattern=COLOR_PATTERN, description="Stroke color as #RRGGBB"
    )
    stroke_width: float = Field(0.0, ge=0, le=64, description="Stroke thickness")
    stroke_align: Literal["center", "inside", "outside"] = Field(
        "inside", description="Stroke placement relative to the shape edge"
    )
    opacity: float = Field(1.0, ge=0, le=1, description="Shape opacity 0..1")


class DecorRect(DecorPaint):
    """Decorative rectangle (case outline, housing, ...)."""

    type: Literal["rect"]
    rect: tuple[float, float, float, float] = Field(..., description="[x, y, w, h]")
    radius: float = Field(0.0, ge=0, description="Corner radius")

    @model_validator(mode="after")
    def _validate_rect(self) -> DecorRect:
        """Reject degenerate rects.

        Raises:
            ValueError: If width or height is not positive.
        """
        if self.rect[2] <= 0 or self.rect[3] <= 0:
            raise ValueError(f"Decor rect needs positive w/h, got {self.rect!r}")
        return self


class DecorCircle(DecorPaint):
    """Decorative circle (fan frame, hub, ...)."""

    type: Literal["circle"]
    center: tuple[float, float] = Field(..., description="Circle center [x, y]")
    radius: float = Field(..., gt=0, description="Circle radius")


class DecorPolygon(DecorPaint):
    """Decorative filled/outlined polygon (fan blade, cutout, ...)."""

    type: Literal["polygon"]
    points: list[tuple[float, float]] = Field(
        ..., min_length=3, max_length=64, description="Polygon vertices"
    )


class _DecorStroke(_Strict):
    """Stroke-only paint block for open shapes."""

    stroke_color: str = Field(
        "#888888", pattern=COLOR_PATTERN, description="Stroke color as #RRGGBB"
    )
    stroke_width: float = Field(1.0, ge=0, le=64, description="Stroke thickness")
    opacity: float = Field(1.0, ge=0, le=1, description="Shape opacity 0..1")


class DecorPolyline(_DecorStroke):
    """Decorative open line (cable, seam, ...); stroke only, never filled."""

    type: Literal["polyline"]
    points: list[tuple[float, float]] = Field(
        ..., min_length=2, max_length=64, description="Line vertices"
    )


DecorShape = Annotated[
    DecorRect | DecorCircle | DecorPolygon | DecorPolyline,
    Field(discriminator="type"),
]


class ArgbDeviceDefinition(_Strict):
    """A drawable device template: LED shapes plus decorative graphics.

    The ``leds`` list holds exactly one shape per LED; the list position is
    the LED index used by effects, masks and the header chain order. LED
    fills come from the effect engine, decor is purely visual.
    """

    id: str = Field(
        ...,
        pattern=ID_PATTERN.pattern,
        description="Unique slug; must match the YAML file name",
    )
    name: str = Field("", max_length=100, description="Display name")
    size: tuple[float, float] | None = Field(
        None,
        description="Nominal design size [w, h]; the instance center is size/2. "
        "Derived from the shape bounds when omitted",
    )
    leds: list[LedShape] = Field(
        ...,
        min_length=1,
        max_length=512,
        description="One shape per LED; list order is the LED index",
    )
    decor: list[DecorShape] = Field(
        default_factory=list, description="Non-LED graphics drawn under the LEDs"
    )

    @property
    def led_count(self) -> int:
        """Number of LEDs this device definition provides."""
        return len(self.leds)

    def bounds(self) -> tuple[float, float, float, float]:
        """Tight bounding box [x, y, w, h] of all LED and decor shapes."""
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        def grow(x0: float, y0: float, x1: float, y1: float) -> None:
            nonlocal min_x, min_y, max_x, max_y
            min_x, min_y = min(min_x, x0, x1), min(min_y, y0, y1)
            max_x, max_y = max(max_x, x0, x1), max(max_y, y0, y1)

        for shape in (*self.leds, *self.decor):
            match shape:
                case LedRect(rect=[x, y, w, h]) | DecorRect(rect=[x, y, w, h]):
                    grow(x, y, x + w, y + h)
                case LedCircle(center=[cx, cy], radius=r) | DecorCircle(
                    center=[cx, cy], radius=r
                ):
                    grow(cx - r, cy - r, cx + r, cy + r)
                case LedPolygon(points=pts) | DecorPolygon(points=pts) | DecorPolyline(
                    points=pts
                ):
                    for px, py in pts:
                        grow(px, py, px, py)
        return (min_x, min_y, max_x - min_x, max_y - min_y)

    def center(self) -> tuple[float, float]:
        """The local point an instance's x/y anchors to."""
        if self.size is not None:
            return (self.size[0] / 2.0, self.size[1] / 2.0)
        x, y, w, h = self.bounds()
        return (x + w / 2.0, y + h / 2.0)


def parse_definition(text: str) -> ArgbDeviceDefinition:
    """Parse and validate a device definition from YAML text.

    Args:
        text: Raw YAML source of the definition.

    Returns:
        The validated definition.

    Raises:
        ArgbError: If the YAML is malformed or fails validation.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ArgbError(f"Invalid device YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ArgbError("Device definition must be a YAML mapping")
    try:
        return ArgbDeviceDefinition.model_validate(data)
    except ValidationError as exc:
        raise ArgbError(f"Invalid device definition: {exc}") from exc


class DeviceLibrary:
    """Loads, validates and persists YAML device definitions.

    Bundled seeds are copied into the directory on first access, so a fresh
    install ships with working example devices the user can edit in place.
    """

    def __init__(self, devices_dir: Path) -> None:
        """Scan the directory and seed built-ins.

        Args:
            devices_dir: Directory holding ``<id>.yaml`` definitions.
        """
        self._dir = devices_dir
        self._defs: dict[str, ArgbDeviceDefinition] = {}
        self._sources: dict[str, str] = {}
        self.reload()

    @property
    def directory(self) -> Path:
        """The library directory."""
        return self._dir

    def reload(self) -> None:
        """(Re)read every definition file, seeding built-ins first.

        Broken files are skipped with a warning so one bad YAML cannot take
        the whole library (and with it the layout) down.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        self._seed_builtin()
        self._defs = {}
        self._sources = {}
        for path in sorted((*self._dir.glob("*.yaml"), *self._dir.glob("*.yml"))):
            try:
                text = path.read_text(encoding="utf-8")
                definition = parse_definition(text)
            except ArgbError as exc:
                logger.warning("argb_device_skipped", file=path.name, error=str(exc))
                continue
            if path.stem != definition.id:
                logger.warning(
                    "argb_device_id_mismatch",
                    file=path.name,
                    id=definition.id,
                )
                continue
            self._defs[definition.id] = definition
            self._sources[definition.id] = text

    def _seed_builtin(self) -> None:
        """Copy bundled example devices that are missing from the library."""
        copied = []
        for src in sorted(BUILTIN_DIR.glob("*.yaml")):
            dst = self._dir / src.name
            if not dst.exists():
                shutil.copyfile(src, dst)
                copied.append(src.stem)
        if copied:
            logger.info("argb_devices_seeded", devices=copied)

    def list(self) -> list[ArgbDeviceDefinition]:
        """All definitions, sorted by id."""
        return [self._defs[device_id] for device_id in sorted(self._defs)]

    def get(self, device_id: str) -> ArgbDeviceDefinition | None:
        """Look up one definition by id."""
        return self._defs.get(device_id)

    def source(self, device_id: str) -> str:
        """Raw YAML text of one definition.

        Raises:
            ArgbError: If the id is unknown.
        """
        if device_id not in self._sources:
            raise ArgbError(f"Unknown device definition: {device_id!r}")
        return self._sources[device_id]

    def save_yaml(self, text: str, expected_id: str | None = None) -> ArgbDeviceDefinition:
        """Validate YAML text and store it as ``<id>.yaml``.

        Args:
            text: Raw YAML source of the definition.
            expected_id: When given (PUT), the definition id must match it.

        Returns:
            The stored definition.

        Raises:
            ArgbError: On invalid YAML, id mismatch or write failure.
        """
        definition = parse_definition(text)
        if expected_id is not None and definition.id != expected_id:
            raise ArgbError(
                f"Definition id {definition.id!r} does not match {expected_id!r}"
            )
        target = self._dir / f"{definition.id}.yaml"
        try:
            tmp = target.with_suffix(".yaml.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(target)
        except OSError as exc:
            raise ArgbError(f"Failed to save device definition: {exc}") from exc
        self._defs[definition.id] = definition
        self._sources[definition.id] = text
        return definition

    def delete(self, device_id: str) -> None:
        """Remove a definition file from the library.

        Raises:
            ArgbError: If the id is unknown or the file cannot be removed.
        """
        if device_id not in self._defs:
            raise ArgbError(f"Unknown device definition: {device_id!r}")
        deleted = False
        for suffix in (".yaml", ".yml"):
            path = self._dir / f"{device_id}{suffix}"
            if path.exists():
                try:
                    path.unlink()
                    deleted = True
                except OSError as exc:
                    raise ArgbError(f"Failed to delete device definition: {exc}") from exc
        if not deleted:
            raise ArgbError(f"Failed to delete device definition: {device_id!r}")
        del self._defs[device_id]
        del self._sources[device_id]

    def led_counts(self, device_ids: Iterable[str]) -> dict[str, int]:
        """LED counts for the given definition ids; unknown ids are omitted."""
        counts: dict[str, int] = {}
        for device_id in device_ids:
            definition = self._defs.get(device_id)
            if definition is not None:
                counts[device_id] = definition.led_count
        return counts


def resolve_led_counts(
    layout: ArgbLayout, library: DeviceLibrary
) -> dict[str, int]:
    """Map every layout device id to its definition's LED count.

    Args:
        layout: Layout whose instances reference library definitions.
        library: The device definition library.

    Returns:
        Mapping of device instance id to LED count.

    Raises:
        ArgbError: If any instance references an unknown definition.
    """
    counts: dict[str, int] = {}
    missing: list[str] = []
    for device in layout.devices:
        definition = library.get(device.device)
        if definition is None:
            missing.append(f"{device.id} -> {device.device!r}")
        else:
            counts[device.id] = definition.led_count
    if missing:
        raise ArgbError(
            "Layout references unknown device definitions: " + ", ".join(missing)
        )
    return counts


def validate_with_library(
    layout: ArgbLayout, library: DeviceLibrary
) -> dict[str, int]:
    """Run the LED-count-dependent layout checks against the library.

    The schema validator cannot see the library, so chain capacity and mask
    ranges are enforced here, right before persistence or rendering.

    Args:
        layout: Structurally valid layout.
        library: The device definition library.

    Returns:
        Resolved LED counts per device instance id.

    Raises:
        ArgbError: On unknown definitions, chain overflow or bad mask runs.
    """
    counts = resolve_led_counts(layout, library)
    for header in layout.headers:
        used = sum(counts[device_id] for device_id in header.devices)
        if header.size is not None and used > header.size:
            raise ArgbError(
                f"Header {header.id!r} chain needs {used} LEDs "
                f"but the zone provides {header.size}"
            )
    by_id = {device.id: device for device in layout.devices}
    for layer in layout.layers:
        for device_id, runs in layer.mask.runs.items():
            last = counts[device_id] - 1
            for start, end in runs:
                if start > end:
                    raise ArgbError(
                        f"Layer {layer.id!r} mask run [{start}, {end}] is inverted"
                    )
                if start < 0 or end > last:
                    raise ArgbError(
                        f"Layer {layer.id!r} mask run [{start}, {end}] is out of "
                        f"range for device {device_id!r} ({last + 1} LEDs)"
                    )
    return counts
