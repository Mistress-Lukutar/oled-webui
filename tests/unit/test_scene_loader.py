"""
File:   test_scene_loader.py
Brief:  Unit tests for scene file loading and component expansion.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oled_webui.argb.schema import ArgbLayout, FillEffect
from oled_webui.exceptions import SceneError
from oled_webui.scene.loader import load_scene
from oled_webui.scene.schema import (
    BarWidget,
    RingWidget,
    SceneDocument,
    ScreenDocument,
    ShapeWidget,
    TextWidget,
    VideoWidget,
)


def _write(tmp_path: Path, relative: str, content: str) -> Path:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_load_plain_screen_section(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen:
          widgets:
            - type: bar
              source: cpu
              rect: [10, 20, 100, 30]
          refresh: 2.0
        """,
    )
    document = load_scene(scene_path)
    screen = document.screen
    assert screen is not None
    assert screen.refresh == 2.0
    assert isinstance(screen.widgets[0], BarWidget)
    assert screen.widgets[0].rect == (10, 20, 100, 30)
    assert document.argb is None


def test_load_argb_only_scene(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        argb:
          fps: 45
          brightness: 80
          headers: []
          devices: []
          layers: []
        """,
    )
    document = load_scene(scene_path)
    assert document.screen is None
    argb = document.argb
    assert argb is not None
    assert argb.fps == 45
    assert argb.brightness == 80


def test_scene_without_sections_rejected(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        refresh: 2.0
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_empty_scene_rejected(tmp_path: Path) -> None:
    scene_path = _write(tmp_path, "scene.yaml", "{}\n")
    with pytest.raises(SceneError, match="at least one device section"):
        load_scene(scene_path)


def test_unknown_device_section_rejected(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        holoprojector:
          power: 1
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_legacy_top_level_widgets_rejected(tmp_path: Path) -> None:
    """Old-format scenes (widgets at the root) fail loudly, no compat shim."""
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        widgets:
          - type: bar
            source: cpu
            rect: [10, 20, 100, 30]
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_mixed_sections_load(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen:
          widgets:
            - type: text
              value: hi
              rect: [0, 0, 100, 30]
        argb:
          headers:
            - id: h1
              zone_index: 0
              devices: [d1]
          devices:
            - id: d1
              device: strip
              header_id: h1
          layers:
            - id: l1
              effect:
                type: fill
                color: "#112233"
        """,
    )
    document = load_scene(scene_path)
    assert isinstance(document.screen, ScreenDocument)
    assert isinstance(document.argb, ArgbLayout)
    assert document.argb.layers[0].effect == FillEffect(type="fill", color="#112233")


def test_font_library_prefix_resolution(tmp_path: Path) -> None:
    """'fonts/' family paths resolve against the shared font library."""
    library = tmp_path / "library"
    library.mkdir()
    scene_path = _write(
        tmp_path,
        "scenes/demo/scene.yaml",
        """
        screen:
          widgets:
            - type: text
              source: time.hms
              rect: [0, 0, 100, 30]
              style:
                family: "fonts/Demo.ttf"
        """,
    )
    document = load_scene(scene_path, fonts_dir=library)
    widget = document.screen.widgets[0]  # type: ignore[union-attr]
    assert isinstance(widget, TextWidget)
    assert widget.style.family == str((library / "Demo.ttf").resolve())


def test_font_asset_stays_scene_relative(tmp_path: Path) -> None:
    """Non-library family paths still resolve against the scene directory."""
    scene_path = _write(
        tmp_path,
        "scenes/demo/scene.yaml",
        """
        screen:
          widgets:
            - type: text
              source: time.hms
              rect: [0, 0, 100, 30]
              style:
                family: "assets/Local.ttf"
        """,
    )
    document = load_scene(scene_path, fonts_dir=tmp_path / "library")
    widget = document.screen.widgets[0]  # type: ignore[union-attr]
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
        screen:
          widgets:
            - use: gauge
              at: [40, 50]
              source: ram
              value: "{value:.0f}%"
        """,
    )
    document = load_scene(scene_path)
    widgets = document.screen.widgets  # type: ignore[union-attr]
    ring, text = widgets
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
        screen:
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
        screen:
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
        screen:
          widgets:
            - type: knob
              rect: [0, 0, 10, 10]
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_unknown_section_key_rejected(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen:
          widgets: []
        argb: []
        """,
    )
    with pytest.raises(SceneError):
        load_scene(scene_path)


def test_relative_paths_resolved(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen:
          background:
            - path: assets/wall.png
          widgets:
            - type: image
              path: sprites/dot.png
              rect: [0, 0, 10, 10]
        """,
    )
    document = load_scene(scene_path)
    screen = document.screen
    assert screen is not None
    assert screen.background[0].path == str(tmp_path / "assets" / "wall.png")
    image_widget = screen.widgets[0]
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
        screen:
          widgets:
            - use: badge
              at: [10, 10]
              label: "hi"
              locked: true
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    assert len(document.screen.widgets) == 1  # type: ignore[union-attr]
    assert document.screen.widgets[0].locked is True  # type: ignore[union-attr]


def test_load_shape_widget(tmp_path: Path) -> None:
    """A shape widget loads with its paint style and kind."""
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen:
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
    widget = document.screen.widgets[0]  # type: ignore[union-attr]
    assert isinstance(widget, ShapeWidget)
    assert widget.shape == "rect"
    assert widget.style.fill_color == "#FF0000"
    assert widget.style.radius == 4


def test_load_video_widget_resolves_path(tmp_path: Path) -> None:
    """A video widget loads and its path resolves against the scene dir."""
    scene_path = _write(
        tmp_path,
        "scenes/demo/scene.yaml",
        """
        screen:
          widgets:
            - type: video
              path: assets/clip.mp4
              rect: [0, 0, 200, 100]
              fps: 12
              loop: false
              start: 1.5
        """,
    )
    document = load_scene(scene_path)
    widget = document.screen.widgets[0]  # type: ignore[union-attr]
    assert isinstance(widget, VideoWidget)
    assert widget.fps == 12 and widget.loop is False and widget.start == 1.5
    assert widget.path == str((tmp_path / "scenes/demo/assets/clip.mp4").resolve())


def test_screen_section_must_be_mapping(tmp_path: Path) -> None:
    scene_path = _write(
        tmp_path,
        "scene.yaml",
        """
        screen: []
        """,
    )
    with pytest.raises(SceneError, match="mapping"):
        load_scene(scene_path)


def test_root_model_direct_validation() -> None:
    document = SceneDocument(screen=ScreenDocument())
    assert document.screen is not None
    assert document.argb is None
