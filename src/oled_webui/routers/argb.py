"""
File:   argb.py
Brief:  ARGB status, active scene layout, device library and preview endpoints.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter

from oled_webui.argb.schema import ArgbLayout
from oled_webui.dependencies import ArgbDep
from oled_webui.models.schemas import DeviceYamlRequest, StatusResponse

router = APIRouter(prefix="/api/argb", tags=["argb"])


@router.get("/status", response_model=StatusResponse)
async def get_status(argb: ArgbDep) -> StatusResponse:
    """Return the ARGB subsystem status (OpenRGB, zones, engine state)."""
    return StatusResponse(data=argb.status())


@router.post("/connect", response_model=StatusResponse)
async def connect(argb: ArgbDep) -> StatusResponse:
    """Open the OpenRGB SDK session and discover header zones."""
    return StatusResponse(data=await argb.connect())


@router.post("/disconnect", response_model=StatusResponse)
async def disconnect(argb: ArgbDep) -> StatusResponse:
    """Stop the engine and close the OpenRGB SDK session."""
    return StatusResponse(data=await argb.disconnect())


@router.get("/active", response_model=StatusResponse)
async def get_active(argb: ArgbDep) -> StatusResponse:
    """Return the currently applied layout and engine state.

    Layouts live in scene files (the ``argb`` section); this endpoint
    exposes the runtime copy for previews and status displays.
    """
    return StatusResponse(
        data={
            "layout": argb.layout.model_dump(),
            "running": argb.is_running,
        }
    )


@router.get("/devices", response_model=StatusResponse)
async def list_devices(argb: ArgbDep) -> StatusResponse:
    """List installed device definitions with their layout usage."""
    return StatusResponse(data={"devices": argb.list_device_definitions()})


@router.get("/devices/{device_id}", response_model=StatusResponse)
async def get_device(device_id: str, argb: ArgbDep) -> StatusResponse:
    """Return one device definition as raw YAML plus parsed form."""
    return StatusResponse(data=argb.get_device_definition(device_id))


@router.post("/devices", response_model=StatusResponse)
async def create_device(body: DeviceYamlRequest, argb: ArgbDep) -> StatusResponse:
    """Validate and install a new device definition from YAML source."""
    definition = await argb.save_device_definition(body.yaml)
    return StatusResponse(data={"definition": definition})


@router.put("/devices/{device_id}", response_model=StatusResponse)
async def update_device(
    device_id: str, body: DeviceYamlRequest, argb: ArgbDep
) -> StatusResponse:
    """Validate and store an updated device definition."""
    definition = await argb.save_device_definition(body.yaml, expected_id=device_id)
    return StatusResponse(data={"definition": definition})


@router.delete("/devices/{device_id}", response_model=StatusResponse)
async def delete_device(device_id: str, argb: ArgbDep) -> StatusResponse:
    """Remove a device definition; rejected while layout instances use it."""
    await argb.delete_device_definition(device_id)
    return StatusResponse(data={"deleted": device_id})


@router.post("/render_preview", response_model=StatusResponse)
async def render_preview(
    layout: ArgbLayout, argb: ArgbDep, t: float | None = None
) -> StatusResponse:
    """Render one frame of the given layout without touching hardware."""
    buffers = await anyio.to_thread.run_sync(
        lambda: argb.render_preview(layout, t)
    )
    return StatusResponse(data={"buffers": buffers})
