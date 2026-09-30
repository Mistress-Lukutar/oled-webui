"""
File:   widgets.py
Brief:  Pillow renderers for scene widgets: bar, text, ring, graph, image.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from oled_webui.exceptions import SceneError
from oled_webui.scene.expressions import EASINGS, Expression
from oled_webui.scene.schema import (
    AnimateSpec,
    BarWidget,
    GraphWidget,
    ImageWidget,
    RingWidget,
    ShapeWidget,
    TextWidget,
    VideoWidget,
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

    # Track first: the stroke must stay visible on top of an opaque fill.
    if style.fill:
        draw.rounded_rectangle(
            (x, y, x + w - 1, y + h - 1),
            radius=radius,
            fill=parse_color(style.fill_color),
        )

    if style.stroke_width:
        # PIL outlines grow inward from the bbox; shift the bbox outward so
        # the stroke sits inside, across, or outside the widget edge.
        out = 0
        if style.stroke_align == "center":
            out = style.stroke_width // 2
        elif style.stroke_align == "outside":
            out = style.stroke_width
        draw.rounded_rectangle(
            (x - out, y - out, x + w - 1 + out, y + h - 1 + out),
            radius=radius,
            outline=parse_color(style.stroke_color),
            width=style.stroke_width,
        )

    inset = style.stroke_width + 1 if style.stroke_width else 0
    if style.orientation == "horizontal":
        track_w = w - 2 * inset
        filled = int(track_w * fill01)
        if filled > 0:
            draw.rounded_rectangle(
                (x + inset, y + inset, x + inset + filled - 1, y + h - inset - 1),
                radius=min(radius, h // 2),
                fill=parse_color(style.progress_color),
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
                fill=parse_color(style.progress_color),
            )

def render_shape(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    widget: ShapeWidget,
) -> None:
    """Draw a static geometric shape into the local widget box.

    Rect and ellipse use the universal paint block (fill, stroke with
    alignment, corner radius); a line runs along the rect diagonal and
    uses only the stroke.

    Args:
        draw: Target draw context (local coordinates).
        rect: Local widget box (0-based).
        widget: Shape widget with style.
    """
    x, y, w, h = rect
    style = widget.style
    radius = min(style.radius, w // 2, h // 2)
    x1, y1 = x + w - 1, y + h - 1

    if widget.shape == "line":
        if style.stroke_width:
            draw.line((x, y, x1, y1), fill=parse_color(style.stroke_color), width=style.stroke_width)
        else:
            draw.line((x, y, x1, y1), fill=parse_color(style.stroke_color))
        return

    if widget.shape == "ellipse":
        if style.fill:
            draw.ellipse((x, y, x1, y1), fill=parse_color(style.fill_color))
        if style.stroke_width:
            # PIL ellipse outlines grow inward from the bbox; shift the
            # bbox outward so the stroke sits inside, across, or outside
            # the shape edge (same idiom as render_bar).
            out = 0
            if style.stroke_align == "center":
                out = style.stroke_width // 2
            elif style.stroke_align == "outside":
                out = style.stroke_width
            draw.ellipse(
                (x - out, y - out, x1 + out, y1 + out),
                outline=parse_color(style.stroke_color),
                width=style.stroke_width,
            )
        return

    if style.fill:
        draw.rounded_rectangle(
            (x, y, x1, y1),
            radius=radius,
            fill=parse_color(style.fill_color),
        )
    if style.stroke_width:
        out = 0
        if style.stroke_align == "center":
            out = style.stroke_width // 2
        elif style.stroke_align == "outside":
            out = style.stroke_width
        draw.rounded_rectangle(
            (x - out, y - out, x1 + out, y1 + out),
            radius=radius,
            outline=parse_color(style.stroke_color),
            width=style.stroke_width,
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
    # PIL arcs stroke inward from the bbox; expand it so the arc sits
    # inside, across, or outside the nominal circle edge.
    out = 0
    if style.stroke_align == "center":
        out = style.stroke_width // 2
    elif style.stroke_align == "outside":
        out = style.stroke_width
    size = min(w, h) - 1 + 2 * out
    box = (
        x + (w - size) // 2,
        y + (h - size) // 2,
        x + (w + size) // 2,
        y + (h + size) // 2,
    )
    fill01 = max(0.0, min(1.0, value01))

    if style.fill:
        draw.arc(
            box,
            style.start_angle,
            style.start_angle + style.sweep,
            fill=parse_color(style.fill_color),
            width=style.stroke_width,
        )
    if fill01 > 0:
        draw.arc(
            box,
            style.start_angle,
            style.start_angle + int(style.sweep * fill01),
            fill=parse_color(style.stroke_color),
            width=style.stroke_width,
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

    line_color = parse_color(style.stroke_color)
    if style.fill:
        polygon = [(x, y + h - 1), *points, (x + w - 1, y + h - 1)]
        draw.polygon(polygon, fill=parse_color(style.fill_color))
    draw.line(points, fill=line_color, width=style.stroke_width, joint="curve")

def composite_clipped(
    layer: Image.Image, sprite: Image.Image, dest_x: int, dest_y: int
) -> None:
    """Alpha-composite a sprite onto a layer, cropping to the layer bounds.

    PIL rejects negative or overflowing destinations in alpha_composite;
    content extending past the layer is cropped instead.

    Args:
        layer: Target RGBA layer.
        sprite: RGBA sprite to composite.
        dest_x: Destination X; may be negative.
        dest_y: Destination Y; may be negative.
    """
    layer_w, layer_h = layer.size
    crop_left = max(0, -dest_x)
    crop_top = max(0, -dest_y)
    crop_right = max(0, dest_x + sprite.width - layer_w)
    crop_bottom = max(0, dest_y + sprite.height - layer_h)
    if (crop_left, crop_top, crop_right, crop_bottom) != (0, 0, 0, 0):
        sprite = sprite.crop(
            (
                crop_left,
                crop_top,
                sprite.width - crop_right,
                sprite.height - crop_bottom,
            )
        )
        dest_x += crop_left
        dest_y += crop_top
    if sprite.width <= 0 or sprite.height <= 0:
        return
    layer.alpha_composite(sprite, dest=(dest_x, dest_y))


def _stroke_kwargs(style: Any) -> dict[str, Any]:
    """Build draw.text keyword arguments for the text outline.

    Args:
        style: TextStyle-like object with ``stroke_width``/``stroke_color``.

    Returns:
        Empty dict for zero-width outlines, otherwise width and fill.
    """
    if style.stroke_width <= 0:
        return {}
    return {
        "stroke_width": style.stroke_width,
        "stroke_fill": parse_color(style.stroke_color),
    }


def _horizontal_block(text: str, widget: Any) -> Image.Image:
    """Render horizontal text (``ltr``/``rtl`` base) into a block image.

    Lines are laid out on a ``leading``-spaced grid and aligned per line
    within the block, mirroring paragraph alignment in design suites.

    Args:
        text: Rendered text; newlines split lines.
        widget: Text widget carrying the style and alignment.

    Returns:
        Transparent RGBA block sized to the text (padding included).
    """
    style = widget.style
    font = get_font(style.family, style.size)
    color = parse_color(style.fill_color) if style.fill else (0, 0, 0, 0)
    stroke = _stroke_kwargs(style)
    tracking = style.tracking
    pad = style.stroke_width + 1
    line_adv = max(1, round(style.size * style.leading))
    ascent, descent = font.getmetrics()  # type: ignore[union-attr]

    lines = text.split("\n")
    widths: list[float] = []
    for line in lines:
        if tracking and line:
            widths.append(
                sum(font.getlength(ch) for ch in line)
                + tracking * (len(line) - 1)
            )
        else:
            widths.append(font.getlength(line) if line else 0.0)
    inner_w = math.ceil(max(widths, default=0.0))
    inner_h = ascent + descent + line_adv * (len(lines) - 1)
    block = Image.new(
        "RGBA", (inner_w + 2 * pad, inner_h + 2 * pad), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(block)

    for index, line in enumerate(lines):
        if not line:
            continue
        if widget.align == "center":
            x = pad + (inner_w - widths[index]) / 2
        elif widget.align == "right":
            x = pad + inner_w - widths[index]
        else:
            x = float(pad)
        baseline = pad + ascent + index * line_adv
        if tracking:
            cursor = x
            for ch in line:
                draw.text(
                    (cursor, baseline), ch, font=font, fill=color, anchor="ls", **stroke
                )
                cursor += font.getlength(ch) + tracking
        else:
            draw.text((x, baseline), line, font=font, fill=color, anchor="ls", **stroke)
    return block


def _vertical_block(text: str, widget: Any) -> Image.Image:
    """Render stacked vertical text (``ttb``/``btt`` base) into a block.

    Characters are stacked upright, one below the other; multi-line text
    becomes columns laid out left to right. Spaces add a fixed gap.

    Args:
        text: Rendered text; newlines split columns.
        widget: Text widget carrying the style and alignment.

    Returns:
        Transparent RGBA block sized to the text (padding included).
    """
    style = widget.style
    font = get_font(style.family, style.size)
    color = parse_color(style.fill_color) if style.fill else (0, 0, 0, 0)
    stroke = _stroke_kwargs(style)
    tracking = style.tracking
    pad = style.stroke_width + 1
    char_gap = tracking if tracking > 0 else round(style.size * 0.1)
    space_adv = max(2, round(style.size * 0.4))
    col_gap = max(tracking, 2)

    lines = text.split("\n")
    widths: list[float] = []
    heights: list[int] = []
    boxes: list[list[tuple[float, float, float]]] = []
    for line in lines:
        y = 0
        width = 0.0
        boxes.append([])
        for ch in line:
            if ch == " ":
                y += space_adv
                continue
            bbox = font.getbbox(ch)
            boxes[-1].append((bbox[3] - bbox[1], bbox[1], font.getlength(ch)))
            y += (bbox[3] - bbox[1]) + char_gap
            width = max(width, font.getlength(ch))
        heights.append(max(0, y - char_gap))
        widths.append(width)

    inner_w = int(sum(widths) + col_gap * (len(lines) - 1))
    inner_h = max(heights, default=0)
    block = Image.new(
        "RGBA", (inner_w + 2 * pad, inner_h + 2 * pad), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(block)

    offset_x = 0.0
    for index, line in enumerate(lines):
        x = pad + offset_x
        y = pad
        metrics = iter(boxes[index])
        for ch in line:
            if ch == " ":
                y += space_adv
                continue
            ink_h, ink_top, _width = next(metrics)
            draw.text((x, y - ink_top), ch, font=font, fill=color, **stroke)
            y += ink_h + char_gap
        offset_x += widths[index] + col_gap
    return block


def render_text(
    image: Image.Image,
    rect: tuple[int, int, int, int],
    text: str,
    widget: TextWidget,
) -> None:
    """Draw a text label into the local widget box.

    The text is rendered into a transparent block at its base orientation
    (``ltr``/``ttb``), mirrored for ``rtl``/``btt``, then pasted into the
    box honoring the horizontal alignment; vertically the block is centered.

    Args:
        image: Target RGBA image (local widget box coordinates).
        rect: Local widget box (0-based).
        text: Rendered text.
        widget: Text widget with style.

    Raises:
        SceneError: If the font file cannot be loaded or a color is invalid.
    """
    if text.strip() == "":
        return
    style = widget.style
    if style.direction in ("ltr", "rtl"):
        base = _horizontal_block(text, widget)
    else:
        base = _vertical_block(text, widget)
    if style.direction == "rtl":
        base = ImageOps.mirror(base)
    elif style.direction == "btt":
        base = ImageOps.flip(base)

    x, y, w, h = rect
    if widget.align == "center":
        tx = x + (w - base.width) // 2
    elif widget.align == "right":
        tx = x + w - base.width
    else:
        tx = x
    ty = y + max(0, (h - base.height) // 2)
    image.paste(base, (tx, ty), base)

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
    widget: ImageWidget | VideoWidget,
    opacity: float,
    rotation: float,
    sprite: Image.Image | None = None,
) -> None:
    """Composite a (possibly rotated/faded) image widget onto the layer.

    The sprite is sized per the widget's ``fit`` mode inside the widget
    box; corner radius clips the sprite, and the style frame is drawn on
    top with the same rotation. Sprites extending past the layer bounds
    are cropped. Video widgets pass their current frame via ``sprite``
    instead of loading ``path`` through the sprite cache.

    Args:
        layer: Target RGBA layer.
        rect: Local widget box (0-based).
        widget: Image or video widget.
        opacity: Evaluated opacity in [0, 1].
        rotation: Evaluated rotation in degrees (counter-clockwise).
        sprite: Pre-loaded sprite; None loads ``widget.path``.
    """
    style = widget.style
    if sprite is None:
        sprite = get_sprite(widget.path)
    x, y, w, h = rect
    if widget.fit == "stretch":
        size = (max(1, w), max(1, h))
    elif widget.fit in ("contain", "cover"):
        box_w, box_h = sprite.size
        ratio_w = w / box_w
        ratio_h = h / box_h
        factor = min(ratio_w, ratio_h) if widget.fit == "contain" else max(ratio_w, ratio_h)
        size = (max(1, int(box_w * factor)), max(1, int(box_h * factor)))
    else:  # scale
        size = (
            max(1, int(sprite.width * widget.scale)),
            max(1, int(sprite.height * widget.scale)),
        )
    if size != sprite.size:
        sprite = sprite.resize(size, Image.Resampling.LANCZOS)
    if style.radius > 0:
        sprite = _round_corners(sprite, style.radius)
    if rotation % 360 != 0:
        sprite = sprite.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
    if opacity < 1.0:
        alpha = sprite.getchannel("A").point(
            lambda a: int(a * max(0.0, min(1.0, opacity)))
        )
        sprite = sprite.copy()
        sprite.putalpha(alpha)

    dest_x = x + (w - sprite.width) // 2
    dest_y = y + (h - sprite.height) // 2
    # 'cover' fills the widget box and is clipped to it (object-fit cover);
    # other modes keep their legacy overflow behavior.
    if widget.fit == "cover":
        clip_left = max(0, x - dest_x)
        clip_top = max(0, y - dest_y)
        clip_right = max(0, dest_x + sprite.width - (x + w))
        clip_bottom = max(0, dest_y + sprite.height - (y + h))
        if (clip_left, clip_top, clip_right, clip_bottom) != (0, 0, 0, 0):
            sprite = sprite.crop(
                (
                    clip_left,
                    clip_top,
                    sprite.width - clip_right,
                    sprite.height - clip_bottom,
                )
            )
            dest_x += clip_left
            dest_y += clip_top
    # Crop whatever extends past the layer bounds; PIL rejects negative
    # or overflowing destinations in alpha_composite.
    composite_clipped(layer, sprite, dest_x, dest_y)
    if style.stroke_width:
        _draw_frame(layer, rect, style, rotation)


def _round_corners(sprite: Image.Image, radius: int) -> Image.Image:
    """Clip the sprite to a rounded rectangle of the given radius."""
    radius = min(radius, sprite.width // 2, sprite.height // 2)
    if radius <= 0:
        return sprite
    mask = Image.new("L", sprite.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, sprite.width - 1, sprite.height - 1), radius=radius, fill=255
    )
    clipped = sprite.copy()
    clipped.putalpha(ImageChops.multiply(clipped.getchannel("A"), mask))
    return clipped


def _draw_frame(
    layer: Image.Image,
    rect: tuple[int, int, int, int],
    style: Any,
    rotation: float,
) -> None:
    """Draw the image frame stroke, rotated like the sprite.

    The frame is rendered into its own padded layer so a center/outside
    aligned stroke survives, then rotated around the rect center — the
    same pivot the sprite rotates around.

    Args:
        layer: Target RGBA layer.
        rect: Local widget box (0-based).
        style: ImageStyle with stroke settings and radius.
        rotation: Evaluated rotation in degrees (counter-clockwise).
    """
    x, y, w, h = rect
    width = style.stroke_width
    out = 0
    if style.stroke_align == "center":
        out = width // 2
    elif style.stroke_align == "outside":
        out = width
    pad = width
    frame = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle(
        (pad - out, pad - out, pad + w - 1 + out, pad + h - 1 + out),
        radius=min(style.radius, w // 2, h // 2),
        outline=parse_color(style.stroke_color),
        width=width,
    )
    if rotation % 360 != 0:
        frame = frame.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        dest_x = x + (w - frame.width) // 2
        dest_y = y + (h - frame.height) // 2
    else:
        dest_x, dest_y = x - pad, y - pad
    composite_clipped(layer, frame, dest_x, dest_y)
