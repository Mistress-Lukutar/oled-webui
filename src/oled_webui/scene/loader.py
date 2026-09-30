"""
File:   loader.py
Brief:  YAML scene loading, component instantiation and path resolution.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from oled_webui.exceptions import SceneError
from oled_webui.scene.schema import (
    ImageWidget,
    SceneDocument,
    VideoWidget,
)

logger = structlog.get_logger(__name__)

# Instance-level keys consumed by the loader itself; everything else in a
# ``use:`` block is treated as a component parameter.
_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "use",
        "at",
        "animate",
        "visible",
        "offset_x",
        "offset_y",
        "opacity",
        "rotation",
        "locked",
    }
)

# Keys copied from the instance block into every rendered child that does
# not define the key itself.
_OVERRIDE_KEYS: tuple[str, ...] = (
    "animate",
    "visible",
    "offset_x",
    "offset_y",
    "opacity",
    "rotation",
    "locked",
)

_PLACEHOLDER: re.Pattern[str] = re.compile(r"\{\{\s*([A-Za-z_]\w*(?:\.\w+)*)\s*\}\}")

_MAX_COMPONENT_DEPTH: int = 8


def load_scene(path: Path, fonts_dir: Path | None = None) -> SceneDocument:
    """Load, resolve and validate a scene file.

    Components (``use:`` blocks) are expanded, relative asset paths are
    resolved against the scene file directory and ``fonts/`` prefixed
    font paths against the shared font library.

    Args:
        path: Path to the scene YAML file.
        fonts_dir: Shared font library directory; ``None`` keeps legacy
            scene-relative resolution for ``fonts/`` paths.

    Returns:
        Validated scene document with one section per device.

    Raises:
        SceneError: If the file cannot be read/parsed or validation fails.
    """
    path = path.expanduser().resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SceneError(f"Cannot read scene file {path}: {exc}") from exc
    return load_scene_from_text(
        text, path.parent, source_name=path.name, fonts_dir=fonts_dir
    )


def load_scene_from_text(
    text: str,
    base_dir: Path,
    source_name: str = "scene.yaml",
    fonts_dir: Path | None = None,
) -> SceneDocument:
    """Parse, resolve and validate a scene file from YAML text.

    Args:
        text: Raw YAML scene source (one section per device).
        base_dir: Directory used to resolve relative asset, font and
            component paths.
        source_name: Scene file name used in error messages.
        fonts_dir: Shared font library directory for ``fonts/`` prefixed
            ``style.family`` values; ``None`` keeps scene-relative.

    Returns:
        Validated scene document.

    Raises:
        SceneError: If the text cannot be parsed or validation fails.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SceneError(f"Invalid YAML in {source_name}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SceneError(f"Scene root must be a mapping, got {type(raw).__name__}")

    raw_screen = raw.get("screen")
    if raw_screen is not None:
        if not isinstance(raw_screen, dict):
            raise SceneError("'screen' section must be a mapping")
        raw_screen["widgets"] = _expand_widgets(
            raw_screen.get("widgets") or [], base_dir, 0
        )
        raw_screen["background"] = _expand_background(
            raw_screen.get("background") or [], base_dir
        )

    try:
        document = SceneDocument.model_validate(raw)
    except Exception as exc:
        raise SceneError(f"Invalid scene {source_name}:\n{exc}") from exc

    screen = document.screen
    if screen is not None:
        for layer in screen.background:
            layer.path = str((base_dir / layer.path).resolve())
        for widget in screen.widgets:
            if (
                isinstance(widget, (ImageWidget, VideoWidget))
                and not Path(widget.path).is_absolute()
            ):
                widget.path = str((base_dir / widget.path).resolve())
            style = getattr(widget, "style", None)
            if style is not None:
                family = getattr(style, "family", None)
                if isinstance(family, str) and family != "":
                    style.family = _resolve_family(family, base_dir, fonts_dir)

    return document


def _resolve_family(family: str, base_dir: Path, fonts_dir: Path | None) -> str:
    """Resolve a text widget font path.

    Args:
        family: Font path as written in the YAML.
        base_dir: Scene directory for relative paths.
        fonts_dir: Shared font library for ``fonts/`` prefixed paths.

    Returns:
        Absolute font file path.
    """
    if family.startswith("fonts/") and fonts_dir is not None:
        return str((fonts_dir / family[len("fonts/") :]).resolve())
    if not Path(family).is_absolute():
        return str((base_dir / family).resolve())
    return family


def _expand_background(layers: list[Any], base_dir: Path) -> list[Any]:
    """Pass background layers through, validating their shape.

    Args:
        layers: Raw background list.
        base_dir: Scene directory (unused here, kept for symmetry).

    Returns:
        The raw list unchanged.

    Raises:
        SceneError: If the background entry is not a mapping.
    """
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise SceneError(f"background[{index}] must be a mapping")
    return layers


def _expand_widgets(widgets: list[Any], base_dir: Path, depth: int) -> list[Any]:
    """Expand ``use:`` component references into concrete widget mappings.

    Args:
        widgets: Raw widget list from the scene or a component.
        base_dir: Directory used to locate ``components/<name>.yaml``.
        depth: Current component nesting depth.

    Returns:
        List of plain widget mappings ready for validation.

    Raises:
        SceneError: If nesting is too deep, a component file is missing,
            or a referenced parameter is undefined.
    """
    if depth > _MAX_COMPONENT_DEPTH:
        raise SceneError("Component nesting too deep (possible recursion)")
    if not isinstance(widgets, list):
        raise SceneError("'widgets' must be a list")

    expanded: list[Any] = []
    for index, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            raise SceneError(f"widgets[{index}] must be a mapping")
        if "use" not in widget:
            expanded.append(widget)
            continue

        name = str(widget.pop("use"))
        component = _load_component(name, base_dir)
        params = component.get("params") or {}
        if not isinstance(params, dict):
            raise SceneError(f"Component {name!r}: 'params' must be a mapping")
        overrides = {k: v for k, v in widget.items() if k not in _RESERVED_KEYS}

        merged: dict[str, Any] = dict(params)
        for key, value in overrides.items():
            if key not in merged:
                raise SceneError(
                    f"Component {name!r}: unknown parameter {key!r}; "
                    f"declared: {sorted(merged)}"
                )
            merged[key] = value

        rendered = component.get("render")
        if not isinstance(rendered, list) or not rendered:
            raise SceneError(f"Component {name!r}: 'render' must be a non-empty list")

        at = widget.get("at") or [0, 0]
        if not isinstance(at, (list, tuple)) or len(at) != 2:
            raise SceneError(f"Component instance {name!r}: 'at' must be [x, y]")

        children = _substitute(rendered, merged)
        for child_index, child in enumerate(children):
            if not isinstance(child, dict):
                raise SceneError(
                    f"Component {name!r}: render[{child_index}] must be a mapping"
                )
            child = dict(child)
            child["rect"] = _shift_rect(child.get("rect"), int(at[0]), int(at[1]))
            for key in _OVERRIDE_KEYS:
                if key in widget and key not in child:
                    child[key] = widget[key]
            expanded.extend(_expand_widgets([child], base_dir, depth + 1))

    return expanded


def _load_component(name: str, base_dir: Path) -> dict[str, Any]:
    """Load a component definition file.

    Args:
        name: Component name; maps to ``components/<name>.yaml``.
        base_dir: Scene directory.

    Returns:
        Parsed component mapping.

    Raises:
        SceneError: If the file is missing or malformed.
    """
    component_path = base_dir / "components" / f"{name}.yaml"
    try:
        component = yaml.safe_load(component_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SceneError(f"Cannot load component {name!r}: {component_path}") from exc
    except yaml.YAMLError as exc:
        raise SceneError(f"Invalid YAML in component {name!r}: {exc}") from exc
    if not isinstance(component, dict):
        raise SceneError(f"Component {name!r} root must be a mapping")
    return component


def _substitute(node: Any, params: dict[str, Any]) -> Any:
    """Recursively substitute ``{{ param }}`` placeholders in a tree.

    A string that is exactly one placeholder keeps the parameter's native
    type (numbers stay numbers); mixed strings are interpolated.

    Args:
        node: Tree node (dict, list, str or scalar).
        params: Available parameters.

    Returns:
        Substituted tree.

    Raises:
        SceneError: If a referenced parameter is undefined.
    """
    if isinstance(node, str):
        full = _PLACEHOLDER.fullmatch(node.strip())
        if full:
            return _lookup(params, full.group(1))
        return _PLACEHOLDER.sub(
            lambda match: str(_lookup(params, match.group(1))), node
        )
    if isinstance(node, dict):
        return {key: _substitute(value, params) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute(item, params) for item in node]
    return node


def _lookup(params: dict[str, Any], path: str) -> Any:
    """Resolve a dotted parameter path.

    Args:
        params: Parameter mapping.
        path: Dotted path such as ``palette.fg``.

    Returns:
        The referenced value.

    Raises:
        SceneError: If the path cannot be resolved.
    """
    value: Any = params
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise SceneError(f"Undefined component parameter {path!r}")
    return value


def _shift_rect(rect: Any, dx: int, dy: int) -> list[int]:
    """Shift a widget rect by an instance offset.

    Args:
        rect: Raw rect value (list/tuple of 4 numbers).
        dx: X offset in pixels.
        dy: Y offset in pixels.

    Returns:
        Shifted rect as a list of 4 ints.

    Raises:
        SceneError: If the rect is malformed.
    """
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        raise SceneError(f"Invalid rect {rect!r}; expected [x, y, width, height]")
    x, y, width, height = (int(value) for value in rect)
    return [x + dx, y + dy, width, height]
