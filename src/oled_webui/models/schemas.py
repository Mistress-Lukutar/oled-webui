"""
File:   schemas.py
Brief:  Pydantic request and response models for the HTTP API.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.3.0
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


class SaveSceneRequest(BaseModel):
    """Save scene YAML source request."""

    yaml: str = Field(..., min_length=1, max_length=200_000)
    name: str | None = Field(default=None, min_length=1, max_length=100)


class DeviceYamlRequest(BaseModel):
    """Save ARGB device definition YAML source request."""

    yaml: str = Field(..., min_length=1, max_length=200_000)
