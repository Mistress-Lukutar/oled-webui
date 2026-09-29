"""
File:   schema.py
Brief:  Pydantic schema for ARGB layouts: headers, devices, effect layers.
Author: Mistress-Lukutar
Date:   2026-09-29
Version: v0.5.1
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Hex color with optional alpha channel, with or without the leading '#'.
COLOR_PATTERN = r"^#?[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$"

# Logical workspace size the editor arranges devices on. Coordinates are
# purely visual (the editor canvas maps them to the window); the engine
# only cares about header chain order.
WORKSPACE_WIDTH: int = 800
WORKSPACE_HEIGHT: int = 500


class _Strict(BaseModel):
    """Base for ARGB models: unknown keys are rejected with a clear error."""

    model_config = ConfigDict(extra="forbid")


class StopSpec(_Strict):
    """One gradient color stop."""

    pos: float = Field(0.0, ge=0, le=1, description="Stop position 0..1")
    color: str = Field(
        "#FFFFFF", pattern=COLOR_PATTERN, description="Stop color as #RRGGBB[AA]"
    )


class FillEffect(_Strict):
    """Static solid color fill."""

    type: Literal["fill"]
    color: str = Field(
        "#0000FF", pattern=COLOR_PATTERN, description="Fill color as #RRGGBB[AA]"
    )


class GradientEffect(_Strict):
    """Multi-stop cyclic gradient with optional scroll animation.

    The gradient tiles across the header chain: ``scale`` is the tile
    length in LEDs, ``speed`` the scroll rate in tiles per second.
    """

    type: Literal["gradient"]
    stops: list[StopSpec] = Field(
        ..., min_length=2, description="Color stops, interpolated cyclically"
    )
    scale: int = Field(30, ge=2, le=1024, description="Gradient tile length in LEDs")
    mode: Literal["static", "scroll", "pingpong"] = Field(
        "static", description="Animation mode"
    )
    speed: float = Field(
        0.2, ge=-20, le=20, description="Scroll speed in tiles/second; sign = direction"
    )


class RainbowEffect(_Strict):
    """Classic rainbow hue cycle along the chain."""

    type: Literal["rainbow"]
    speed: float = Field(
        0.5, ge=0, le=20, description="Hue cycle drift in cycles per second"
    )
    scale: int = Field(
        32, ge=2, le=1024, description="Chain length of one full hue cycle in LEDs"
    )
    direction: Literal[1, -1] = Field(1, description="Scroll direction along the chain")
    saturation: float = Field(1.0, ge=0, le=1, description="HSV saturation")
    value: float = Field(1.0, ge=0, le=1, description="HSV brightness")


class BreathingEffect(_Strict):
    """Smooth brightness pulse cycling through a color list."""

    type: Literal["breathing"]
    colors: list[str] = Field(
        ...,
        min_length=1,
        description="Colors cycled with a crossfade, as #RRGGBB[AA]",
    )
    period: float = Field(2.0, gt=0, le=60, description="Full cycle time in seconds")
    min_level: float = Field(
        0.0, ge=0, le=1, description="Dimmest level of the pulse 0..1"
    )


class CometEffect(_Strict):
    """A moving head pixel with an optional fading tail.

    Outside the head and tail the effect is fully transparent, so lower
    layers show through.
    """

    type: Literal["comet"]
    color: str = Field(
        "#FF0000", pattern=COLOR_PATTERN, description="Head color as #RRGGBB[AA]"
    )
    tail: int = Field(6, ge=0, le=512, description="Fading tail length in LEDs")
    speed: float = Field(10.0, ge=0, le=500, description="Head speed in LEDs/second")
    direction: Literal[1, -1] = Field(1, description="Movement direction")
    mode: Literal["loop", "bounce"] = Field(
        "loop", description="loop wraps around, bounce reflects at the ends"
    )
    fade: bool = Field(True, description="Fade the tail linearly")


class ScannerEffect(_Strict):
    """A bar of given width sweeping back and forth over the chain."""

    type: Literal["scanner"]
    color: str = Field(
        "#00FF00", pattern=COLOR_PATTERN, description="Bar color as #RRGGBB[AA]"
    )
    width: int = Field(3, ge=1, le=512, description="Bar width in LEDs")
    period: float = Field(2.0, gt=0, le=60, description="Seconds per full sweep")


class MeterEffect(_Strict):
    """Map a data source value to color, optionally as a progress bar."""

    type: Literal["meter"]
    source: str = Field(
        "cpu.percent", min_length=1, description="Data source path, e.g. cpu.percent"
    )
    color_low: str = Field(
        "#00FF88", pattern=COLOR_PATTERN, description="Color at value 0"
    )
    color_high: str = Field(
        "#FF2222", pattern=COLOR_PATTERN, description="Color at max_value"
    )
    max_value: float = Field(
        100.0, gt=0, description="Source value mapped to color_high / full bar"
    )
    mode: Literal["fill", "bar"] = Field(
        "bar",
        description="fill colors the whole chain, bar lights the leading segment",
    )


ArgbEffect = Annotated[
    FillEffect
    | GradientEffect
    | RainbowEffect
    | BreathingEffect
    | CometEffect
    | ScannerEffect
    | MeterEffect,
    Field(discriminator="type"),
]


class MaskSpec(_Strict):
    """Pixel mask limiting a layer to a subset of LEDs.

    When ``all`` is true the layer covers every pixel. Otherwise ``runs``
    holds, per device id, the inclusive ``[start, end]`` index ranges that
    the layer affects; devices absent from the mapping are fully excluded.
    """

    all: bool = Field(True, description="Affect all pixels")
    runs: dict[str, list[tuple[int, int]]] = Field(
        default_factory=dict,
        description="device id -> list of inclusive [start, end] index runs",
    )


class ArgbDevice(_Strict):
    """One physical ARGB item (strip, fan ring, dual-ring fan)."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field("", max_length=100, description="Display name")
    type: Literal["strip", "ring", "ring_stripes"]
    header_id: str = Field(..., min_length=1, description="Header this device hangs on")
    leds: int = Field(
        24, ge=1, le=512, description="LED count (ring size for ring_stripes)"
    )
    leds_side: int = Field(
        0, ge=0, le=256, description="Per-stripe LED count (ring_stripes only)"
    )
    x: float = Field(100.0, description="Workspace center X")
    y: float = Field(100.0, description="Workspace center Y")
    rotation: float = Field(
        0.0, ge=-360, le=360, description="Visual angle in degrees"
    )
    scale: float = Field(1.0, gt=0, le=10, description="Visual size multiplier")

    @property
    def total_leds(self) -> int:
        """Full pixel count including side stripes."""
        if self.type == "ring_stripes":
            return self.leds + 2 * self.leds_side
        return self.leds


