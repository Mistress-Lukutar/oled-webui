"""
File:   dependencies.py
Brief:  FastAPI dependency providers for services and connection guards.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from oled_webui.argb.service import ArgbService
from oled_webui.config import Settings, get_settings
from oled_webui.services.display_service import DisplayService
from oled_webui.services.scene_runtime import SceneRuntime
from oled_webui.services.scene_service import SceneService


def get_display_service(request: Request) -> DisplayService:
    """Fetch the display service created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide DisplayService instance.
    """
    return cast(DisplayService, request.app.state.display)


def get_scene_service(request: Request) -> SceneService:
    """Fetch the scene service created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide SceneService instance.
    """
    return cast(SceneService, request.app.state.scenes)


def get_argb_service(request: Request) -> ArgbService:
    """Fetch the ARGB service created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide ArgbService instance.
    """
    return cast(ArgbService, request.app.state.argb)


def get_scene_runtime(request: Request) -> SceneRuntime:
    """Fetch the scene runtime created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide SceneRuntime instance.
    """
    return cast(SceneRuntime, request.app.state.scene_runtime)


def require_connection(
    display: Annotated[DisplayService, Depends(get_display_service)],
) -> DisplayService:
    """Guard dependency: raise 409 when the display is not connected.

    Args:
        display: The display service instance.

    Returns:
        The display service when a connection exists.
    """
    display.require_connection()
    return display


DisplayDep = Annotated[DisplayService, Depends(get_display_service)]
ConnectedDisplayDep = Annotated[DisplayService, Depends(require_connection)]
ScenesDep = Annotated[SceneService, Depends(get_scene_service)]
ArgbDep = Annotated[ArgbService, Depends(get_argb_service)]
SceneRuntimeDep = Annotated[SceneRuntime, Depends(get_scene_runtime)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
