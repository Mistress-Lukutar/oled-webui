"""
File:   test_scene_loader.py
Brief:  Unit tests for scene loading and component expansion.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oled_webui.exceptions import SceneError
from oled_webui.scene.loader import load_scene
from oled_webui.scene.schema import BarWidget, RingWidget, ShapeWidget, TextWidget


def _write(tmp_path: Path, relative: str, content: str) -> Path:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_load_plain_scene(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - type: bar
            source: cpu
            rect: [10, 20, 100, 30]
        refresh: 2.0
        """,
    )
    document = load_scene(scene_path)
    assert document.refresh == 2.0
    assert isinstance(document.widgets[0], BarWidget)
    assert document.widgets[0].rect == (10, 20, 100, 30)


def test_font_library_prefix_resolution(tmp_path: Path) -> None:
    """'fonts/' family paths resolve against the shared font library."""
    library = tmp_path / "library"
    library.mkdir()
    scene_path = _write(
        tmp_path,
        "scenes/demo/scene.yaml",
        """
        widgets:
          - type: text
            source: time.hms
            rect: [0, 0, 100, 30]
            style:
              family: "fonts/Demo.ttf"
        """,
    )
    document = load_scene(scene_path, fonts_dir=library)
    widget = document.widgets[0]
    assert isinstance(widget, TextWidget)
    assert widget.style.family == str((library / "Demo.ttf").resolve())


def test_font_asset_stays_scene_relative(tmp_path: Path) -> None:
    """Non-library family paths still resolve against the scene directory."""
    scene_path = _write(
        tmp_path,
        "scenes/demo/scene.yaml",
        """
        widgets:
          - type: text
            source: time.hms
            rect: [0, 0, 100, 30]
            style:
              family: "assets/Local.ttf"
        """,
    )
    document = load_scene(scene_path, fonts_dir=tmp_path / "library")
    widget = document.widgets[0]
    assert isinstance(widget, TextWidget)
    assert widget.style.family == str(
        (tmp_path / "scenes" / "demo" / "assets" / "Local.ttf").resolve()
    )


def test_component_expansion_with_params(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "components/gauge.yaml",
        """
        params:
          source: cpu
          value: "{value:.1f}"
          palette:
            fg: "#00FF00"
        render:
          - type: ring
            rect: [0, 0, 160, 160]
            source: "{{ source }}"
            style:
              stroke_color: "{{ palette.fg }}"
          - type: text
            rect: [0, 0, 160, 160]
            align: center
            value: "{{ value }}"
        """,
    )
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - use: gauge
            at: [40, 50]
            source: ram
            value: "{value:.0f}%"        """,
    )
    document = load_scene(scene_path)
    ring, text = document.widgets
    assert isinstance(ring, RingWidget)
    assert ring.rect == (40, 50, 160, 160)
    assert ring.source == "ram"
    assert ring.style.stroke_color == "#00FF00"
    assert isinstance(text, TextWidget)
    assert text.value == "{value:.0f}%"


def test_component_unknown_param_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "components/gauge.yaml",
        """
        params:
          source: cpu
        render:
          - type: ring
            rect: [0, 0, 10, 10]
            source: "{{ source }}"
        """,
    )
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - use: gauge
            at: [0, 0]
            bogus: 1
        """,
    )
    with pytest.raises(SceneError, match="unknown parameter"):
        load_scene(scene_path)


def test_component_missing_file_raises(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - use: ghost
            at: [0, 0]
        """,
    )
    with pytest.raises(SceneError, match="ghost"):
        load_scene(scene_path)


def test_invalid_widget_type_raises(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - type: knob
            rect: [0, 0, 10, 10]
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        bogus_setting: true
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_relative_paths_resolved(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        background:
          - path: assets/wall.png
        widgets:
          - type: image
            path: sprites/dot.png
            rect: [0, 0, 10, 10]
        """,
    )
    document = load_scene(scene_path)
    assert document.background[0].path == str(tmp_path / "assets" / "wall.png")
    image_widget = document.widgets[0]
    assert image_widget.path == str(tmp_path / "sprites" / "dot.png")  # type: ignore[attr-defined]


def test_locked_instance_override_propagates(tmp_path: Path) -> None:
    """`locked` on a use: instance is an override, not a component param."""
    component = tmp_path / "components" / "badge.yaml"
    component.parent.mkdir(parents=True)
    component.write_text(
        """
        params:
          label: "x"
        render:
          - type: text
            rect: [0, 0, 80, 30]
            value: "{{ label }}"
        """,
        encoding="utf-8",
    )
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        widgets:
          - use: badge
            at: [10, 10]
            label: "hi"
            locked: true
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    assert len(document.widgets) == 1
    assert document.widgets[0].locked is True


def test_load_shape_widget(tmp_path: Path) -> None:
    """A shape widget loads with its paint style and kind."""
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - type: shape
            shape: rect
            rect: [0, 0, 100, 50]
            style:
              fill_color: "#FF0000"
              stroke_color: "#00FF00"
              stroke_width: 2
              radius: 4
        """,
    )
    document = load_scene(scene_path)
    widget = document.widgets[0]
    assert isinstance(widget, ShapeWidget)
    assert widget.shape == "rect"
    assert widget.style.fill_color == "#FF0000"
    assert widget.style.radius == 4