class ArgbHeader(_Strict):
    """One controller output (OpenRGB zone) driving a chain of devices."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field("", max_length=100, description="Display name")
    zone_index: int = Field(0, ge=0, description="OpenRGB zone on the controller")
    size: int | None = Field(
        None, ge=1, le=1024, description="Zone capacity in LEDs; None = unknown"
    )
    devices: list[str] = Field(
        default_factory=list, description="Device ids in physical chain order"
    )


class ArgbLayer(_Strict):
    """One effect layer composited over the layers below it."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field("", max_length=100, description="Display name")
    enabled: bool = Field(True, description="Layer participates in compositing")
    opacity: float = Field(1.0, ge=0, le=1, description="Blend opacity 0..1")
    mask: MaskSpec = Field(default_factory=MaskSpec, description="Pixel mask")
    effect: ArgbEffect = Field(..., description="Effect rendered by this layer")


class ArgbLayout(BaseModel):
    """Validated ARGB layout: headers, devices and the effect stack."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(1, ge=1, description="Schema version")
    fps: int = Field(30, ge=1, le=60, description="Engine tick rate")
    brightness: int = Field(
        100, ge=0, le=200, description="Global brightness percent (gamma-corrected)"
    )
    autostart: bool = Field(
        False, description="Start the engine automatically on server startup"
    )
    headers: list[ArgbHeader] = Field(default_factory=list)
    devices: list[ArgbDevice] = Field(default_factory=list)
    layers: list[ArgbLayer] = Field(
        default_factory=list, description="Effect layers, bottom first"
    )

    @model_validator(mode="after")
    def _validate_references(self) -> ArgbLayout:
        """Check id uniqueness and header/device cross-references.

        Raises:
            ValueError: If ids repeat or references dangle.
        """
        device_ids = [device.id for device in self.devices]
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("Duplicate device ids in layout")
        header_ids = [header.id for header in self.headers]
        if len(header_ids) != len(set(header_ids)):
            raise ValueError("Duplicate header ids in layout")
        layer_ids = [layer.id for layer in self.layers]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("Duplicate layer ids in layout")

        by_id = {device.id: device for device in self.devices}
        chained: set[str] = set()
        for header in self.headers:
            used = 0
            for device_id in header.devices:
                device = by_id.get(device_id)
                if device is None:
                    raise ValueError(
                        f"Header {header.id!r} references unknown device {device_id!r}"
                    )
                if device_id in chained:
                    raise ValueError(
                        f"Device {device_id!r} is chained on more than one header"
                    )
                if device.header_id != header.id:
                    raise ValueError(
                        f"Device {device_id!r} declares header {device.header_id!r} "
                        f"but is chained on {header.id!r}"
                    )
                chained.add(device_id)
                used += device.total_leds
            if header.size is not None and used > header.size:
                raise ValueError(
                    f"Header {header.id!r} chain needs {used} LEDs "
                    f"but the zone provides {header.size}"
                )

        for device in self.devices:
            if device.id not in chained:
                raise ValueError(
                    f"Device {device.id!r} is not chained on any header devices list"
                )
            if device.type == "ring_stripes" and device.leds_side == 0:
                raise ValueError(
                    f"Device {device.id!r}: ring_stripes requires leds_side >= 1"
                )

        for layer in self.layers:
            for device_id, runs in layer.mask.runs.items():
                if device_id not in by_id:
                    raise ValueError(
                        f"Layer {layer.id!r} mask references unknown device "
                        f"{device_id!r}"
                    )
                last = by_id[device_id].total_leds - 1
                for start, end in runs:
                    if start > end:
                        raise ValueError(
                            f"Layer {layer.id!r} mask run [{start}, {end}] is inverted"
                        )
                    if start < 0 or end > last:
                        raise ValueError(
                            f"Layer {layer.id!r} mask run [{start}, {end}] is out of "
                            f"range for device {device_id!r} ({last + 1} LEDs)"
                        )
        return self


def default_layout() -> ArgbLayout:
    """Build the starter layout: one header, one 24-LED strip, blue fill.

    Returns:
        A minimal valid layout to seed the editor and persistence.
    """
    return ArgbLayout(
        headers=[ArgbHeader(id="h1", name="ARGB 1", zone_index=0, devices=["d1"])],
        devices=[
            ArgbDevice(
                id="d1",
                name="Strip 1",
                type="strip",
                header_id="h1",
                leds=24,
                x=200.0,
                y=250.0,
            )
        ],
        layers=[
            ArgbLayer(
                id="l1",
                name="Fill",
                effect=FillEffect(type="fill", color="#2244CC"),
            )
        ],
    )
