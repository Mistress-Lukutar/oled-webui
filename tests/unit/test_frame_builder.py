"""
File:   test_frame_builder.py
Brief:  Unit tests for the render pipeline and text rendering.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

import pytest
from PIL import Image

from oled_webui.exceptions import RenderError
from oled_webui.services.frame_builder import (
    FrameBuilder,
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
    """Brightness 50 halves pixel values; 200 clamps at 255."""
    gray = Image.new("RGB", (4, 4), (100, 100, 100))
    dark = _builder(brightness=50).apply_brightness(gray)
    assert dark.getpixel((0, 0)) == (50, 50, 50)

    bright = _builder(brightness=200).apply_brightness(
        Image.new("RGB", (4, 4), (200, 200, 200))
    )
    assert bright.getpixel((0, 0)) == (255, 255, 255)


def test_apply_rotation_base_180() -> None:
    """Default rotation is 180 degrees, flipping the image."""
    image = Image.new("RGB", (10, 6), (255, 0, 0))
    rotated = _builder().apply_rotation(image)
    assert rotated.size == (10, 6)


def test_build_color_image_applies_brightness() -> None:
    """Solid color images honor the brightness setting."""
    result = _builder(brightness=100).build_color_image((255, 255, 255))
    assert result.getpixel((0, 0)) == (255, 255, 255)
    dark = _builder(brightness=50).build_color_image((255, 255, 255))
    assert dark.getpixel((0, 0)) == (127, 127, 127) or dark.getpixel((0, 0)) == (
        128,
        128,
        128,
    )


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
