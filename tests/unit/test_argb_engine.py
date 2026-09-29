"""
File:   test_argb_engine.py
Brief:  Effect math tests for the pure ARGB engine.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.1.0
"""

from __future__ import annotations

from typing import Any

from oled_webui.argb.engine import parse_rgba, render_layout
from oled_webui.argb.schema import (
    ArgbDevice,
    ArgbHeader,
    ArgbLayer,
    ArgbLayout,
    MaskSpec,
)

WHITE = (255, 255, 255)

# LED counts recorded by the _strip factory; the engine takes them as an
# argument now that instances reference device definitions.
_COUNTS: dict[str, int] = {}


def _layout(
    devices: list[ArgbDevice],
    headers: list[ArgbHeader],
    layers: list[ArgbLayer],
) -> ArgbLayout:
    """Assemble a layout from parts."""
    return ArgbLayout(headers=headers, devices=devices, layers=layers)


def _strip(device_id: str, header_id: str, leds: int) -> ArgbDevice:
    """Make a strip device and remember its LED count."""
    _COUNTS[device_id] = leds
    return ArgbDevice(
        id=device_id, device="test-def", header_id=header_id, x=0, y=0
    )


def _render(
    layout: ArgbLayout, t: float = 0.0, samples: dict[str, float] | None = None
) -> dict[str, bytearray]:
    """Render with the counts recorded so far."""
    return render_layout(layout, t, samples, dict(_COUNTS))


def _fill_layer(color: str, **kwargs: Any) -> ArgbLayer:
    """Make a fill layer."""
    return ArgbLayer(id="l", effect={"type": "fill", "color": color}, **kwargs)


def _pixel(buf: bytearray, index: int) -> tuple[int, int, int]:
    """Read one LED color from a packed buffer."""
    return buf[index * 3], buf[index * 3 + 1], buf[index * 3 + 2]


def test_parse_rgba() -> None:
    """Hex colors parse with and without alpha."""
    assert parse_rgba("#FF8000") == (255, 128, 0, 1.0)
    assert parse_rgba("FF800080") == (255, 128, 0, 128 / 255)


