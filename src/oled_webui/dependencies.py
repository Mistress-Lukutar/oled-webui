"""
File:   dependencies.py
Brief:  FastAPI dependency providers for services and connection guards.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from oled_webui.config import Settings, get_settings
from oled_webui.services.display_service import DisplayService
from oled_webui.services.preset_service import PresetService


def get_display_service(request: Request) -> DisplayService:
    """Fetch the display service created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide DisplayService instance.
    """
    return cast(DisplayService, request.app.state.display)


def get_preset_service(request: Request) -> PresetService:
    """Fetch the preset service created during app lifespan.

    Args:
        request: Incoming request carrying the app state.

    Returns:
        The application-wide PresetService instance.
    """
    return cast(PresetService, request.app.state.presets)


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
PresetsDep = Annotated[PresetService, Depends(get_preset_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
