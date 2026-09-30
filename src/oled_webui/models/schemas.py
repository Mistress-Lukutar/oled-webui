"""
File:   schemas.py
Brief:  Pydantic request and response models for the HTTP API.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    """Uniform response envelope for all API actions."""

    success: bool = Field(default=True, description="Whether the action succeeded")
    error: str | None = Field(default=None, description="Error message, if any")
    data: dict[str, Any] | None = Field(default=None, description="Action result data")


class DisplaySettingsRequest(BaseModel):
    """Display settings update; omitted fields keep their current value."""

    keepalive_enabled: bool | None = Field(None, description="Run keepalive loop")
    keepalive_interval: float | None = Field(
        None, ge=0.1, description="Resend interval in seconds"
    )
    brightness: int | None = Field(
        None, ge=0, le=200, description="Global brightness percent"
    )
    quality: int | None = Field(None, ge=1, le=100, description="Global JPEG quality")
    blank_on_display_off: bool | None = Field(
        None, description="Blank panel when the Windows display powers off"
    )


class TestRequest(BaseModel):
    """Test pattern request."""

    delay: float = Field(default=1.0, ge=0.1, le=10, description="Seconds per color")


class ArgbSettingsRequest(BaseModel):
    """ARGB settings update; omitted fields keep their current value."""

    off_on_display_off: bool | None = Field(
        None, description="Turn lighting off when the Windows display powers off"
    )


class PanelConfig(BaseModel):
    """One dashboard panel instance."""

    id: str = Field(..., min_length=1, max_length=64, description="Unique panel id")
    type: str = Field(..., min_length=1, max_length=40, description="Panel type")
    device: str | None = Field(
        None, max_length=64, description="Owning device id for device panels"
    )
    aspect: float = Field(1.0, gt=0.25, le=4.0, description="Tile width/height ratio")


class PanelLayout(BaseModel):
    """Ordered dashboard panel layout."""

    version: int = Field(1, ge=1, description="Layout schema version")
    panels: list[PanelConfig] = Field(
        default_factory=list, max_length=32, description="Panels in display order"
    )


class SystemDeviceInfo(BaseModel):
    """One entry of the system device registry."""

    id: str = Field(..., description="Stable device id, e.g. display:0")
    kind: str = Field(..., description="Device kind: display or argb")
    name: str = Field(..., description="Human-readable device name")
    connected: bool = Field(..., description="Live connection state")


class SaveSceneRequest(BaseModel):
    """Save scene YAML source request."""

    yaml: str = Field(..., min_length=1, max_length=200_000)
    name: str | None = Field(default=None, min_length=1, max_length=100)


class DeviceYamlRequest(BaseModel):
    """Save ARGB device definition YAML source request."""

    yaml: str = Field(..., min_length=1, max_length=200_000)
