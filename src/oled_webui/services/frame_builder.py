"""
File:   frame_builder.py
Brief:  Pillow-based render and encode pipeline for display frames.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image, ImageDraw, ImageFont

from oled_webui.core.constants import (
    DEFAULT_BASE_ROTATION,
    DEFAULT_FIT,
    DEFAULT_JPEG_QUALITY,
    FIT_CONTAIN,
    FIT_HEIGHT,
    FIT_STRETCH,
    FIT_WIDTH,
)
from oled_webui.exceptions import RenderError

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = structlog.get_logger(__name__)

# Pillow ships DejaVu fonts for its own test suite but does not install them;
# these names are tried in order when no explicit font file is given.
_FALLBACK_FONT_NAMES: tuple[str, ...] = (
    "DejaVuSans.ttf",
    "arial.ttf",
    "segoeui.ttf",
    "LiberationSans-Regular.ttf",
)

# Panels are driven with sRGB-encoded values and respond to them with a
# power law of roughly this exponent. Multiplying encoded values by the
# brightness fraction directly would make physical luminance follow
# (fraction)^gamma: "50 %" would light the panel at ~22 % luminance and
# dark levels would collapse into the first few output steps. Scaling in
# linear light (factor**(1/gamma) in encoded space) keeps luminance
# proportional to the setting and preserves separation of dark tones.
DISPLAY_GAMMA: float = 2.2


def brightness_scale(brightness: int) -> float:
    """Return the sRGB-encoded multiplier for a brightness percent.

    A setting of N percent targets N percent of the panel's maximum
    physical luminance, so encoded values are scaled by the gamma root
    of the fraction (50 % -> ~0.73, not 0.5).

    Args:
        brightness: Software brightness 0-200 percent.

    Returns:
        Multiplier applied to sRGB-encoded channel values.
    """
    factor = max(0, brightness) / 100.0
    return float(factor ** (1.0 / DISPLAY_GAMMA))


def brightness_lut(brightness: int) -> list[int]:
    """Build the 256-entry lookup table for brightness scaling.

    Rounding to the nearest level (instead of truncating) keeps low
    encoded values from collapsing to black, which is what made dark
    areas band and merge at low settings.

    Args:
        brightness: Software brightness 0-200 percent.

    Returns:
        Table mapping an input channel value to the scaled output value.
    """
    scale = brightness_scale(brightness)
    return [min(255, int(i * scale + 0.5)) for i in range(256)]


def parse_hex_color(value: str) -> tuple[int, int, int]:
    """Parse a hex color string into an RGB tuple.

    Args:
        value: Hex color in ``RRGGBB`` or ``#RRGGBB`` form.

    Returns:
        Tuple of (red, green, blue) in 0-255 range.

    Raises:
        RenderError: If the string is not a valid hex color.
    """
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise RenderError(f"Invalid hex color: {value!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as exc:
        raise RenderError(f"Invalid hex color: {value!r}") from exc


class FrameBuilder:
    """Render, transform and encode frames for the USB LCD."""

    def __init__(
        self,
        width: int,
        height: int,
        rotation: int = 0,
        brightness: int = 100,
        fit: str = DEFAULT_FIT,
        quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        self._width = width
        self._height = height
        self._rotation = rotation
        self._brightness = brightness
        self._fit = fit
        self._quality = quality

    @property
    def width(self) -> int:
        """Target canvas width."""
        return self._width

    @property
    def height(self) -> int:
        """Target canvas height."""
        return self._height

    @property
    def source_size(self) -> tuple[int, int]:
        """Canvas size content must be produced at before the user rotation.

        For quarter-turn rotations the content canvas is swapped, so after
        the rotation the frame lands on the exact panel size instead of a
        transposed one the panel cannot display full-screen.
        """
        if self._rotation % 180 != 0:
            return (self._height, self._width)
        return (self._width, self._height)

    @staticmethod
    def load_image(path: Path) -> Image.Image:
        """Load an image from disk.

        Args:
            path: Path to the image file.

        Returns:
            Loaded PIL image.

        Raises:
            RenderError: If the file cannot be loaded.
        """
        try:
            image = Image.open(path)
            image.load()
            return image
        except (OSError, ValueError) as exc:
            raise RenderError(f"Failed to load image {path}: {exc}") from exc

    @staticmethod
    def load_image_bytes(data: bytes) -> Image.Image:
        """Load an image from an in-memory byte buffer.

        Args:
            data: Encoded image bytes (PNG/JPEG/BMP/...).

        Returns:
            Loaded PIL image.

        Raises:
            RenderError: If the bytes cannot be decoded.
        """
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            return image
        except (OSError, ValueError) as exc:
            raise RenderError(f"Failed to decode uploaded image: {exc}") from exc

    def fit_image(self, image: Image.Image) -> Image.Image:
        """Resize an image to the target canvas using the configured fit mode.

        Args:
            image: Source image.

        Returns:
            Resized image matching the canvas size.

        Raises:
            RenderError: If the fit mode is unsupported.
        """
        mode = self._fit.lower()
        if mode == FIT_STRETCH:
            return image.resize((self._width, self._height), Image.Resampling.LANCZOS)

        if mode == FIT_CONTAIN:
            image.thumbnail((self._width, self._height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (self._width, self._height), (0, 0, 0))
            offset_x = (self._width - image.width) // 2
            offset_y = (self._height - image.height) // 2
            canvas.paste(image, (offset_x, offset_y))
            return canvas

        if mode in (FIT_WIDTH, FIT_HEIGHT):
            target = self._width if mode == FIT_WIDTH else self._height
            ratio = target / image.width if mode == FIT_WIDTH else target / image.height
            new_size = (int(image.width * ratio), int(image.height * ratio))
            resized = image.resize(new_size, Image.Resampling.LANCZOS)
            # Crop or pad to the canvas so the frame size always matches the panel.
            canvas = Image.new("RGB", (self._width, self._height), (0, 0, 0))
            offset_x = (self._width - resized.width) // 2
            offset_y = (self._height - resized.height) // 2
            canvas.paste(resized, (offset_x, offset_y))
            return canvas

        raise RenderError(f"Unsupported fit mode: {self._fit!r}")

    def apply_brightness(self, image: Image.Image) -> Image.Image:
        """Adjust image brightness with gamma-correct pixel scaling.

        The LUT scales in linear light, so the brightness percent tracks
        perceived (physical) luminance and dark tones stay separable.

        Args:
            image: Source image.

        Returns:
            Brightness-adjusted image.
        """
        if self._brightness == 100:
            return image
        table = brightness_lut(self._brightness)
        return image.point(table * len(image.getbands()))

    def apply_user_rotation(self, image: Image.Image) -> Image.Image:
        """Apply the user-requested rotation to pre-fit content.

        Args:
            image: Source image sized for ``source_size``.

        Returns:
            Rotated image; quarter turns swap its dimensions.
        """
        rotation = self._rotation % 360
        if rotation == 0:
            return image
        return image.rotate(rotation, expand=True)

    def apply_base_rotation(self, image: Image.Image) -> Image.Image:
        """Apply the fixed 180° base panel rotation.

        The panel is natively mounted upside-down; a 180° turn never changes
        the image dimensions, so this is safe to apply to panel-sized frames.

        Args:
            image: Source image.

        Returns:
            Rotated image.
        """
        if DEFAULT_BASE_ROTATION % 360 == 0:
            return image
        return image.rotate(DEFAULT_BASE_ROTATION, expand=False)

    def build_frame(self, source: Image.Image | Path) -> Image.Image:
        """Load, rotate, fit and adjust brightness for a single frame.

        The user rotation is applied before fitting so quarter-turned
        content is fitted against the panel canvas and fills it; the fixed
        180° base rotation is applied last on the panel-sized frame.

        Args:
            source: PIL image or path to an image file.

        Returns:
            Final RGB image ready for encoding.
        """
        if isinstance(source, Image.Image):
            image = source.copy().convert("RGB")
        else:
            image = self.load_image(source).convert("RGB")

        image = self.apply_user_rotation(image)
        image = self.fit_image(image)
        image = self.apply_base_rotation(image)
        image = self.apply_brightness(image)
        return image

    def encode_jpeg(self, image: Image.Image) -> bytes:
        """Encode an RGB image to JPEG bytes.

        Args:
            image: RGB image.

        Returns:
            JPEG byte stream.

        Raises:
            RenderError: If encoding fails.
        """
        buffer = io.BytesIO()
        try:
            image.save(buffer, format="JPEG", quality=self._quality)
        except (OSError, ValueError) as exc:
            raise RenderError(f"JPEG encoding failed: {exc}") from exc
        return buffer.getvalue()

    def build_color_image(self, color: tuple[int, int, int]) -> Image.Image:
        """Create a solid color RGB image at the target size.

        Args:
            color: RGB tuple.

        Returns:
            Solid color image with brightness applied.
        """
        image = Image.new("RGB", (self._width, self._height), color)
        return self.apply_brightness(image)

    def render_text_frame(
        self,
        text: str,
        font_size: int = 48,
        color: tuple[int, int, int] = (255, 255, 255),
        background: tuple[int, int, int] = (0, 0, 0),
        align: str = "center",
        valign: str = "middle",
        padding: int = 20,
        font_path: Path | None = None,
    ) -> Image.Image:
        """Render multi-line text onto a canvas at the pre-rotation size.

        The canvas matches ``source_size``, so after the caller applies the
        user rotation and base panel rotation the frame is exactly the panel
        size.

        Args:
            text: Text to render; newlines start a new line.
            font_size: Font size in pixels.
            color: Text color as RGB tuple.
            background: Background color as RGB tuple.
            align: Horizontal alignment: left, center or right.
            valign: Vertical alignment: top, middle or bottom.
            padding: Margin in pixels around the text block.
            font_path: Optional TTF/OTF file; falls back to bundled fonts.

        Returns:
            Rendered RGB image (before rotation/brightness).

        Raises:
            RenderError: If alignment values are invalid.
        """
        if align not in ("left", "center", "right"):
            raise RenderError(f"Unsupported horizontal align: {align!r}")
        if valign not in ("top", "middle", "bottom"):
            raise RenderError(f"Unsupported vertical align: {valign!r}")

        canvas_width, canvas_height = self.source_size
        font = _load_font(font_size, font_path)
        canvas = Image.new("RGB", (canvas_width, canvas_height), background)
        draw = ImageDraw.Draw(canvas)

        lines = text.split("\n")
        line_heights: list[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line or " ", font=font)
            line_heights.append(int(bbox[3] - bbox[1]))

        line_spacing = max(4, font_size // 4)
        total_height = sum(line_heights) + line_spacing * (len(lines) - 1)

        if valign == "top":
            cursor_y = padding
        elif valign == "bottom":
            cursor_y = canvas_height - padding - total_height
        else:
            cursor_y = (canvas_height - total_height) // 2

        anchor_map = {"left": "la", "center": "ma", "right": "ra"}
        anchor = anchor_map[align]
        for line, line_height in zip(lines, line_heights, strict=True):
            if align == "left":
                x = padding
            elif align == "right":
                x = canvas_width - padding
            else:
                x = canvas_width // 2
            draw.text((x, cursor_y), line, font=font, fill=color, anchor=anchor)
            cursor_y += line_height + line_spacing

        return canvas


def _load_font(font_size: int, font_path: Path | None) -> ImageFont.FreeTypeFont:
    """Load a TrueType font, falling back through common system fonts.

    Args:
        font_size: Requested size in pixels.
        font_path: Explicit font file, or None to auto-resolve.

    Returns:
        Loaded FreeType font.

    Raises:
        RenderError: If no usable font is found.
    """
    candidates: Sequence[Path | str] = (
        [font_path] if font_path is not None else list(_FALLBACK_FONT_NAMES)
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), font_size)
        except OSError:
            continue
    raise RenderError("No usable TTF font found; place one in data/fonts/")


def build_black_frame(width: int, height: int) -> Image.Image:
    """Return a black RGB image of the given size.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        Black RGB image.
    """
    return Image.new("RGB", (width, height), (0, 0, 0))
