"""
File:   test_scene_widgets.py
Brief:  Unit tests for widget renderers and value animation.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from collections import deque

import pytest
from PIL import Image, ImageDraw

from oled_webui.exceptions import SceneError
from oled_webui.scene.schema import (
    AnimateSpec,
    BarStyle,
    BarWidget,
    GraphStyle,
    GraphWidget,
    RingStyle,
    RingWidget,
    TextStyle,
    TextWidget,
)
from oled_webui.scene.widgets import (
    AnimatedValue,
    parse_color,
    render_bar,
    render_graph,
    render_ring,
    render_text,
)


def _scratch(
    width: int = 60, height: int = 30
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def test_parse_color_formats() -> None:
    assert parse_color("#FF0000") == (255, 0, 0, 255)
    assert parse_color("#0F0") == (0, 255, 0, 255)
    assert parse_color("#00000080")[3] == 128


def test_parse_color_invalid_raises() -> None:
    with pytest.raises(SceneError):
        parse_color("#12345")


def _bar_widget(**style_kwargs: object) -> BarWidget:
    return BarWidget(
        type="bar",
        source="cpu",
        rect=(0, 0, 60, 30),
        style=BarStyle(**style_kwargs),  # type: ignore[arg-type]
    )


def test_render_bar_fills_track() -> None:
    image, draw = _scratch()
    widget = _bar_widget(fg="#FF0000", bg="#000000")
    render_bar(draw, (0, 0, 60, 30), 0.5, widget)
    pixels = image.load()
    assert pixels[29, 15][:3] == (255, 0, 0)  # filled half
    assert pixels[59, 15][:3] == (0, 0, 0)  # unfilled track


def test_render_bar_empty_and_full() -> None:
    for value01, expected in ((0.0, (0, 0, 0)), (1.0, (255, 0, 0))):
        image, draw = _scratch()
        render_bar(
            draw, (0, 0, 60, 30), value01, _bar_widget(fg="#FF0000", bg="#000000")
        )
        assert image.load()[2, 15][:3] == expected


def test_render_ring_draws_arc() -> None:
    image, draw = _scratch(60, 60)
    widget = RingWidget(
        type="ring",
        source="cpu",
        rect=(0, 0, 60, 60),
        style=RingStyle(fg="#00FF00", bg="#111111", width=6),
    )
    render_ring(draw, (0, 0, 60, 60), 1.0, widget)
    center = image.load()[30, 4]
    assert center[:3] == (0, 255, 0)


def test_render_graph_draws_line() -> None:
    image, draw = _scratch(100, 40)
    widget = GraphWidget(
        type="graph",
        source="cpu",
        rect=(0, 0, 100, 40),
        style=GraphStyle(fg="#00FF00", fill=False),
    )
    render_graph(draw, (0, 0, 100, 40), deque([10, 50, 90, 30]), widget)
    colors = {pixel[:3] for pixel in image.getdata()}
    assert (0, 255, 0) in colors


def test_render_text_draws_glyphs() -> None:
    image, draw = _scratch(120, 40)
    widget = TextWidget(
        type="text",
        rect=(0, 0, 120, 40),
        align="center",
        style=TextStyle(color="#FFFFFF"),
    )
    render_text(draw, (0, 0, 120, 40), "42%", widget)
    assert any(pixel[3] > 0 for pixel in image.getdata())


def test_animated_value_transitions() -> None:
    animator = AnimatedValue(AnimateSpec(easing="linear", duration=1000))
    assert animator.update(100.0, now=0.0) == 100.0
    # New target at t=1.5s starts a fresh 1s transition from the old value.
    assert animator.update(200.0, now=1.5) == pytest.approx(100.0)
    assert animator.update(200.0, now=2.0) == pytest.approx(150.0)
    assert animator.update(200.0, now=3.0) == pytest.approx(200.0)
    assert not animator.active
