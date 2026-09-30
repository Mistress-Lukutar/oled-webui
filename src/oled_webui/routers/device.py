"""
File:   device.py
Brief:  Device connection, status and display settings endpoints.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from fastapi import APIRouter

from oled_webui.dependencies import (
    DisplayDep,
    SceneRuntimeDep,
    ScenesDep,
    SettingsDep,
)
from oled_webui.models.schemas import DisplaySettingsRequest, StatusResponse
from oled_webui.services.content_state import restore_last_content

router = APIRouter(prefix="/api/device", tags=["device"])


@router.get("/status", response_model=StatusResponse)
async def get_status(display: DisplayDep) -> StatusResponse:
    """Return the full display status snapshot."""
    return StatusResponse(data=display.status())


@router.post("/connect", response_model=StatusResponse)
async def connect(
    display: DisplayDep,
    runtime: SceneRuntimeDep,
    scenes: ScenesDep,
    settings: SettingsDep,
) -> StatusResponse:
    """Open the USB device, perform the handshake and restore the last screen."""
    result = await display.connect()
    await restore_last_content(runtime, scenes, settings)
    return StatusResponse(data=result.model_dump())


@router.post("/disconnect", response_model=StatusResponse)
async def disconnect(display: DisplayDep) -> StatusResponse:
    """Close the USB device and stop background tasks."""
    await display.disconnect()
    return StatusResponse(data=display.status())


@router.get("/settings", response_model=StatusResponse)
async def get_display_settings(display: DisplayDep) -> StatusResponse:
    """Return the persisted display settings snapshot."""
    return StatusResponse(data=display.display_settings())


@router.post("/settings", response_model=StatusResponse)
async def set_display_settings(
    req: DisplaySettingsRequest, display: DisplayDep
) -> StatusResponse:
    """Update global display settings (keepalive, brightness, quality)."""
    data = await display.set_display_settings(
        keepalive_enabled=req.keepalive_enabled,
        keepalive_interval=req.keepalive_interval,
        brightness=req.brightness,
        quality=req.quality,
        blank_on_display_off=req.blank_on_display_off,
    )
    return StatusResponse(data=data)


@router.get("/info", response_model=StatusResponse)
async def get_info(display: DisplayDep) -> StatusResponse:
    """Return the resolved device info from the last handshake."""
    handshake = display.require_connection()
    return StatusResponse(data=handshake.model_dump())


@router.post("/reconnect", response_model=StatusResponse)
async def reconnect(
    display: DisplayDep,
    runtime: SceneRuntimeDep,
    scenes: ScenesDep,
    settings: SettingsDep,
) -> StatusResponse:
    """Re-establish the USB connection and restore the last screen."""
    await display.disconnect()
    result = await display.connect()
    await restore_last_content(runtime, scenes, settings)
    return StatusResponse(data=result.model_dump())
