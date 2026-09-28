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
from PIL import Image, ImageDraw, ImageOps

from oled_webui.exceptions import SceneError
from oled_webui.scene.schema import (
    AnimateSpec,
    BarStyle,
    BarWidget,
    GraphStyle,
    GraphWidget,
    ImageStyle,
    ImageWidget,
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
    render_image,
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
    widget = _bar_widget(progress_color="#FF0000", fill_color="#000000")
    render_bar(draw, (0, 0, 60, 30), 0.5, widget)
    pixels = image.load()
    assert pixels[29, 15][:3] == (255, 0, 0)  # filled half
    assert pixels[59, 15][:3] == (0, 0, 0)  # unfilled track


def test_render_bar_empty_and_full() -> None:
    for value01, expected in ((0.0, (0, 0, 0)), (1.0, (255, 0, 0))):
        image, draw = _scratch()
        render_bar(
            draw, (0, 0, 60, 30), value01, _bar_widget(progress_color="#FF0000", fill_color="#000000")
        )
        assert image.load()[2, 15][:3] == expected


@pytest.mark.parametrize(
    ("align", "border_rows"),
    (("inside", (2, 3)), ("center", (1, 2)), ("outside", (0, 1))),
)
def test_render_bar_border_align(
    align: str, border_rows: tuple[int, int]
) -> None:
    """A 2 px stroke shifts per stroke_align around the edge at y=2."""
    image, draw = _scratch(14, 14)
    widget = _bar_widget(
        stroke_width=2, stroke_color="#00FF00", fill_color="#0000FF", stroke_align=align
    )
    render_bar(draw, (2, 2, 10, 10), 0.0, widget)
    pixels = image.load()
    for row in border_rows:
        assert pixels[7, row][:3] == (0, 255, 0)
    assert pixels[7, border_rows[-1] + 1][:3] == (0, 0, 255)  # track below


def test_render_bar_border_visible_over_opaque_bg() -> None:
    """The track fill must not paint over the border."""
    image, draw = _scratch()
    widget = _bar_widget(stroke_width=2, stroke_color="#00FF00", fill_color="#0000FF")
    render_bar(draw, (0, 0, 60, 30), 0.0, widget)
    assert image.load()[30, 0][:3] == (0, 255, 0)


def test_render_ring_draws_arc() -> None:
    image, draw = _scratch(60, 60)
    widget = RingWidget(
        type="ring",
        source="cpu",
        rect=(0, 0, 60, 60),
        style=RingStyle(stroke_color="#00FF00", fill_color="#111111", stroke_width=6),
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
        style=GraphStyle(stroke_color="#00FF00", fill=False),
    )
    render_graph(draw, (0, 0, 100, 40), deque([10, 50, 90, 30]), widget)
    colors = {pixel[:3] for pixel in image.getdata()}
    assert (0, 255, 0) in colors


def test_render_text_draws_glyphs() -> None:
    image, _draw = _scratch(120, 40)
    widget = TextWidget(
        type="text",
        rect=(0, 0, 120, 40),
        align="center",
        style=TextStyle(fill_color="#FFFFFF"),
    )
    render_text(image, (0, 0, 120, 40), "42%", widget)
    assert any(pixel[3] > 0 for pixel in image.getdata())


def _text_widget(**style_kwargs: object) -> TextWidget:
    return TextWidget(
        type="text",
        rect=(0, 0, 80, 40),
        align="center",
        style=TextStyle(fill_color="#FFFFFF", **style_kwargs),  # type: ignore[arg-type]
    )


def test_render_text_rtl_is_mirror_of_ltr() -> None:
    ltr = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    rtl = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    render_text(ltr, (0, 0, 80, 40), "OK", _text_widget())
    render_text(rtl, (0, 0, 80, 40), "OK", _text_widget(direction="rtl"))
    assert list(rtl.getdata()) == list(ImageOps.mirror(ltr).getdata())


def test_render_text_ttb_stacks_vertically() -> None:
    image = Image.new("RGBA", (60, 140), (0, 0, 0, 0))
    render_text(image, (0, 0, 60, 140), "AB", _text_widget(direction="ttb"))
    bounds = image.getchannel("A").getbbox()
    assert bounds is not None
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    assert height > width * 2


def test_render_text_btt_is_flip_of_ttb() -> None:
    ttb = Image.new("RGBA", (60, 140), (0, 0, 0, 0))
    btt = Image.new("RGBA", (60, 140), (0, 0, 0, 0))
    render_text(ttb, (0, 0, 60, 140), "AB", _text_widget(direction="ttb"))
    render_text(btt, (0, 0, 60, 140), "AB", _text_widget(direction="btt"))
    assert list(btt.getdata()) == list(ImageOps.flip(ttb).getdata())


def test_render_text_leading_spreads_lines() -> None:
    def ink_height(leading: float) -> int:
        image = Image.new("RGBA", (60, 140), (0, 0, 0, 0))
        render_text(image, (0, 0, 60, 140), "A\nB", _text_widget(leading=leading))
        bounds = image.getchannel("A").getbbox()
        assert bounds is not None
        return bounds[3] - bounds[1]

    assert ink_height(3.0) > ink_height(1.0) + 20


def test_render_text_tracking_widens_text() -> None:
    def ink_width(tracking: int) -> int:
        image = Image.new("RGBA", (160, 40), (0, 0, 0, 0))
        render_text(image, (0, 0, 160, 40), "WW", _text_widget(tracking=tracking))
        bounds = image.getchannel("A").getbbox()
        assert bounds is not None
        return bounds[2] - bounds[0]

    assert ink_width(8) >= ink_width(0) + 8


def test_render_text_stroke_expands_ink() -> None:
    plain = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    stroked = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
    render_text(plain, (0, 0, 120, 40), "OK", _text_widget())
    render_text(
        stroked,
        (0, 0, 120, 40),
        "OK",
        _text_widget(stroke_width=2, stroke_color="#FF0000"),
    )
    plain_bounds = plain.getchannel("A").getbbox()
    stroked_bounds = stroked.getchannel("A").getbbox()
    assert plain_bounds is not None and stroked_bounds is not None
    assert stroked_bounds[2] - stroked_bounds[0] > plain_bounds[2] - plain_bounds[0]
    assert any(pixel[:3] == (255, 0, 0) for pixel in stroked.getdata())


def test_animated_value_transitions() -> None:
    animator = AnimatedValue(AnimateSpec(easing="linear", duration=1000))
    assert animator.update(100.0, now=0.0) == 100.0
    # New target at t=1.5s starts a fresh 1s transition from the old value.
    assert animator.update(200.0, now=1.5) == pytest.approx(100.0)
    assert animator.update(200.0, now=2.0) == pytest.approx(150.0)
    assert animator.update(200.0, now=3.0) == pytest.approx(200.0)
    assert not animator.active


def _sprite(path, rgb=(200, 60, 60), size=(40, 20)):
    image = Image.new("RGB", size, rgb)
    image.save(path)
    return path


def _opaque_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    alpha = image.getchannel("A")
    return alpha.getbbox() or (0, 0, 0, 0)


def test_render_image_fit_modes(tmp_path) -> None:
    """contain fits inside the rect, stretch fills it, cover overflows."""
    from oled_webui.scene.schema import ImageWidget

    sprite_path = _sprite(tmp_path / "sprite.png", size=(40, 20))
    rect = (10, 10, 80, 80)  # square box, wide sprite

    for fit, expected in (("contain", (80, 40)), ("stretch", (80, 80)), ("cover", (80, 80))):
        layer = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        widget = ImageWidget(type="image", path=str(sprite_path), rect=rect, fit=fit)
        render_image(layer, rect, widget, opacity=1.0, rotation=0.0)
        bounds = _opaque_bounds(layer)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        assert (width, height) == expected, fit


def test_render_image_covers_layer_bounds(tmp_path) -> None:
    """Sprites extending past the layer are cropped, not crashing PIL."""
    from oled_webui.scene.schema import ImageWidget

    sprite_path = _sprite(tmp_path / "big.png", size=(100, 100))
    layer = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    widget = ImageWidget(
        type="image", path=str(sprite_path), rect=(0, 0, 200, 200), fit="scale", scale=3.0
    )
    render_image(layer, (0, 0, 200, 200), widget, opacity=1.0, rotation=0.0)
    assert _opaque_bounds(layer) == (0, 0, 60, 60)


def test_render_bar_fill_disabled_hides_track() -> None:
    image, draw = _scratch()
    widget = _bar_widget(progress_color="#FF0000", fill_color="#0000FF", fill=False)
    render_bar(draw, (0, 0, 60, 30), 0.5, widget)
    pixels = image.load()
    assert pixels[29, 15][:3] == (255, 0, 0)  # progress still drawn
    assert pixels[59, 15] == (0, 0, 0, 0)  # track area stays transparent


def test_render_ring_fill_toggle() -> None:
    def render(fill: bool) -> Image.Image:
        image, draw = _scratch(60, 60)
        widget = RingWidget(
            type="ring",
            source="cpu",
            rect=(0, 0, 60, 60),
            style=RingStyle(
                stroke_color="#00FF00", fill_color="#0000FF", fill=fill
            ),
        )
        render_ring(draw, (0, 0, 60, 60), 0.25, widget)
        return image

    # The 6 o'clock track arc is drawn only when fill is on.
    assert render(True).load()[30, 55][:3] == (0, 0, 255)
    assert render(False).load()[30, 55] == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("align", "top_row"), (("inside", 10), ("center", 7), ("outside", 4))
)
def test_render_ring_stroke_align(align: str, top_row: int) -> None:
    """A 6 px arc shifts per stroke_align around the circle top."""
    image, draw = _scratch(80, 80)
    widget = RingWidget(
        type="ring",
        source="cpu",
        rect=(10, 10, 60, 60),
        style=RingStyle(
            stroke_color="#00FF00",
            stroke_width=6,
            stroke_align=align,
            fill=False,
        ),
    )
    render_ring(draw, (10, 10, 60, 60), 0.25, widget)  # top-right quadrant
    assert image.load()[40, top_row][:3] == (0, 255, 0)


