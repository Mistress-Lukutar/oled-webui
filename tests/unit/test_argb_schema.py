"""
File:   test_argb_schema.py
Brief:  Validation tests for the ARGB layout schema.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.2.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from oled_webui.argb.schema import (
    ArgbDevice,
    ArgbHeader,
    ArgbLayer,
    ArgbLayout,
    MaskSpec,
    default_layout,
)


def _layout(**overrides: object) -> ArgbLayout:
    """Build a minimal valid layout with optional overrides."""
    payload: dict[str, object] = {
        "headers": [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        "devices": [
            ArgbDevice(id="d1", device="strip", header_id="h1", x=0, y=0)
        ],
        "layers": [ArgbLayer(id="l1", effect={"type": "fill", "color": "#FF0000"})],
    }
    payload.update(overrides)
    return ArgbLayout(**payload)  # type: ignore[arg-type]


def test_default_layout_is_valid() -> None:
    """The starter layout validates and references the strip definition."""
    layout = default_layout()
    assert layout.devices[0].device == "strip"
    assert layout.headers[0].devices == ["d1"]


def test_unknown_keys_are_rejected() -> None:
    """Extra keys raise a validation error, mirroring scene schema."""
    with pytest.raises(ValidationError):
        ArgbDevice(
            id="d1",
            device="strip",
            header_id="h1",
            x=0,
            y=0,
            leds=5,  # type: ignore[call-arg]
            bogus=1,  # type: ignore[call-arg]
        )


def test_bad_color_pattern_rejected() -> None:
    """Colors must be #RRGGBB or #RRGGBBAA hex strings."""
    with pytest.raises(ValidationError):
        ArgbLayer(id="l1", effect={"type": "fill", "color": "red"})


def test_unknown_device_reference_rejected() -> None:
    """Headers may not reference devices that do not exist."""
    with pytest.raises(ValidationError, match="unknown device"):
        _layout(headers=[ArgbHeader(id="h1", zone_index=0, devices=["ghost"])])


def test_device_on_two_headers_rejected() -> None:
    """One device cannot hang on two header chains."""
    headers = [
        ArgbHeader(id="h1", zone_index=0, devices=["d1"]),
        ArgbHeader(id="h2", zone_index=1, devices=["d1"]),
    ]
    with pytest.raises(ValidationError, match="more than one header"):
        _layout(headers=headers)


def test_device_must_be_chained() -> None:
    """Every device must appear in some header's devices list."""
    with pytest.raises(ValidationError, match="not chained"):
        _layout(headers=[ArgbHeader(id="h1", zone_index=0, devices=[])])


def test_header_mismatch_rejected() -> None:
    """Device header_id must match the header chaining it."""
    with pytest.raises(ValidationError, match="declares header"):
        _layout(
            headers=[ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
            devices=[
                ArgbDevice(id="d1", device="strip", header_id="h2", x=0, y=0)
            ],
        )


def test_mask_unknown_device_rejected() -> None:
    """Masks may only reference devices that exist in the layout."""
    layer = ArgbLayer(
        id="l1",
        effect={"type": "fill"},
        mask=MaskSpec(all=False, runs={"ghost": [(0, 1)]}),
    )
    with pytest.raises(ValidationError, match="unknown device"):
        _layout(layers=[layer])


def test_duplicate_ids_rejected() -> None:
    """Duplicate device, header or layer ids are rejected."""
    with pytest.raises(ValidationError, match="Duplicate device"):
        _layout(
            devices=[
                ArgbDevice(id="d1", device="strip", header_id="h1", x=0, y=0),
                ArgbDevice(id="d1", device="strip", header_id="h1", x=9, y=9),
            ]
        )


def test_unknown_effect_type_rejected() -> None:
    """The effect union discriminates on type and rejects unknown kinds."""
    with pytest.raises(ValidationError):
        ArgbLayer(id="l1", effect={"type": "laser"})
