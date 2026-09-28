"""
File:   schema.py
Brief:  Pydantic schema for scene documents: background, widgets, animation.
Author: Mistress-Lukutar
Date:   2026-09-28
Version: v0.4.0
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base for scene models: unknown keys are rejected with a clear error."""

    model_config = ConfigDict(extra="forbid")


class ImageLayer(_Strict):
    """Static background image composited once at scene start."""

    path: str = Field(..., description="Image path relative to the scene file")
    pos: tuple[int, int] | None = Field(
        None, description="Top-left corner; None stretches the image to the canvas"
    )
    scale: float = Field(1.0, gt=0, description="Size multiplier")
    opacity: float = Field(1.0, ge=0, le=1, description="Layer opacity 0..1")


class TextStyle(_Strict):
    """Text rendering style (typography options follow design-suite terms).

    ``leading`` is the line spacing as a multiplier of the font size,
    ``tracking`` adds letter spacing in pixels, and ``direction`` selects
    the writing direction: ``ltr`` (default), ``rtl`` (mirror of ``ltr``),
    ``ttb`` (characters stacked top-to-bottom) or ``btt`` (mirror of
    ``ttb``).
    """

    family: str | None = Field(
        None,
        description=(
            "Font file path; 'fonts/<name>.ttf' resolves against the shared "
            "font library, other relative paths against the scene directory"
        ),
    )
    size: int = Field(24, ge=4, le=200, description="Font size in pixels")
    color: str = Field("#FFFFFF", description="Text color as #RRGGBB")
    leading: float = Field(
        1.2, gt=0, le=4.0, description="Line spacing as a multiplier of font size"
    )
    tracking: int = Field(
        0, ge=-32, le=128, description="Letter spacing in pixels"
    )
    direction: Literal["ltr", "rtl", "ttb", "btt"] = Field(
        "ltr", description="Writing direction: ltr, rtl (mirror), ttb, btt (mirror)"
    )
    stroke_width: int = Field(0, ge=0, le=32, description="Outline thickness in pixels")
    stroke_color: str = Field("#000000", description="Outline color as #RRGGBB")


class BarStyle(_Strict):
    """Progress bar style."""

    fg: str = Field("#7CFC00", description="Filled part color")
    bg: str = Field("#222222", description="Track color")
    border: int = Field(0, ge=0, le=16, description="Border thickness in pixels")
    border_color: str = Field("#888888", description="Border color")
    border_align: Literal["center", "inside", "outside"] = Field(
        "inside", description="Border alignment: inside, centered on the edge, outside"
    )
    radius: int = Field(0, ge=0, description="Corner radius in pixels")
    orientation: Literal["horizontal", "vertical"] = "horizontal"


class RingStyle(_Strict):
    """Ring (circular progress) style."""

    fg: str = Field("#7CFC00", description="Progress arc color")
    bg: str = Field("#222222", description="Background arc color")
    width: int = Field(8, ge=1, le=64, description="Arc thickness in pixels")
    start_angle: int = Field(-90, ge=-360, le=360, description="Arc start angle")
    sweep: int = Field(360, ge=30, le=360, description="Full-track sweep in degrees")


class GraphStyle(_Strict):
    """Sparkline/history graph style."""

    fg: str = Field("#7CFC00", description="Line color")
    bg: str | None = Field(None, description="Background fill; None for transparent")
    fill: bool = Field(True, description="Fill the area under the line")
    line_width: int = Field(2, ge=1, le=16, description="Line thickness in pixels")
    scale_max: float | None = Field(
        None, gt=0, description="Fixed scale maximum; None scales to history peak"
    )


class AnimateSpec(_Strict):
    """Value transition animation spec."""

    easing: str = Field("ease-out-cubic", description="Easing curve name")
    duration: int = Field(400, gt=0, le=10000, description="Transition time in ms")


class WidgetBase(_Strict):
    """Fields shared by every widget type.

    Expression-valued fields accept either a number or a string expression
    with variables ``t`` (seconds since scene start), ``dt`` and ``v``
    (the widget's current source value).
    """

    rect: tuple[int, int, int, int] = Field(
        ..., description="Widget box as (x, y, width, height)"
    )
    visible: bool | str = Field(True, description="Bool or visibility expression")
    offset_x: str | int | float = Field(0, description="X offset or expression")
    offset_y: str | int | float = Field(0, description="Y offset or expression")
    opacity: str | int | float = Field(1.0, description="Opacity or expression 0..1")
    rotation: str | int | float = Field(
        0.0, description="Rotation degrees or expression (all widget types)"
    )
    animate: dict[str, AnimateSpec] = Field(
        default_factory=dict, description="Named animations; 'value' eases the source"
    )
    locked: bool = Field(
        False, description="Editor hint: element is locked and mouse-transparent"
    )


class TextWidget(WidgetBase):
    """Text label bound to a data source or a literal template."""

    type: Literal["text"]
    source: str | None = Field(None, description="Data source path, e.g. cpu.percent")
    value: str | int | float | None = Field(
        None, description="Template with {value} or a literal text"
    )
    align: Literal["left", "center", "right"] = "left"
    style: TextStyle = Field(default_factory=lambda: TextStyle())


class BarWidget(WidgetBase):
    """Progress bar bound to a 0..100 data source."""

    type: Literal["bar"]
    source: str = Field(..., description="Numeric data source path")
    style: BarStyle = Field(default_factory=lambda: BarStyle())


class RingWidget(WidgetBase):
    """Circular progress bound to a 0..100 data source."""

    type: Literal["ring"]
    source: str = Field(..., description="Numeric data source path")
    style: RingStyle = Field(default_factory=lambda: RingStyle())


class GraphWidget(WidgetBase):
    """History sparkline bound to a numeric data source."""

    type: Literal["graph"]
    source: str = Field(..., description="Numeric data source path")
    history: int = Field(60, ge=2, le=3600, description="Number of samples kept")
    style: GraphStyle = Field(default_factory=lambda: GraphStyle())


class ImageWidget(WidgetBase):
    """Image sprite; supports procedural rotation/opacity animation."""

    type: Literal["image"]
    path: str = Field(..., description="Image path relative to the scene file")
    fit: Literal["scale", "contain", "cover", "stretch"] = Field(
        "scale",
        description=(
            "Sizing: 'scale' multiplies the sprite (legacy), 'contain' fits "
            "inside the rect, 'cover' fills the rect, 'stretch' distorts to it"
        ),
    )
    scale: float = Field(1.0, gt=0, description="Size multiplier (fit='scale' only)")


Widget = Annotated[
    TextWidget | BarWidget | RingWidget | GraphWidget | ImageWidget,
    Field(discriminator="type"),
]


class SceneDocument(BaseModel):
    """Validated scene document: static background plus animated widgets.

    Brightness and JPEG quality are global display settings managed by the
    application, not per-scene values.
    """

    model_config = ConfigDict(extra="forbid")

    background: list[ImageLayer] = Field(default_factory=list)
    widgets: list[Widget] = Field(default_factory=list)
    refresh: float = Field(1.0, gt=0, le=60, description="Data polling frequency in Hz")
    max_fps: float = Field(
        20.0, gt=0, le=60, description="Cap for animation frame rate in fps"
    )
    keepalive_interval: float = Field(
        2.0, gt=0, description="Resend interval for unchanged frames in seconds"
    )