def test_fill_covers_chain() -> None:
    """A plain fill lights every LED of every device."""
    layout = _layout(
        [_strip("d1", "h1", 4)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [_fill_layer("#102030")],
    )
    buf = _render(layout, 0.0)["h1"]
    assert len(buf) == 12
    assert _pixel(buf, 0) == (0x10, 0x20, 0x30)
    assert _pixel(buf, 3) == (0x10, 0x20, 0x30)


def test_two_devices_share_header_offset() -> None:
    """Devices chain up sequentially on one header buffer."""
    devices = [_strip("d1", "h1", 2), _strip("d2", "h1", 3)]
    layout = _layout(
        devices,
        [ArgbHeader(id="h1", zone_index=0, devices=["d1", "d2"])],
        [_fill_layer("#010203")],
    )
    buf = _render(layout, 0.0)["h1"]
    assert len(buf) == 15
    for led in range(5):
        assert _pixel(buf, led) == (1, 2, 3)


def test_alpha_blending_makes_purple() -> None:
    """Blue fill + 50%-opacity red comet layer blends toward purple."""
    comet = ArgbLayer(
        id="l2",
        effect={
            "type": "comet",
            "color": "#FF0000",
            "tail": 0,
            "speed": 0.0,
            "mode": "loop",
        },
        opacity=0.5,
    )
    layout = _layout(
        [_strip("d1", "h1", 3)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [_fill_layer("#0000FF"), comet],
    )
    buf = _render(layout, 0.0)["h1"]
    # Head sits at chain index 0 at t=0: 0.5*255 red over 0 blue.
    assert _pixel(buf, 0) == (128, 0, 128)
    # Untouched pixels stay pure blue.
    assert _pixel(buf, 1) == (0, 0, 255)


def test_mask_limits_fill() -> None:
    """A masked fill only lights the selected index runs."""
    layer = _fill_layer(
        "#FFFFFF", mask=MaskSpec(all=False, runs={"d1": [(1, 2)]})
    )
    layout = _layout(
        [_strip("d1", "h1", 4)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0)["h1"]
    assert _pixel(buf, 0) == (0, 0, 0)
    assert _pixel(buf, 1) == WHITE
    assert _pixel(buf, 2) == WHITE
    assert _pixel(buf, 3) == (0, 0, 0)


def test_disabled_layer_is_skipped() -> None:
    """Disabled layers do not contribute."""
    layer = _fill_layer("#FFFFFF", enabled=False)
    layout = _layout(
        [_strip("d1", "h1", 2)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0)["h1"]
    assert _pixel(buf, 0) == (0, 0, 0)


def test_gradient_scrolls_over_time() -> None:
    """Gradient static vs scroll: same place, different colors at t."""
    stops = [
        {"pos": 0.0, "color": "#000000"},
        {"pos": 1.0, "color": "#FFFFFF"},
    ]
    devices = [_strip("d1", "h1", 8)]
    headers = [ArgbHeader(id="h1", zone_index=0, devices=["d1"])]
    static = ArgbLayout(
        headers=headers,
        devices=devices,
        layers=[
            ArgbLayer(
                id="l",
                effect={
                    "type": "gradient",
                    "stops": stops,
                    "scale": 8,
                    "mode": "static",
                },
            )
        ],
    )
    scrolling = ArgbLayout(
        headers=headers,
        devices=[_strip("d1", "h1", 8)],
        layers=[
            ArgbLayer(
                id="l",
                effect={
                    "type": "gradient",
                    "stops": stops,
                    "scale": 8,
                    "mode": "scroll",
                    "speed": 0.25,
                },
            )
        ],
    )
    a = _render(static, 0.0)["h1"]
    b = _render(scrolling, 0.0)["h1"]
    assert _pixel(a, 4) == _pixel(b, 4)
    c = _render(scrolling, 2.0)["h1"]
    # Half a tile (4 LEDs) of scroll shift: LED 4 now shows LED 0's color.
    assert _pixel(c, 4) == _pixel(a, 0)


def test_rainbow_has_full_cycle() -> None:
    """Rainbow returns to the start hue after `scale` LEDs."""
    layer = ArgbLayer(id="l", effect={"type": "rainbow", "speed": 0.0, "scale": 8})
    layout = _layout(
        [_strip("d1", "h1", 9)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0)["h1"]
    assert _pixel(buf, 0) == _pixel(buf, 8)


def test_breathing_alpha_modulates() -> None:
    """Breathing at min and peak yields transparent vs full color."""
    layer = ArgbLayer(
        id="l",
        effect={
            "type": "breathing",
            "colors": ["#FF0000"],
            "period": 2.0,
            "min_level": 0.0,
        },
    )
    layout = _layout(
        [_strip("d1", "h1", 1)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    at_min = _render(layout, 0.0)["h1"]
    at_peak = _render(layout, 1.0)["h1"]
    assert _pixel(at_min, 0) == (0, 0, 0)
    assert _pixel(at_peak, 0)[0] > 250


def test_comet_loop_wraps_with_transparent_gap() -> None:
    """Comet head moves with t; the tail fades behind the head."""
    comet = ArgbLayer(
        id="l",
        effect={
            "type": "comet",
            "color": "#00FF00",
            "tail": 2,
            "speed": 1.0,
            "mode": "loop",
        },
    )
    layout = _layout(
        [_strip("d1", "h1", 6)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [comet],
    )
    # t=2 -> head at index 0 (it starts one tail-length before the chain).
    buf = _render(layout, 2.0)["h1"]
    assert _pixel(buf, 0) == (0, 255, 0)
    assert _pixel(buf, 5) == (0, 0, 0)
    # t=4 -> head at index 2, tail fading across 1 and 0.
    later = _render(layout, 4.0)["h1"]
    assert _pixel(later, 2) == (0, 255, 0)
    assert _pixel(later, 1) == (0, 170, 0)
    assert _pixel(later, 0) == (0, 85, 0)
    assert _pixel(later, 3) == (0, 0, 0)


def test_comet_bounce_reflects() -> None:
    """Bounce mode sends the head back from the far end."""
    comet = ArgbLayer(
        id="l",
        effect={
            "type": "comet",
            "color": "#FFFFFF",
            "tail": 0,
            "speed": 2.0,
            "mode": "bounce",
        },
    )
    layout = _layout(
        [_strip("d1", "h1", 5)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [comet],
    )
    start = _render(layout, 0.0)["h1"]
    far = _render(layout, 2.0)["h1"]
    assert _pixel(start, 0) == WHITE
    assert _pixel(far, 4) == WHITE


def test_scanner_covers_width() -> None:
    """Scanner lights a contiguous bar of the given width."""
    layer = ArgbLayer(
        id="l",
        effect={"type": "scanner", "color": "#FF00FF", "width": 2, "period": 2.0},
    )
    layout = _layout(
        [_strip("d1", "h1", 6)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0)["h1"]
    assert _pixel(buf, 0) == (255, 0, 255)
    assert _pixel(buf, 1) == (255, 0, 255)
    assert _pixel(buf, 2) == (0, 0, 0)


def test_meter_bar_maps_value() -> None:
    """Meter bar mode lights the leading segment for the value."""
    layer = ArgbLayer(
        id="l",
        effect={
            "type": "meter",
            "source": "cpu.percent",
            "color_low": "#00FF00",
            "color_high": "#00FF00",
            "max_value": 100.0,
            "mode": "bar",
        },
    )
    layout = _layout(
        [_strip("d1", "h1", 4)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0, {"cpu.percent": 50.0})["h1"]
    assert _pixel(buf, 1) == (0, 255, 0)
    assert _pixel(buf, 2) == (0, 0, 0)


def test_meter_missing_source_is_transparent() -> None:
    """A meter with unavailable source renders nothing (alpha 0)."""
    layer = ArgbLayer(id="l", effect={"type": "meter", "source": "nope.value"})
    layout = _layout(
        [_strip("d1", "h1", 2)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1"])],
        [layer],
    )
    buf = _render(layout, 0.0, {})["h1"]
    assert _pixel(buf, 0) == (0, 0, 0)


def test_zone_size_pads_with_black() -> None:
    """A known zone size extends the buffer beyond the chain."""
    layout = _layout(
        [_strip("d1", "h1", 2)],
        [ArgbHeader(id="h1", zone_index=0, size=5, devices=["d1"])],
        [_fill_layer("#0A0B0C")],
    )
    buf = _render(layout, 0.0)["h1"]
    assert len(buf) == 15
    assert _pixel(buf, 1) == (0x0A, 0x0B, 0x0C)
    assert _pixel(buf, 4) == (0, 0, 0)


def test_gradient_spans_across_devices() -> None:
    """Chain indices continue across devices, so gradients flow through."""
    stops = [
        {"pos": 0.0, "color": "#000000"},
        {"pos": 1.0, "color": "#FFFFFF"},
    ]
    layer = ArgbLayer(
        id="l",
        effect={"type": "gradient", "stops": stops, "scale": 4, "mode": "static"},
    )
    layout = _layout(
        [_strip("d1", "h1", 2), _strip("d2", "h1", 2)],
        [ArgbHeader(id="h1", zone_index=0, devices=["d1", "d2"])],
        [layer],
    )
    buf = _render(layout, 0.0)["h1"]
    # Chain indices continue across devices: device 2 picks up at 50 % of
    # the tile instead of restarting dark.
    assert _pixel(buf, 2) == (128, 128, 128)
    assert _pixel(buf, 3)[0] > _pixel(buf, 2)[0]
