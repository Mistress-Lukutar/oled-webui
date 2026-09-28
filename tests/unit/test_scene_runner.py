"""
File:   test_scene_runner.py
Brief:  Integration tests for SceneRenderer rendering without a device.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oled_webui.core.models import Resolution
from oled_webui.scene.loader import load_scene
from oled_webui.scene.runner import SceneRenderer
from oled_webui.scene.schema import GraphWidget


@pytest.fixture(name="scene_file")
def scene_file_fixture(tmp_path: Path) -> Path:
    component = tmp_path / "components" / "gauge.yaml"
    component.parent.mkdir(parents=True)
    component.write_text(
        """
        params:
          source: cpu
          value: "{value:.0f}%"
          palette:
            fg: "#7CFC00"
            bg: "#222222"
        render:
          - type: ring
            rect: [0, 0, 120, 120]
            source: "{{ source }}"
            style:
              fg: "{{ palette.fg }}"
              bg: "{{ palette.bg }}"
          - type: text
            rect: [0, 40, 120, 60]
            align: center
            source: "{{ source }}"
            value: "{{ value }}"
        """,
        encoding="utf-8",
    )
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        refresh: 10.0
        max_fps: 30
        widgets:
          - use: gauge
            at: [20, 20]
            source: cpu
          - type: bar
            source: ram
            rect: [200, 40, 200, 20]
          - type: graph
            source: cpu
            rect: [200, 80, 200, 60]
          - type: text
            source: time.hms
            rect: [20, 180, 160, 40]
        """,
        encoding="utf-8",
    )
    return scene_path


def test_scene_renderer_yields_initial_frame(scene_file: Path) -> None:
    document = load_scene(scene_file)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))

    # First tick must produce the initial frame.
    payload = renderer.tick(now=0.0)
    assert payload is not None
    assert payload[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert renderer.size == (480, 480)

    # Identical inputs must not trigger a new frame.
    assert renderer.tick(now=0.01) is None


def test_scene_renderer_keeps_alive_when_unchanged(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        refresh: 0.1
        keepalive_interval: 0.5
        widgets:
          - type: text
            value: "static"
            rect: [20, 20, 120, 40]
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    renderer.tick(now=0.0)

    # No poll is due and nothing changed: no frame.
    assert renderer.tick(now=0.1) is None
    # Unchanged content plus elapsed keepalive interval must re-yield the
    # exact same cached payload.
    keepalive = renderer.tick(now=0.6)
    assert keepalive is not None
    assert keepalive[:2] == b"\xff\xd8"


def test_scene_renderer_yields_on_change(scene_file: Path) -> None:
    document = load_scene(scene_file)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    renderer.tick(now=0.0)

    # Simulate a new poll with changing metric values: the clock text and
    # graph history change on every poll, so the next tick must re-render.
    renderer._providers.poll()
    assert renderer.tick(now=0.5) is not None


def test_scene_renderer_grows_graph_history(scene_file: Path) -> None:
    """Each data poll appends a sample so the graph accumulates history."""
    document = load_scene(scene_file)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    graph_widget = next(
        w for w in document.widgets if isinstance(w, GraphWidget)
    )
    graph_runtime = renderer._runtimes[id(graph_widget)]

    renderer.tick(now=0.0)
    assert len(graph_runtime.history) == 1
    # refresh is 10 Hz, so a poll is due at now=0.2 and must add a sample.
    renderer.tick(now=0.2)
    assert len(graph_runtime.history) == 2
    renderer.tick(now=0.4)
    assert len(graph_runtime.history) == 3


def test_scene_renderer_background_layer(tmp_path: Path) -> None:
    from PIL import Image

    image_path = tmp_path / "wall.png"
    Image.new("RGB", (32, 32), (200, 0, 0)).save(image_path)
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        f"""
        background:
          - path: {image_path.as_posix()}
        widgets: []
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=64, height=64))
    assert renderer.tick(now=0.0) is not None


def test_missing_sprite_is_skipped(tmp_path: Path) -> None:
    """A broken image widget hides itself instead of failing the scene."""
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        widgets:
          - type: image
            path: assets/missing.png
            rect: [10, 10, 60, 60]
          - type: text
            value: "alive"
            rect: [10, 90, 100, 30]
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    payload = renderer.render_frame()
    assert payload[:2] == b"\xff\xd8"


def test_missing_background_layer_is_skipped(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        background:
          - path: assets/nope.png
        widgets:
          - type: text
            value: "alive"
            rect: [10, 10, 100, 30]
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    payload = renderer.render_frame()
    assert payload[:2] == b"\xff\xd8"


def test_preview_fills_graph_history(tmp_path: Path) -> None:
    """render_frame backfills sparse graph history with synthetic samples."""
    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        widgets:
          - type: graph
            source: cpu
            history: 60
            rect: [10, 10, 200, 60]
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    runtime = next(iter(renderer._runtimes.values()))
    payload = renderer.render_frame()
    assert payload[:2] == b"\xff\xd8"
    assert len(runtime.history) >= 2


def test_render_rotates_non_image_widget(tmp_path: Path) -> None:
    """Rotation applies to every widget type, not only images."""
    import io

    from PIL import Image

    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(
        """
        widgets:
          - type: text
            value: "####"
            rect: [240, 220, 200, 40]
            rotation: 90
            align: center
            style:
              size: 28
              color: "#FFFFFF"
        """,
        encoding="utf-8",
    )
    document = load_scene(scene_path)
    renderer = SceneRenderer(document, Resolution(width=480, height=480))
    frame = Image.open(io.BytesIO(renderer.render_frame())).convert("RGB")
    points = [
        (x, y)
        for y in range(frame.height)
        for x in range(frame.width)
        if all(channel > 120 for channel in frame.getpixel((x, y)))
    ]
    assert points, "rotated text left no visible ink"
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    ink_w = max(xs) - min(xs)
    ink_h = max(ys) - min(ys)
    # A wide horizontal label rotated 90° becomes a tall narrow one.
    assert ink_h > ink_w * 2
