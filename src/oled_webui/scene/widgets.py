"""
File:   widgets.py
Brief:  Pillow renderers for scene widgets: bar, text, ring, graph, image.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

from oled_webui.exceptions import SceneError
from oled_webui.scene.expressions import EASINGS, Expression
from oled_webui.scene.schema import (
    AnimateSpec,
    BarWidget,
    GraphWidget,
    ImageWidget,
    RingWidget,
    TextWidget,
)

# Font cache keyed by (family, size).
_FONTS: dict[tuple[str | None, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

# Sprite cache keyed by resolved path.
_SPRITES: dict[str, Image.Image] = {}


def parse_color(spec: str) -> tuple[int, int, int, int]:
    """Parse a color string into an RGBA tuple.

    Args:
        spec: Color as ``#RGB``, ``#RRGGBB`` or ``#RRGGBBAA``.

    Returns:
        (red, green, blue, alpha) tuple.

    Raises:
        SceneError: If the color format is invalid.
    """
    text = spec.strip().lstrip("#")
    if text.lower() in ("white",):
        return (255, 255, 255, 255)
    if text.lower() in ("black",):
        return (0, 0, 0, 255)
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text) + "FF"
    elif len(text) == 6:
        text += "FF"
    if len(text) != 8:
        raise SceneError(f"Invalid color {spec!r}; expected #RRGGBB")
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore[return-value]
    except ValueError as exc:
        raise SceneError(f"Invalid color {spec!r}: {exc}") from exc

def get_font(
    family: str | None, size: int
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Return a cached font for the given family and size.

    Args:
        family: Path to a TTF/OTF file, or None for the built-in default.
        size: Font size in pixels.

    Returns:
        Pillow font object.

    Raises:
        SceneError: If the font file cannot be loaded.
    """
    key = (family, size)
    if key not in _FONTS:
        try:
            if family:
                _FONTS[key] = ImageFont.truetype(family, size)
            else:
                _FONTS[key] = ImageFont.load_default(size=size)
        except OSError as exc:
            raise SceneError(f"Cannot load font {family!r}: {exc}") from exc
    return _FONTS[key]

class AnimatedValue:
    """Smoothly interpolated numeric value driven by an easing curve."""

    def __init__(self, spec: AnimateSpec) -> None:
        """Create an animator from a scene animation spec.

        Args:
            spec: Animation spec with easing name and duration in ms.
        """
        self._easing: Callable[[float], float] = EASINGS[spec.easing]
        self._duration = spec.duration / 1000.0
        self._current: float = 0.0
        self._from: float = 0.0
        self._target: float = 0.0
        self._start: float = 0.0
        self._primed = False

    def update(self, target: float, now: float) -> float:
        """Advance the animation toward the target value.

        Args:
            target: Desired value.
            now: Monotonic time in seconds.

        Returns:
            Current displayed value.
        """
        if not self._primed:
            self._current = target
            self._target = target
            self._primed = True
            return target
        if target != self._target:
            self._from = self.value(now)
            self._target = target
            self._start = now
        self._current = self.value(now)
        return self._current

    def value(self, now: float) -> float:
        """Compute the displayed value at the given time.

        Args:
            now: Monotonic time in seconds.

        Returns:
            Interpolated value.
        """
        if now >= self._start + self._duration:
            return self._target
        progress = (now - self._start) / self._duration if self._duration else 1.0
        eased = self._easing(max(0.0, min(1.0, progress)))
        return self._from + (self._target - self._from) * eased

    @property
    def active(self) -> bool:
        """True while a transition is in flight."""
        return self._primed and self._current != self._target

class WidgetRuntime:
    """Per-widget mutable state kept across ticks."""

    def __init__(self, widget: BarWidget | RingWidget | GraphWidget) -> None:
        """Create runtime state for a data-bound widget.

        Args:
            widget: Widget owning this state.
        """
        self.animator: AnimatedValue | None = None
        if "value" in widget.animate:
            self.animator = AnimatedValue(widget.animate["value"])
        self.history: deque[float] = deque(
            maxlen=widget.history if isinstance(widget, GraphWidget) else 2
        )

def eval_number(
    spec: str | int | float, variables: dict[str, float], context: str
) -> float:
    """Evaluate a number-or-expression field.

    Args:
        spec: Numeric literal or expression string.
        variables: Expression variables.
        context: Field description used in error messages.

    Returns:
        Numeric result.

    Raises:
        SceneError: If the expression is invalid.
    """
    if isinstance(spec, str):
        try:
            return Expression(spec).evaluate(variables)
        except SceneError as exc:
            raise SceneError(f"{context}: {exc}") from exc
    return float(spec)

