"""
File:   test_argb_schema.py
Brief:  Validation tests for the ARGB layout schema.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.1.0
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
            ArgbDevice(
                id="d1", type="strip", header_id="h1", leds=10, x=0, y=0
            )
        ],
        "layers": [ArgbLayer(id="l1", effect={"type": "fill", "color": "#FF0000"})],
    }
    payload.update(overrides)
    return ArgbLayout(**payload)  # type: ignore[arg-type]


def test_default_layout_is_valid() -> None:
    """The starter layout validates and has one chained device."""
    layout = default_layout()
    assert layout.devices[0].total_leds == 24
    assert layout.headers[0].devices == ["d1"]


def test_unknown_keys_are_rejected() -> None:
    """Extra keys raise a validation error, mirroring scene schema."""
    with pytest.raises(ValidationError):
        ArgbDevice(
            id="d1",
            type="strip",
            header_id="h1",
            leds=1,
            x=0,
            y=0,
            bogus=1,  # type: ignore[call-arg]
        )


def test_bad_color_pattern_rejected() -> None:
    """Colors must be #RRGGBB or #RRGGBBAA hex strings."""
    with pytest.raises(ValidationError):
        ArgbLayer(id="l1", effect={"type": "fill", "color": "red"})


def test_ring_stripes_total_leds() -> None:
    """ring_stripes counts the ring plus both side stripes."""
    device = ArgbDevice(
        id="d",
        type="ring_stripes",
        header_id="h1",
        leds=24,
        leds_side=8,
        x=0,
        y=0,
    )
    assert device.total_leds == 40


def test_ring_stripes_requires_side_leds() -> None:
    """ring_stripes without side LEDs is rejected."""
    with pytest.raises(ValidationError):
        _layout(
            devices=[
                ArgbDevice(
                    id="d1",
                    type="ring_stripes",
                    header_id="h1",
                    leds=12,
                    leds_side=0,
                    x=0,
                    y=0,
                )
            ]
        )


def test_chain_overflow_rejected() -> None:
    """A chain needing more LEDs than the zone provides is rejected."""
    with pytest.raises(ValidationError, match="chain needs"):
        _layout(headers=[ArgbHeader(id="h1", zone_index=0, size=8, devices=["d1"])])


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
                ArgbDevice(id="d1", type="strip", header_id="h2", leds=4, x=0, y=0)
            ],
        )


def test_mask_run_out_of_range_rejected() -> None:
    """Mask runs beyond the device LED count are rejected."""
    layer = ArgbLayer(
        id="l1",
        effect={"type": "fill"},
        mask=MaskSpec(all=False, runs={"d1": [(0, 99)]}),
    )
    with pytest.raises(ValidationError, match="out of range"):
        _layout(layers=[layer])


def test_mask_run_inverted_rejected() -> None:
    """Mask runs with start > end are rejected."""
    layer = ArgbLayer(
        id="l1",
        effect={"type": "fill"},
        mask=MaskSpec(all=False, runs={"d1": [(5, 2)]}),
    )
    with pytest.raises(ValidationError, match="inverted"):
        _layout(layers=[layer])


def test_duplicate_ids_rejected() -> None:
    """Duplicate device, header or layer ids are rejected."""
    with pytest.raises(ValidationError, match="Duplicate device"):
        _layout(
            devices=[
                ArgbDevice(id="d1", type="strip", header_id="h1", leds=4, x=0, y=0),
                ArgbDevice(id="d1", type="strip", header_id="h1", leds=4, x=9, y=9),
            ]
        )


def test_unknown_effect_type_rejected() -> None:
    """The effect union discriminates on type and rejects unknown kinds."""
    with pytest.raises(ValidationError):
        ArgbLayer(id="l1", effect={"type": "laser"})
