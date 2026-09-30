"""
File:   test_frame_builder.py
Brief:  Unit tests for the render pipeline and text rendering.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import pytest
from PIL import Image

from oled_webui.exceptions import RenderError
from oled_webui.services.frame_builder import (
    FrameBuilder,
    brightness_lut,
    build_black_frame,
    parse_hex_color,
)


def test_parse_hex_color() -> None:
    """Both #RRGGBB and RRGGBB forms parse into RGB tuples."""
    assert parse_hex_color("#ff0000") == (255, 0, 0)
    assert parse_hex_color("00FF00") == (0, 255, 0)
    assert parse_hex_color(" #0000ff ") == (0, 0, 255)


def test_parse_hex_color_invalid() -> None:
    """Malformed colors raise RenderError."""
    with pytest.raises(RenderError):
        parse_hex_color("red")
    with pytest.raises(RenderError):
        parse_hex_color("#12345")


def _builder(**kwargs: object) -> FrameBuilder:
    return FrameBuilder(width=100, height=50, **kwargs)  # type: ignore[arg-type]


def test_fit_stretch_exact_size() -> None:
    """Stretch resizes to the exact canvas dimensions."""
    image = Image.new("RGB", (30, 30), (255, 0, 0))
    result = _builder(fit="stretch").fit_image(image)
    assert result.size == (100, 50)


def test_fit_contain_preserves_aspect() -> None:
    """Contain letterboxes the image centered on a black canvas."""
    image = Image.new("RGB", (50, 25), (255, 0, 0))
    result = _builder(fit="contain").fit_image(image)
    assert result.size == (100, 50)
    assert result.getpixel((5, 5)) == (0, 0, 0)  # letterbox
    assert result.getpixel((50, 25)) == (255, 0, 0)  # center


def test_fit_width_pads_to_canvas() -> None:
    """Width mode scales to full width and pads to canvas height."""
    image = Image.new("RGB", (50, 25), (255, 0, 0))
    result = _builder(fit="width").fit_image(image)
    assert result.size == (100, 50)


def test_brightness_scaling() -> None:
    """Brightness scales in linear light: 50 % -> ~0.73 of encoded levels."""
    gray = Image.new("RGB", (4, 4), (100, 100, 100))
    dark = _builder(brightness=50).apply_brightness(gray)
    assert dark.getpixel((0, 0)) == (73, 73, 73)

    bright = _builder(brightness=200).apply_brightness(
        Image.new("RGB", (4, 4), (200, 200, 200))
    )
    assert bright.getpixel((0, 0)) == (255, 255, 255)


def test_brightness_lut_preserves_dark_levels() -> None:
    """Low settings keep dark values distinct instead of crushing to black.

    The old truncating linear LUT mapped everything below 10 to black at
    10 % brightness; the gamma-correct rounded LUT only loses value 1.
    """
    lut = brightness_lut(10)
    assert lut[0] == 0  # black stays black (OLED benefit)
    assert lut[1] == 0
    assert lut[2] == 1
    assert lut[9] == 3
    assert lut == sorted(lut)  # monotonic, so tones stay ordered

    lut50 = brightness_lut(50)
    assert lut50[255] == 186  # 255 * 0.5**(1/2.2)
    assert lut50[128] == 93
    assert lut50[0] == 0

    over = brightness_lut(200)
    assert over[255] == 255  # clamped
    assert over[128] == 175


def test_brightness_zero_and_100_passthrough() -> None:
    """0 % yields black, 100 % returns the image unchanged."""
    image = Image.new("RGB", (4, 4), (80, 160, 240))
    assert _builder(brightness=0).apply_brightness(image).getpixel((0, 0)) == (
        0,
        0,
        0,
    )
    untouched = _builder(brightness=100).apply_brightness(image)
    assert untouched is image


def test_apply_base_rotation_flips_without_resize() -> None:
    """The 180° base rotation flips the image but keeps its dimensions."""
    image = Image.new("RGB", (10, 6), (255, 0, 0))
    rotated = _builder().apply_base_rotation(image)
    assert rotated.size == (10, 6)


def test_source_size_swapped_for_quarter_turns() -> None:
    """Quarter-turn rotations request a transposed pre-rotation canvas."""
    assert _builder(rotation=0).source_size == (100, 50)
    assert _builder(rotation=90).source_size == (50, 100)
    assert _builder(rotation=180).source_size == (100, 50)
    assert _builder(rotation=270).source_size == (50, 100)


def test_build_frame_quarter_turn_fills_canvas() -> None:
    """A rotated portrait image is fitted to the full panel canvas."""
    portrait = Image.new("RGB", (25, 100), (255, 0, 0))
    frame = _builder(rotation=90).build_frame(portrait)
    assert frame.size == (100, 50)


def test_rotated_text_pipeline_lands_on_panel_size() -> None:
    """Rotated text renders on a transposed canvas, then lands panel-sized."""
    builder = _builder(rotation=90)
    canvas = builder.render_text_frame("HELLO", font_size=24)
    assert canvas.size == (50, 100)
    frame = builder.apply_user_rotation(canvas)
    frame = builder.apply_base_rotation(frame)
    assert frame.size == (100, 50)


def test_build_color_image_applies_brightness() -> None:
    """Solid color images honor the brightness setting."""
    result = _builder(brightness=100).build_color_image((255, 255, 255))
    assert result.getpixel((0, 0)) == (255, 255, 255)
    dark = _builder(brightness=50).build_color_image((255, 255, 255))
    assert dark.getpixel((0, 0)) == (186, 186, 186)


def test_render_text_frame_draws_pixels() -> None:
    """Text rendering produces visible non-background pixels."""
    builder = _builder()
    frame = builder.render_text_frame("HELLO", font_size=24)
    assert frame.size == (100, 50)
    colors = frame.getcolors(maxcolors=100000)
    assert colors is not None and len(colors) > 1  # more than background only


def test_render_text_frame_invalid_align() -> None:
    """Invalid alignment values raise RenderError."""
    with pytest.raises(RenderError):
        _builder().render_text_frame("x", align="diagonal")


def test_encode_jpeg_magic() -> None:
    """Encoded frames start with the JPEG SOI marker."""
    payload = _builder().encode_jpeg(build_black_frame(32, 32))
    assert payload[:2] == b"\xff\xd8"