def render_bar(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    value01: float,
    widget: BarWidget,
) -> None:
    """Draw a progress bar into the local widget box.

    Args:
        draw: Target draw context (local coordinates).
        rect: Local widget box (0-based).
        value01: Normalized value in [0, 1].
        widget: Bar widget with style.
    """
    x, y, w, h = rect
    style = widget.style
    radius = min(style.radius, w // 2, h // 2)
    fill01 = max(0.0, min(1.0, value01))

    if style.border:
        draw.rounded_rectangle(
            (x, y, x + w - 1, y + h - 1),
            radius=radius,
            outline=parse_color(style.border_color),
            width=style.border,
        )
    draw.rounded_rectangle(
        (x, y, x + w - 1, y + h - 1), radius=radius, fill=parse_color(style.bg)
    )

    inset = style.border + 1 if style.border else 0
    if style.orientation == "horizontal":
        track_w = w - 2 * inset
        filled = int(track_w * fill01)
        if filled > 0:
            draw.rounded_rectangle(
                (x + inset, y + inset, x + inset + filled - 1, y + h - inset - 1),
                radius=min(radius, h // 2),
                fill=parse_color(style.fg),
            )
    else:
        track_h = h - 2 * inset
        filled = int(track_h * fill01)
        if filled > 0:
            draw.rounded_rectangle(
                (
                    x + inset,
                    y + h - inset - filled,
                    x + w - inset - 1,
                    y + h - inset - 1,
                ),
                radius=min(radius, w // 2),
                fill=parse_color(style.fg),
            )

def render_ring(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    value01: float,
    widget: RingWidget,
) -> None:
    """Draw a circular progress arc into the local widget box.

    Args:
        draw: Target draw context (local coordinates).
        rect: Local widget box (0-based).
        value01: Normalized value in [0, 1].
        widget: Ring widget with style.
    """
    x, y, w, h = rect
    style = widget.style
    size = min(w, h) - 1
    box = (
        x + (w - size) // 2,
        y + (h - size) // 2,
        x + (w + size) // 2,
        y + (h + size) // 2,
    )
    fill01 = max(0.0, min(1.0, value01))

    draw.arc(
        box,
        style.start_angle,
        style.start_angle + style.sweep,
        fill=parse_color(style.bg),
        width=style.width,
    )
    if fill01 > 0:
        draw.arc(
            box,
            style.start_angle,
            style.start_angle + int(style.sweep * fill01),
            fill=parse_color(style.fg),
            width=style.width,
        )

def render_graph(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    history: deque[float],
    widget: GraphWidget,
) -> None:
    """Draw a history sparkline into the local widget box.

    Args:
        draw: Target draw context (local coordinates).
        rect: Local widget box (0-based).
        history: Recent samples, oldest first.
        widget: Graph widget with style.
    """
    x, y, w, h = rect
    style = widget.style
    if style.bg:
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=parse_color(style.bg))
    if len(history) < 2:
        return

    peak = style.scale_max if style.scale_max is not None else max(max(history), 1e-6)
    peak = max(peak, 1e-6)
    points: list[tuple[float, float]] = []
    count = len(history)
    for index, sample in enumerate(history):
        px = x + w * index / (count - 1)
        norm = max(0.0, min(1.0, sample / peak))
        py = y + h - 1 - (h - 1) * norm
        points.append((px, py))

    line_color = parse_color(style.fg)
    if style.fill:
        polygon = [(x, y + h - 1), *points, (x + w - 1, y + h - 1)]
        draw.polygon(polygon, fill=(line_color[0], line_color[1], line_color[2], 96))
    draw.line(points, fill=line_color, width=style.line_width, joint="curve")

def render_text(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    text: str,
    widget: TextWidget,
) -> None:
    """Draw a text label into the local widget box.

    Args:
        draw: Target draw context (local coordinates).
        rect: Local widget box (0-based).
        text: Rendered text.
        widget: Text widget with style.
    """
    x, y, w, h = rect
    font = get_font(widget.style.family, widget.style.size)
    color = parse_color(widget.style.color)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_w = right - left
    text_h = bottom - top
    if widget.align == "center":
        tx = x + (w - text_w) // 2
    elif widget.align == "right":
        tx = x + w - text_w
    else:
        tx = x
    ty = y + max(0, (h - text_h) // 2) - top
    draw.text((tx, ty), text, font=font, fill=color)

def get_sprite(path: str) -> Image.Image:
    """Load and cache an RGBA sprite.

    Args:
        path: Resolved image file path.

    Returns:
        RGBA image.

    Raises:
        SceneError: If the image cannot be loaded.
    """
    if path not in _SPRITES:
        try:
            sprite = Image.open(path).convert("RGBA")
        except (OSError, ValueError) as exc:
            raise SceneError(f"Cannot load image {path}: {exc}") from exc
        _SPRITES[path] = sprite
    return _SPRITES[path]

def render_image(
    layer: Image.Image,
    rect: tuple[int, int, int, int],
    widget: ImageWidget,
    opacity: float,
    rotation: float,
) -> None:
    """Composite a (possibly rotated/faded) image widget onto the layer.

    The sprite is centered in the widget box; rotation and opacity are
    applied before compositing.

    Args:
        layer: Target RGBA layer.
        rect: Local widget box (0-based).
        widget: Image widget.
        opacity: Evaluated opacity in [0, 1].
        rotation: Evaluated rotation in degrees (counter-clockwise).
    """
    sprite = get_sprite(widget.path)
    size = (
        max(1, int(sprite.width * widget.scale)),
        max(1, int(sprite.height * widget.scale)),
    )
    if size != sprite.size:
        sprite = sprite.resize(size, Image.Resampling.LANCZOS)
    if rotation % 360 != 0:
        sprite = sprite.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    if opacity < 1.0:
        alpha = sprite.getchannel("A").point(
            lambda a: int(a * max(0.0, min(1.0, opacity)))
        )
        sprite = sprite.copy()
        sprite.putalpha(alpha)

    x, y, w, h = rect
    dest = (x + (w - sprite.width) // 2, y + (h - sprite.height) // 2)
    layer.alpha_composite(sprite, dest=dest)
