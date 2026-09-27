"""
File:   device.py
Brief:  Device connection, status and keepalive endpoints.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0
"""

from __future__ import annotations

from fastapi import APIRouter

from oled_webui.dependencies import DisplayDep
from oled_webui.models.schemas import KeepaliveRequest, StatusResponse

router = APIRouter(prefix="/api/device", tags=["device"])


@router.get("/status", response_model=StatusResponse)
async def get_status(display: DisplayDep) -> StatusResponse:
    """Return the full display status snapshot."""
    return StatusResponse(data=display.status())


@router.post("/connect", response_model=StatusResponse)
async def connect(display: DisplayDep) -> StatusResponse:
    """Open the USB device and perform the handshake."""
    result = await display.connect()
    return StatusResponse(data=result.model_dump())


@router.post("/disconnect", response_model=StatusResponse)
async def disconnect(display: DisplayDep) -> StatusResponse:
    """Close the USB device and stop background tasks."""
    await display.disconnect()
    return StatusResponse(data=display.status())


@router.post("/keepalive", response_model=StatusResponse)
async def set_keepalive(req: KeepaliveRequest, display: DisplayDep) -> StatusResponse:
    """Enable or disable the keepalive refresh loop."""
    await display.set_keepalive(req.enabled, req.interval)
    return StatusResponse(data=display.status()["keepalive"])


@router.get("/info", response_model=StatusResponse)
async def get_info(display: DisplayDep) -> StatusResponse:
    """Return the resolved device info from the last handshake."""
    handshake = display.require_connection()
    return StatusResponse(data=handshake.model_dump())


@router.post("/reconnect", response_model=StatusResponse)
async def reconnect(display: DisplayDep) -> StatusResponse:
    """Drop and re-establish the USB connection."""
    await display.disconnect()
    result = await display.connect()
    return StatusResponse(data=result.model_dump())
