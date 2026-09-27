"""
File:   runner.py
Brief:  Scene rendering state machine: evaluation, compositing, scheduling.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.3.0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from PIL import Image, ImageDraw

from oled_webui.core.constants import DEFAULT_BRIGHTNESS, DEFAULT_JPEG_QUALITY
from oled_webui.exceptions import SceneError
from oled_webui.scene.expressions import Expression
from oled_webui.scene.providers import DataSources
from oled_webui.scene.schema import (
    BarWidget,
    GraphWidget,
    ImageLayer,
    ImageWidget,
    RingWidget,
    SceneDocument,
    TextWidget,
    Widget,
)
from oled_webui.scene.widgets import (
    WidgetRuntime,
    eval_number,
    get_sprite,
    render_bar,
    render_graph,
    render_image,
    render_ring,
    render_text,
)
from oled_webui.services.frame_builder import FrameBuilder

if TYPE_CHECKING:
    from collections.abc import Sequence

    from oled_webui.core.models import Resolution

logger = structlog.get_logger(__name__)

_DATA_BOUND = (BarWidget, RingWidget, GraphWidget)

# Sentinel returned by _fetch_source when the source cannot be resolved.
_UNAVAILABLE: Any = object()


@dataclass
class _Evaluated:
    """Per-widget evaluation result for one tick."""

    widget: Widget
    runtime: WidgetRuntime | None
    visible: bool = True
    text: str = ""
    value01: float = 0.0
    offset_x: int = 0
    offset_y: int = 0
    opacity: float = 1.0
    rotation: float = 0.0
    raw: float | str | None = None
    signature: tuple[Any, ...] = field(default_factory=tuple)


class SceneRenderer:
    """Renders a scene into JPEG payloads and schedules frame updates.

    The renderer owns no hardware: :meth:`tick` returns the encoded JPEG
    when a frame should go to the panel (fresh render or keepalive resend)
    and ``None`` when nothing needs sending. The caller (DisplayService)
    owns the USB transport, the send loop and the keepalive task.

    The static background layer is composited once; the widget layer is
    redrawn only when inputs change. Unchanged scenes fall back to
    re-yielding the last JPEG payload at the keepalive interval so the
    firmware does not revert to its built-in logo.
    """

    def __init__(
        self,
        scene: SceneDocument,
        resolution: Resolution,
        brightness: int = DEFAULT_BRIGHTNESS,
        quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        """Prepare caches, providers and the static layer.

        Args:
            scene: Validated scene document.
            resolution: Panel resolution.
            brightness: Global output brightness percent.
            quality: Global JPEG encoding quality.
        """
        self._scene = scene
        self._providers = DataSources()
        self._size = (resolution.width, resolution.height)
        self._output = (brightness, quality)
        self._output_dirty = False
        self._builder = FrameBuilder(
            width=resolution.width,
            height=resolution.height,
            brightness=brightness,
            quality=quality,
        )
        self._static = self._render_static(scene.background)
        self._runtimes: dict[int, WidgetRuntime] = {
            id(widget): WidgetRuntime(widget)
            for widget in scene.widgets
            if isinstance(widget, _DATA_BOUND)
        }
        self._last_signature: list[tuple[Any, ...]] | None = None
        self._last_payload: bytes | None = None
        self._started: float = 0.0
        self._just_polled: bool = False
        self._next_poll: float = 0.0
        self._last_yield: float = 0.0
        self._reported_missing: set[str] = set()

    @property
    def size(self) -> tuple[int, int]:
        """Canvas size as (width, height)."""
        return self._size

    @property
    def refresh(self) -> float:
        """Data polling frequency of the scene in Hz."""
        return self._scene.refresh

    @property
    def max_fps(self) -> float:
        """Animation frame rate cap of the scene."""
        return self._scene.max_fps

    def set_output(self, brightness: int, quality: int) -> None:
        """Update the global output settings and force a re-encode.

        The next :meth:`tick` re-encodes the frame even when widget state
        is unchanged, so the new settings become visible promptly.

        Args:
            brightness: Global output brightness percent.
            quality: Global JPEG encoding quality.
        """
        if (brightness, quality) == self._output:
            return
        self._output = (brightness, quality)
        self._builder = FrameBuilder(
            width=self._size[0],
            height=self._size[1],
            brightness=brightness,
            quality=quality,
        )
        self._output_dirty = True

    def tick(self, now: float | None = None) -> bytes | None:
        """Advance the scene by one tick.

        Args:
            now: Monotonic timestamp; defaults to the current clock.

        Returns:
            Encoded JPEG bytes when a frame should be sent (content changed
            or the keepalive interval elapsed), otherwise None.

        Raises:
            SceneError: If evaluation or rendering fails.
        """
        if now is None:
            now = time.monotonic()
        if self._started == 0.0:
            self._started = now
        if now >= self._next_poll:
            self._providers.poll()
            self._just_polled = True
            self._next_poll = now + 1.0 / self._scene.refresh

        evaluated = self._evaluate(now)
        self._just_polled = False
        signature = [item.signature for item in evaluated]
        if not self._output_dirty and signature == self._last_signature:
            if self._last_payload is not None and (
                now - self._last_yield >= self._scene.keepalive_interval
            ):
                self._last_yield = now
                return self._last_payload
            return None

        self._output_dirty = False
        payload = self._compose_and_encode(evaluated)
        self._last_signature = signature
        self._last_payload = payload
        self._last_yield = now
        return payload

    def render_frame(self, now: float = 0.0) -> bytes:
        """Render one frame for preview purposes without touching state.

        Polls the data providers once and evaluates every widget at the
        given time, so animations sit at their initial position. Graph
        widgets with a fresh (near-empty) history are filled with a
        representative synthetic series, so previews show a plausible
        sparkline instead of an empty box. Widget history and signatures
        are not advanced; safe to call alongside a running :meth:`tick`
        loop from another scene instance only.

        Args:
            now: Scene-relative time in seconds for expression variables.

        Returns:
            Encoded JPEG payload.

        Raises:
            SceneError: If evaluation or rendering fails.
        """
        self._providers.poll()
        evaluated = self._evaluate(self._started + now, poll=False)
        self._fill_graph_previews(evaluated)
        return self._compose_and_encode(evaluated)

    def _fill_graph_previews(self, evaluated: list[_Evaluated]) -> None:
        """Backfill sparse graph histories with a synthetic series.

        A preview renderer starts with an empty history, which would
        render as an invisible one-sample line; filling it keeps previews
        representative of the live widget.

        Args:
            evaluated: Evaluation results to patch (in place).
        """
        for item in evaluated:
            runtime = item.runtime
            widget = item.widget
            if runtime is None or not isinstance(widget, GraphWidget):
                continue
            if len(runtime.history) >= 2:
                continue
            base = runtime.history[-1] if runtime.history else 50.0
            if not isinstance(base, (int, float)):
                base = 50.0
            for i in range(widget.history):
                wave = (
                    base * 0.18 * ((i % 7) - 3) / 3
                    + base * 0.08 * ((i % 3) - 1)
                )
                runtime.history.append(max(0.0, base + wave))

    def _render_static(self, layers: Sequence[ImageLayer]) -> Image.Image:
        """Composite the static background layer once.

        Args:
            layers: Background image layers.

        Returns:
            RGBA canvas with the background applied.

        Raises:
            SceneError: If an asset cannot be loaded.
        """
        canvas = Image.new("RGBA", self._size, (0, 0, 0, 255))
        for index, layer in enumerate(layers):
            try:
                self._composite_background(canvas, layer)
            except SceneError as exc:
                # A missing or corrupt background image is skipped instead
                # of failing the whole scene.
                logger.warning("scene_background_unavailable", path=layer.path, error=str(exc))
            logger.debug("background_layer_composited", index=index)
        return canvas

    def _composite_background(self, canvas: Image.Image, layer: ImageLayer) -> None:
        """Composite one background layer onto the canvas.

        Args:
            canvas: Target RGBA canvas.
            layer: Background layer definition.

        Raises:
            SceneError: If the asset cannot be loaded.
        """
        sprite = get_sprite(layer.path)
        if layer.scale != 1.0:
            size = (
                max(1, int(sprite.width * layer.scale)),
                max(1, int(sprite.height * layer.scale)),
            )
            sprite = sprite.resize(size, Image.Resampling.LANCZOS)
        if layer.pos is None:
            sprite = sprite.resize(self._size, Image.Resampling.LANCZOS)
            dest = (0, 0)
        else:
            dest = layer.pos
        if layer.opacity < 1.0:
            alpha = sprite.getchannel("A").point(
                lambda a, o=layer.opacity: int(a * o)
            )
            sprite = sprite.copy()
            sprite.putalpha(alpha)
        canvas.alpha_composite(sprite, dest=dest)

    def _expression_vars(
        self, now: float, raw: float | str | None
    ) -> dict[str, float]:
        """Build the variable scope for widget expressions.

        Args:
            now: Monotonic time in seconds.
            raw: The widget's current source value if numeric.

        Returns:
            Variable mapping with ``t``, ``dt`` and ``v``.
        """
        return {
            "t": now - self._started,
            "dt": 1.0 / self._scene.max_fps,
            "v": float(raw) if isinstance(raw, (int, float)) else 0.0,
        }

    def _evaluate(
        self, now: float, *, poll: bool = False
    ) -> list[_Evaluated]:
        """Evaluate every widget for the current tick.

        Args:
            now: Monotonic time in seconds.
            poll: True when providers were polled on this tick, so graph
                widgets should append a new sample.

        Returns:
            Evaluation results in widget order.

        Raises:
            SceneError: If an expression is invalid.
        """
        results: list[_Evaluated] = []
        for index, widget in enumerate(self._scene.widgets):
            context = f"widgets[{index}] ({widget.type})"
            runtime = self._runtimes.get(id(widget))
            raw = self._fetch_source(widget, runtime, context)
            if raw is _UNAVAILABLE:
                results.append(
                    _Evaluated(
                        widget=widget,
                        runtime=runtime,
                        visible=False,
                        signature=("unavailable", index),
                    )
                )
                continue

            variables = self._expression_vars(now, raw)
            text = ""
            value01 = 0.0
            history: tuple[float, ...] = ()

            if isinstance(widget, TextWidget):
                text = self._format_text(widget, raw)
            elif isinstance(widget, (BarWidget, RingWidget)):
                target = max(0.0, min(100.0, float(raw)))
                if runtime is not None and runtime.animator is not None:
                    value01 = runtime.animator.update(target, now) / 100.0
                else:
                    value01 = target / 100.0
            elif isinstance(widget, GraphWidget):
                sample = float(raw)
                if runtime is not None:
                    if poll or not runtime.history:
                        runtime.history.append(sample)
                    history = tuple(runtime.history)

            visible = self._eval_visible(widget.visible, variables, context)
            offset_x = round(
                eval_number(widget.offset_x, variables, f"{context}.offset_x")
            )
            offset_y = round(
                eval_number(widget.offset_y, variables, f"{context}.offset_y")
            )
            opacity = eval_number(widget.opacity, variables, f"{context}.opacity")
            rotation = eval_number(widget.rotation, variables, f"{context}.rotation")

            signature: tuple[Any, ...] = (
                visible,
                round(value01, 3),
                offset_x,
                offset_y,
                round(opacity, 3),
                round(rotation, 3),
                history,
            )
            if isinstance(widget, TextWidget):
                signature += (text,)
            results.append(
                _Evaluated(
                    widget=widget,
                    runtime=runtime,
                    visible=visible,
                    text=text,
                    value01=value01,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    opacity=opacity,
                    rotation=rotation,
                    raw=raw if isinstance(raw, (int, float, str)) else None,
                    signature=signature,
                )
            )
        return results

    def _fetch_source(
        self,
        widget: Widget,
        runtime: WidgetRuntime | None,
        context: str,
    ) -> float | str | Any:
        """Fetch a widget's source value.

        Args:
            widget: Widget being evaluated.
            runtime: Widget runtime (data-bound widgets only).
            context: Widget description for log messages.

        Returns:
            Source value, or :data:`_UNAVAILABLE` when the source does not
            exist on this platform; the widget is hidden in that case.
        """
        source = getattr(widget, "source", None)
        if source is None:
            return None
        try:
            return self._providers.get(source)
        except SceneError:
            if source not in self._reported_missing:
                logger.warning(
                    "scene_source_unavailable", context=context, source=source
                )
                self._reported_missing.add(source)
            return _UNAVAILABLE

    def _eval_visible(
        self, visible: bool | str, variables: dict[str, float], context: str
    ) -> bool:
        """Evaluate the visibility flag.

        Args:
            visible: Bool or expression string.
            variables: Expression variables.
            context: Widget description for error messages.

        Returns:
            Visibility result.

        Raises:
            SceneError: If the expression is invalid.
        """
        if isinstance(visible, str):
            try:
                return bool(Expression(visible).evaluate(variables))
            except SceneError as exc:
                raise SceneError(f"{context}.visible: {exc}") from exc
        return visible

    @staticmethod
    def _format_text(widget: TextWidget, raw: float | str | None) -> str:
        """Render the text template for a text widget.

        Args:
            widget: Text widget.
            raw: Source value (when bound).

        Returns:
            Formatted string.

        Raises:
            SceneError: If the template cannot be formatted.
        """
        if widget.source is None and widget.value is None:
            return ""
        template = widget.value if widget.value is not None else "{value}"
        value = raw if raw is not None else widget.value
        try:
            return str(template).format(value=value)
        except (KeyError, IndexError, ValueError) as exc:
            raise SceneError(f"Invalid text template {template!r}: {exc}") from exc

    def _compose_and_encode(self, evaluated: list[_Evaluated]) -> bytes:
        """Composite the widget layer over the static background and encode.

        Args:
            evaluated: Current evaluation results.

        Returns:
            Encoded JPEG payload.

        Raises:
            SceneError: If rendering fails.
        """
        layer = Image.new("RGBA", self._size, (0, 0, 0, 0))
        for item in evaluated:
            if item.visible:
                self._render_widget(layer, item)
        frame = Image.alpha_composite(self._static, layer).convert("RGB")
        frame = self._builder.apply_base_rotation(frame)
        frame = self._builder.apply_brightness(frame)
        return self._builder.encode_jpeg(frame)

    def _render_widget(self, layer: Image.Image, item: _Evaluated) -> None:
        """Render one widget onto the widget layer.

        Args:
            layer: Target RGBA layer.
            item: Evaluation result for the widget.

        Raises:
            SceneError: If the widget type is unsupported.
        """
        widget = item.widget
        x, y, width, height = widget.rect
        px = x + item.offset_x
        py = y + item.offset_y

        if isinstance(widget, ImageWidget):
            try:
                render_image(
                    layer,
                    (px, py, width, height),
                    widget,
                    opacity=max(0.0, min(1.0, item.opacity)),
                    rotation=item.rotation,
                )
            except SceneError as exc:
                # A missing or corrupt sprite hides this widget instead of
                # failing the whole scene (mirrors unavailable sources).
                logger.warning("scene_image_unavailable", path=widget.path, error=str(exc))
            return

        scratch = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        local = (0, 0, width, height)
        if isinstance(widget, BarWidget):
            render_bar(draw, local, item.value01, widget)
        elif isinstance(widget, RingWidget):
            render_ring(draw, local, item.value01, widget)
        elif isinstance(widget, GraphWidget):
            if item.runtime is None:
                raise SceneError("Graph widget has no runtime state")
            render_graph(draw, local, item.runtime.history, widget)
        elif isinstance(widget, TextWidget):
            render_text(draw, local, item.text, widget)
        else:  # pragma: no cover - schema limits widget types
            raise SceneError(f"Unsupported widget type: {type(widget).__name__}")

        opacity = max(0.0, min(1.0, item.opacity))
        if opacity < 1.0:
            alpha = scratch.getchannel("A").point(lambda a, o=opacity: int(a * o))
            scratch.putalpha(alpha)
        layer.alpha_composite(scratch, dest=(px, py))
