"""
File:   system.py
Brief:  System-level endpoints: the device registry backing the dashboard.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.1.0
"""

from __future__ import annotations

from fastapi import APIRouter

from oled_webui.dependencies import ArgbDep, DisplayDep
from oled_webui.models.schemas import StatusResponse, SystemDeviceInfo

router = APIRouter(prefix="/api/system", tags=["system"])

# Synthetic device registry ids. A single HID panel and one OpenRGB
# connection exist today; multi-device support will extend this list.
DISPLAY_DEVICE_ID: str = "display:0"
ARGB_DEVICE_ID: str = "argb:openrgb"


@router.get("/devices", response_model=StatusResponse)
async def list_devices(display: DisplayDep, argb: ArgbDep) -> StatusResponse:
    """List content-producing devices known to the system.

    The frontend derives available dashboard panels from this registry.
    """
    status = display.status()
    resolution = status["resolution"]
    devices = [
        SystemDeviceInfo(
            id=DISPLAY_DEVICE_ID,
            kind="display",
            name=f"OLED {resolution['width']}×{resolution['height']}",
            connected=bool(status["connected"]),
        )
    ]
    argb_status = argb.status()
    controller = argb_status.get("controller")
    zones = argb_status.get("zones", [])
    devices.append(
        SystemDeviceInfo(
            id=ARGB_DEVICE_ID,
            kind="argb",
            name=f"{controller or 'OpenRGB'} · {len(zones)} zones",
            connected=bool(argb_status.get("connected")),
        )
    )
    return StatusResponse(data={"devices": [device.model_dump() for device in devices]})
