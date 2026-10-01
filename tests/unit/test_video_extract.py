"""
File:   test_video_extract.py
Brief:  Unit tests for the ffmpeg filter building and extraction pipeline.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import pytest

from luminaflowui.exceptions import VideoError
from luminaflowui.services.video_extract import (
    build_brightness_filter,
    build_filter_chain,
    build_fit_filter,
    build_rotation_filter,
    quality_to_qscale,
)


def test_quality_to_qscale_maps_inversely() -> None:
    """Higher quality maps to a lower (better) qscale, clamped to 2-31."""
    assert quality_to_qscale(100) == 2
    assert quality_to_qscale(95) < quality_to_qscale(50)
    assert quality_to_qscale(1) == 31


def test_build_fit_filter_contain_pads() -> None:
    """Contain scales down and letterboxes centered."""
    chain = build_fit_filter("contain", 1600, 720)
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=1600:720" in chain


def test_build_fit_filter_stretch_scales_exact() -> None:
    """Stretch resizes to the exact canvas without padding."""
    assert build_fit_filter("stretch", 1600, 720) == "scale=1600:720"


def test_build_fit_filter_width_height_crop() -> None:
    """Width and height modes fill the canvas and crop the overflow."""
    for mode in ("width", "height"):
        chain = build_fit_filter(mode, 1600, 720)
        assert "force_original_aspect_ratio=increase" in chain
        assert "crop=1600:720" in chain


def test_build_fit_filter_invalid() -> None:
    """Unknown fit modes raise VideoError."""
    with pytest.raises(VideoError):
        build_fit_filter("diagonal", 100, 50)


def test_build_rotation_filter_matches_pil_direction() -> None:
    """PIL rotates counter-clockwise; ffmpeg filters must match."""
    assert build_rotation_filter(0) == ""
    assert build_rotation_filter(90) == "transpose=2"  # CCW 90
    assert build_rotation_filter(180) == "hflip,vflip"
    assert build_rotation_filter(270) == "transpose=1"  # CCW 270
    assert "rotate=-45" in build_rotation_filter(45)


def test_build_brightness_filter_matches_pil_lut() -> None:
    """Brightness 100 is a no-op; others use the gamma-correct scale."""
    assert build_brightness_filter(100) == ""
    assert (
        build_brightness_filter(200)
        == "lutrgb=r=trunc(val*1.370351+0.5):g=trunc(val*1.370351+0.5)"
        ":b=trunc(val*1.370351+0.5)"
    )
    assert (
        build_brightness_filter(50)
        == "lutrgb=r=trunc(val*0.729740+0.5):g=trunc(val*0.729740+0.5)"
        ":b=trunc(val*0.729740+0.5)"
    )


def test_build_filter_chain_includes_base_rotation_and_420() -> None:
    """The chain applies the 180° base flip and always forces 4:2:0 output.

    Without the explicit yuvj420p, brightness processing routes through
    rgb24 and the mjpeg encoder emits 4:4:4 JPEGs the panel cannot decode.
    """
    plain = build_filter_chain("contain", 1600, 720, 0, 100)
    filters = plain.split(",")
    assert filters[0] == "hflip" and filters[1] == "vflip"  # base panel rotation
    assert "force_original_aspect_ratio=decrease" in plain
    assert filters[-1] == "format=yuvj420p"

    bright = build_filter_chain("contain", 1600, 720, 90, 150).split(",")
    assert bright[0] == "transpose=2"  # user rotation first
    assert bright[1] == "hflip" and bright[2] == "vflip"
    assert "lutrgb=" in ",".join(bright)
    assert bright[-1] == "format=yuvj420p"


def test_build_filter_chain_widget_mode_skips_rotation_and_brightness() -> None:
    """Scene video widgets omit the base rotation and brightness steps."""
    chain = build_filter_chain("contain", 100, 80, None, None)
    filters = chain.split(",")
    assert filters[-1] == "format=yuvj420p"
    assert "force_original_aspect_ratio=decrease" in chain
    assert "hflip" not in chain and "lutrgb" not in chain
