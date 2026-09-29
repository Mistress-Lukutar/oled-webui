"""
File:   engine.py
Brief:  Pure ARGB effect engine: layout + time -> per-header pixel buffers.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.5.1
"""

from __future__ import annotations

import colorsys
import math
from collections.abc import Mapping
from dataclasses import dataclass

from oled_webui.argb.schema import (
    ArgbDevice,
    ArgbEffect,
    ArgbLayer,
    ArgbLayout,
    BreathingEffect,
    CometEffect,
    FillEffect,
    GradientEffect,
    MaskSpec,
    MeterEffect,
    RainbowEffect,
    ScannerEffect,
    StopSpec,
)

# Straight RGBA: 0-255 color channels plus alpha 0..1. An alpha below 1
# lets the layers underneath show through (alpha-over compositing).
Rgba = tuple[int, int, int, float]

_COLOR_CACHE: dict[str, Rgba] = {}


def parse_rgba(value: str) -> Rgba:
    """Parse a hex color string into straight RGBA.

    Args:
        value: Color as ``#RRGGBB`` or ``#RRGGBBAA`` (``#`` optional).

    Returns:
        Tuple of (red, green, blue, alpha) with 0-255 channels.

    Raises:
        ValueError: If the string is not a valid hex color.
    """
    cached = _COLOR_CACHE.get(value)
    if cached is not None:
        return cached
    text = value.strip().lstrip("#")
    if len(text) not in (6, 8):
        raise ValueError(f"Invalid color: {value!r}")
    try:
        red = int(text[0:2], 16)
        green = int(text[2:4], 16)
        blue = int(text[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Invalid color: {value!r}") from exc
    alpha = int(text[6:8], 16) / 255.0 if len(text) == 8 else 1.0
    out = (red, green, blue, alpha)
    _COLOR_CACHE[value] = out
    return out


def _lerp_rgba(a: Rgba, b: Rgba, f: float) -> Rgba:
    """Linearly interpolate two RGBA values."""
    return (
        round(a[0] + (b[0] - a[0]) * f),
        round(a[1] + (b[1] - a[1]) * f),
        round(a[2] + (b[2] - a[2]) * f),
        a[3] + (b[3] - a[3]) * f,
    )


@dataclass(frozen=True)
class PixelContext:
    """Everything an effect needs to color one pixel.

    Attributes:
        device: The device the pixel belongs to.
        i_local: Pixel index within the device (0-based).
        i_chain: Pixel index along the whole header chain.
        chain_len: Total LED count of the header chain.
        t: Effect time in seconds.
        samples: Current data-source snapshot for meter effects.
    """

    device: ArgbDevice
    i_local: int
    i_chain: int
    chain_len: int
    t: float
    samples: Mapping[str, float | str]


# ---------------------------------------------------------------------------
# Effects. Each returns straight RGBA; alpha 0 means "fully transparent, let
# the layers below show".
# ---------------------------------------------------------------------------


def _fx_fill(effect: FillEffect, _ctx: PixelContext) -> Rgba:
    """Uniform static color."""
    return parse_rgba(effect.color)


def _sample_stops(stops: list[StopSpec], pos: float) -> Rgba:
    """Sample a cyclic multi-stop gradient at position 0..1."""
    ordered = sorted(stops, key=lambda stop: stop.pos)
    count = len(ordered)
    for index in range(count):
        cur = ordered[index]
        nxt = ordered[(index + 1) % count]
        start = cur.pos
        end = nxt.pos if nxt.pos > start else nxt.pos + 1.0
        if start <= pos < end or (index == count - 1 and pos >= start):
            frac = (pos - start) / (end - start) if end > start else 0.0
            return _lerp_rgba(parse_rgba(cur.color), parse_rgba(nxt.color), frac)
    return parse_rgba(ordered[0].color)


def _fx_gradient(effect: GradientEffect, ctx: PixelContext) -> Rgba:
    """Tiled multi-stop gradient, optionally scrolling along the chain."""
    x = ctx.i_chain / effect.scale
    if effect.mode == "scroll":
        pos = (x + ctx.t * effect.speed) % 1.0
    elif effect.mode == "pingpong":
        phase = (x + ctx.t * effect.speed) % 2.0
        pos = phase if phase <= 1.0 else 2.0 - phase
    else:
        pos = x % 1.0
    return _sample_stops(effect.stops, pos)


def _fx_rainbow(effect: RainbowEffect, ctx: PixelContext) -> Rgba:
    """HSV rainbow scrolling along the chain."""
    hue = ((ctx.i_chain * effect.direction) % effect.scale) / effect.scale
    hue = (hue + ctx.t * effect.speed) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, effect.saturation, effect.value)
    return (round(red * 255), round(green * 255), round(blue * 255), 1.0)


def _fx_breathing(effect: BreathingEffect, ctx: PixelContext) -> Rgba:
    """Smooth pulse whose brightness modulates the layer alpha."""
    phase = (ctx.t / effect.period) % 1.0
    wave = 0.5 - 0.5 * math.cos(2.0 * math.pi * phase)
    level = effect.min_level + (1.0 - effect.min_level) * wave
    base = parse_rgba(effect.colors[0])
    if len(effect.colors) > 1:
        x = phase * len(effect.colors)
        i0 = int(x) % len(effect.colors)
        i1 = (i0 + 1) % len(effect.colors)
        base = _lerp_rgba(
            parse_rgba(effect.colors[i0]), parse_rgba(effect.colors[i1]), x - int(x)
        )
    return (base[0], base[1], base[2], base[3] * level)


def _fx_comet(effect: CometEffect, ctx: PixelContext) -> Rgba:
    """A head pixel with a fading tail; transparent outside of it."""
    chain = ctx.chain_len
    tail = effect.tail
    if effect.mode == "loop":
        span = chain + tail
        head = (ctx.t * effect.speed) % span - tail
    else:
        travel = max(chain - 1, 0)
        step = (ctx.t * effect.speed) % (2 * travel) if travel > 0 else 0.0
        head = step if step <= travel else 2 * travel - step
    dist = (head - ctx.i_chain) * effect.direction
    if 0.0 <= dist <= tail:
        base = parse_rgba(effect.color)
        alpha = 1.0 if not effect.fade or tail == 0 else 1.0 - dist / (tail + 1.0)
        return (base[0], base[1], base[2], base[3] * alpha)
    return (0, 0, 0, 0.0)


def _fx_scanner(effect: ScannerEffect, ctx: PixelContext) -> Rgba:
    """A solid bar sweeping back and forth over the chain."""
    span = max(ctx.chain_len - effect.width, 0)
    travel = (ctx.t / effect.period) % 2.0
    head = travel * span if travel <= 1.0 else (2.0 - travel) * span
    if 0.0 <= ctx.i_chain - head < effect.width:
        return parse_rgba(effect.color)
    return (0, 0, 0, 0.0)


def _fx_meter(effect: MeterEffect, ctx: PixelContext) -> Rgba:
    """Color by data-source value; bar mode lights a leading segment."""
    raw = ctx.samples.get(effect.source)
    if raw is None or isinstance(raw, str):
        return (0, 0, 0, 0.0)
    value = max(0.0, min(float(raw) / effect.max_value, 1.0))
    if effect.mode == "fill":
        color = _lerp_rgba(
            parse_rgba(effect.color_low), parse_rgba(effect.color_high), value
        )
        return (color[0], color[1], color[2], 1.0)
    lit = round(value * ctx.device.total_leds)
    if ctx.i_local < lit:
        color = _lerp_rgba(
            parse_rgba(effect.color_low), parse_rgba(effect.color_high), value
        )
        return (color[0], color[1], color[2], 1.0)
    return (0, 0, 0, 0.0)


def _effect_color(effect: ArgbEffect, ctx: PixelContext) -> Rgba:
    """Dispatch an effect spec to its renderer."""
    match effect:
        case FillEffect():
            return _fx_fill(effect, ctx)
        case GradientEffect():
            return _fx_gradient(effect, ctx)
        case RainbowEffect():
            return _fx_rainbow(effect, ctx)
        case BreathingEffect():
            return _fx_breathing(effect, ctx)
        case CometEffect():
            return _fx_comet(effect, ctx)
        case ScannerEffect():
            return _fx_scanner(effect, ctx)
        case MeterEffect():
            return _fx_meter(effect, ctx)
    raise ValueError(f"Unknown effect type: {type(effect).__name__}")


def _mask_covers(mask: MaskSpec, device_id: str, i_local: int) -> bool:
    """Return True when the mask includes this pixel."""
    if mask.all:
        return True
    runs = mask.runs.get(device_id)
    if not runs:
        return False
    return any(start <= i_local <= end for start, end in runs)


def _render_device(
    buffer: bytearray,
    offset: int,
    device: ArgbDevice,
    layers: list[ArgbLayer],
    t: float,
    chain_len: int,
    samples: Mapping[str, float | str],
) -> None:
    """Composite all layers onto one device's slice of the header buffer."""
    total = device.total_leds
    for i_local in range(total):
        red = green = blue = 0
        for layer in layers:
            if not layer.enabled or layer.opacity <= 0.0:
                continue
            if not _mask_covers(layer.mask, device.id, i_local):
                continue
            ctx = PixelContext(
                device=device,
                i_local=i_local,
                i_chain=offset + i_local,
                chain_len=chain_len,
                t=t,
                samples=samples,
            )
            color = _effect_color(layer.effect, ctx)
            alpha = color[3] * layer.opacity
            if alpha <= 0.0:
                continue
            index = 3 * (offset + i_local)
            if alpha >= 1.0:
                red, green, blue = color[0], color[1], color[2]
            else:
                red = round(red * (1.0 - alpha) + color[0] * alpha)
                green = round(green * (1.0 - alpha) + color[1] * alpha)
                blue = round(blue * (1.0 - alpha) + color[2] * alpha)
            buffer[index] = min(red, 255)
            buffer[index + 1] = min(green, 255)
            buffer[index + 2] = min(blue, 255)


def render_layout(
    layout: ArgbLayout,
    t: float,
    samples: Mapping[str, float | str] | None = None,
) -> dict[str, bytearray]:
    """Render the full layout into one RGB buffer per header.

    Args:
        layout: Validated layout (references are assumed consistent).
        t: Effect time in seconds.
        samples: Data-source snapshot for meter effects.

    Returns:
        Mapping of header id to an ``RGBRGB...`` bytearray; buffer length
        is the zone size when known, otherwise the chained LED count.
    """
    snapshot = samples if samples is not None else {}
    devices = {device.id: device for device in layout.devices}
    buffers: dict[str, bytearray] = {}
    for header in layout.headers:
        chained = [devices[did] for did in header.devices if did in devices]
        chain_len = sum(device.total_leds for device in chained)
        size = header.size if header.size is not None else chain_len
        buffer = bytearray(max(size, 1) * 3)
        offset = 0
        for device in chained:
            _render_device(
                buffer, offset, device, layout.layers, t, chain_len, snapshot
            )
            offset += device.total_leds
        buffers[header.id] = buffer
    return buffers


def apply_brightness(buffer: bytearray, lut: list[int]) -> None:
    """Apply a 256-entry brightness LUT to a buffer in place."""
    for index, value in enumerate(buffer):
        buffer[index] = lut[value]


def buffers_to_hex(buffers: dict[str, bytearray]) -> dict[str, str]:
    """Encode per-header buffers as hex strings for the JSON API."""
    return {header_id: bytes(buf).hex() for header_id, buf in buffers.items()}
