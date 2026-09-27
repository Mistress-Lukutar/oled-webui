"""
File:   schemas.py
Brief:  Pydantic request and response models for the HTTP API.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AlignH = Literal["left", "center", "right"]
AlignV = Literal["top", "middle", "bottom"]


class StatusResponse(BaseModel):
    """Uniform response envelope for all API actions."""

    success: bool = Field(default=True, description="Whether the action succeeded")
    error: str | None = Field(default=None, description="Error message, if any")
    data: dict[str, Any] | None = Field(default=None, description="Action result data")


class ColorRequest(BaseModel):
    """Solid color frame request."""

    color: str = Field(
        ...,
        pattern=r"^#?[0-9a-fA-F]{6}$",
        description="Hex color, with or without leading #",
    )
    brightness: int = Field(default=100, ge=0, le=200)


class TextRequest(BaseModel):
    """Text frame request."""

    text: str = Field(..., min_length=1, max_length=5000)
    font_size: int = Field(default=48, ge=8, le=500)
    color: str = Field(default="ffffff", pattern=r"^#?[0-9a-fA-F]{6}$")
    background: str = Field(default="000000", pattern=r"^#?[0-9a-fA-F]{6}$")
    align: AlignH = Field(default="center")
    valign: AlignV = Field(default="middle")
    padding: int = Field(default=20, ge=0, le=500)
    rotation: int = Field(default=0, ge=-360, le=360)
    brightness: int = Field(default=100, ge=0, le=200)
    quality: int = Field(default=95, ge=1, le=100)
    font_name: str | None = Field(default=None, description="TTF file in data/fonts")


class KeepaliveRequest(BaseModel):
    """Keepalive toggle request."""

    enabled: bool = Field(..., description="Whether keepalive should run")
    interval: float | None = Field(
        default=None, ge=0.1, description="Resend interval in seconds"
    )


class TestRequest(BaseModel):
    """Test pattern request."""

    delay: float = Field(default=1.0, ge=0.1, le=10, description="Seconds per color")


class SavePresetRequest(BaseModel):
    """Save-current-content-as-preset request."""

    name: str = Field(..., min_length=1, max_length=100)


class SaveSceneRequest(BaseModel):
    """Save scene YAML source request."""

    yaml: str = Field(..., min_length=1, max_length=200_000)
    name: str | None = Field(default=None, min_length=1, max_length=100)