def test_render_text_fill_disabled_draws_outline_only() -> None:
    def render(fill: bool) -> Image.Image:
        image, _draw = _scratch(120, 60)
        widget = TextWidget(
            type="text",
            rect=(0, 0, 120, 60),
            align="center",
            style=TextStyle(
                size=48,
                fill=fill,
                fill_color="#FF0000",
                stroke_width=2,
                stroke_color="#00FF00",
            ),
        )
        render_text(image, (0, 0, 120, 60), "H", widget)
        return image

    def has_color(image: Image.Image, color: tuple[int, int, int]) -> bool:
        return any(pixel[:3] == color for pixel in image.getdata())

    assert has_color(render(True), (255, 0, 0))  # glyphs painted
    assert not has_color(render(False), (255, 0, 0))  # fill suppressed
    assert has_color(render(False), (0, 255, 0))  # outline still drawn


def test_render_image_draws_frame(tmp_path) -> None:
    sprite_path = _sprite(tmp_path / "framed.png")
    rect = (10, 10, 40, 20)
    layer = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    widget = ImageWidget(
        type="image",
        path=str(sprite_path),
        rect=rect,
        style=ImageStyle(
            stroke_width=2, stroke_color="#00FF00", stroke_align="outside"
        ),
    )
    render_image(layer, rect, widget, opacity=1.0, rotation=0.0)
    pixels = layer.load()
    # An outside frame sits just above the widget box top edge...
    assert pixels[30, 8][:3] == (0, 255, 0)
    # ...while the sprite stays untouched inside.
    assert pixels[30, 12][:3] == (200, 60, 60)


def test_render_image_rounds_corners(tmp_path) -> None:
    sprite_path = _sprite(tmp_path / "rounded.png")
    rect = (10, 10, 40, 20)
    layer = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
    widget = ImageWidget(
        type="image",
        path=str(sprite_path),
        rect=rect,
        style=ImageStyle(radius=8),
    )
    render_image(layer, rect, widget, opacity=1.0, rotation=0.0)
    assert layer.load()[10, 10][3] == 0  # corner masked away
    assert layer.load()[30, 20][3] == 255  # center stays opaque
