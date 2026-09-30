"""
File:   scene_runtime.py
Brief:  Scene activation runtime: drives every device from its scene section.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from oled_webui.exceptions import OledWebUIError

if TYPE_CHECKING:
    from oled_webui.argb.service import ArgbService
    from oled_webui.services.display_service import DisplayService
    from oled_webui.services.scene_service import SceneService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SceneActivation:
    """Identity of the scene being activated, shared with device runtimes."""

    scene_id: str
    name: str


class DeviceRuntime(Protocol):
    """One registered device backend driven by a scene section.

    A new device kind plugs in by implementing this protocol and calling
    :meth:`SceneRuntime.register`; the scene document gains a matching
    typed section in ``scene/schema.py``.
    """

    key: str

    async def activate(self, section: Any, activation: SceneActivation) -> None:
        """Start the device with its scene section; ``None`` stops it."""
        ...


class ScreenRuntime:
    """Drives the OLED panel from the scene's ``screen`` section."""

    key = "screen"

    def __init__(self, display: DisplayService) -> None:
        self._display = display

    async def activate(self, section: Any, activation: SceneActivation) -> None:
        """Start panel playback, or stop it when the section is absent.

        Args:
            section: Validated :class:`ScreenDocument` or ``None``.
            activation: Scene identity used for state tracking.
        """
        if section is None:
            await self._display.stop_scene()
            return
        await self._display.start_scene(section, activation.scene_id, activation.name)


class ArgbRuntime:
    """Drives the ARGB engine from the scene's ``argb`` section."""

    key = "argb"

    def __init__(self, argb: ArgbService) -> None:
        self._argb = argb

    async def activate(self, section: Any, activation: SceneActivation) -> None:
        """Start the effect engine, or stop it when the section is absent.

        The layout is adopted before connecting so header size sync sees
        the fresh section. Connecting to OpenRGB is best-effort: the
        engine runs without a connection and reconnects itself once the
        SDK server appears.

        Args:
            section: Validated :class:`ArgbLayout` or ``None``.
            activation: Unused (ARGB is scene-scoped, not addressable).
        """
        if section is None:
            await self._argb.stop()
            return
        await self._argb.apply(section)
        try:
            await self._argb.connect()
        except OledWebUIError as exc:
            logger.warning("argb_scene_connect_failed", error=str(exc))


class SceneRuntime:
    """Applies a whole scene file to every registered device runtime.

    The scene is the single description of the computer's appearance:
    a section present in the scene starts (or restarts) that device with
    it, a missing section stops the device.
    """

    def __init__(
        self,
        scenes: SceneService,
        display: DisplayService,
        argb: ArgbService,
    ) -> None:
        self._scenes = scenes
        self._active_scene_id: str | None = None
        self._runtimes: list[DeviceRuntime] = [
            ScreenRuntime(display),
            ArgbRuntime(argb),
        ]

    def register(self, runtime: DeviceRuntime) -> None:
        """Add a device runtime to the activation loop.

        Args:
            runtime: Device backend whose ``key`` matches a scene section.
        """
        self._runtimes.append(runtime)

    @property
    def active_scene_id(self) -> str | None:
        """Id of the last activated scene, if any."""
        return self._active_scene_id

    async def activate(self, scene_id: str) -> dict[str, Any]:
        """Apply a stored scene to all registered devices.

        Every device is driven independently: one failing device does not
        stop the others; its error is reported in the result payload.

        Args:
            scene_id: Scene to activate.

        Returns:
            Mapping of device key to ``"started"``, ``"stopped"`` or an
            ``"error: ..."`` marker.

        Raises:
            SceneNotFoundError: If the scene does not exist.
            SceneError: If the scene YAML does not validate.
        """
        meta = self._scenes.get_meta(scene_id)
        document = self._scenes.load_document(scene_id)
        activation = SceneActivation(scene_id=scene_id, name=meta.name)
        results: dict[str, Any] = {}
        for runtime in self._runtimes:
            section = getattr(document, runtime.key, None)
            try:
                await runtime.activate(section, activation)
            except OledWebUIError as exc:
                logger.warning(
                    "scene_device_activate_failed",
                    scene_id=scene_id,
                    device=runtime.key,
                    error=str(exc),
                )
                results[runtime.key] = f"error: {exc}"
                continue
            results[runtime.key] = "started" if section is not None else "stopped"
        self._active_scene_id = scene_id
        logger.info("scene_activated", scene_id=scene_id, devices=results)
        return results

    async def deactivate(self) -> None:
        """Stop every registered device (scene playback stops everywhere)."""
        activation = SceneActivation(scene_id="", name="")
        for runtime in self._runtimes:
            try:
                await runtime.activate(None, activation)
            except OledWebUIError as exc:
                logger.warning(
                    "scene_device_deactivate_failed",
                    device=runtime.key,
                    error=str(exc),
                )
        self._active_scene_id = None
