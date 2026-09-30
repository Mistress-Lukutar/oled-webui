"""
File:   models.py
Brief:  Pydantic data models for device handshake and panel profile.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from oled_webui.core.constants import resolve_resolution


class Resolution(BaseModel):
    """Panel resolution as width and height."""

    width: int = Field(..., ge=1, description="Panel width in pixels")
    height: int = Field(..., ge=1, description="Panel height in pixels")

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


class DeviceProfile(BaseModel):
    """Resolved panel profile after handshake."""

    pm: int = Field(..., description="Panel model byte")
    sub: int = Field(..., description="Sub-model byte")
    resolution: Resolution = Field(..., description="Panel resolution")

    @classmethod
    def from_raw(cls, pm: int, sub: int) -> DeviceProfile:
        """Build a profile from raw handshake bytes.

        Args:
            pm: Panel model byte.
            sub: Sub-model byte.

        Returns:
            Resolved device profile.
        """
        resolved = resolve_resolution(pm, sub)
        return cls(
            pm=pm,
            sub=sub,
            resolution=Resolution(width=resolved.width, height=resolved.height),
        )


class HandshakeResult(BaseModel):
    """Result of a successful device handshake."""

    vid: int = Field(..., description="USB vendor ID")
    pid: int = Field(..., description="USB product ID")
    pm: int = Field(..., description="Panel model byte")
    sub: int = Field(..., description="Sub-model byte")
    resolution: Resolution = Field(..., description="Panel resolution")

    @property
    def device_key(self) -> str:
        """Return the canonical ``VID:PID`` string."""
        return f"{self.vid:04X}:{self.pid:04X}"

    @classmethod
    def from_profile(
        cls,
        vid: int,
        pid: int,
        profile: DeviceProfile,
    ) -> HandshakeResult:
        """Build a handshake result from a resolved profile.

        Args:
            vid: USB vendor ID.
            pid: USB product ID.
            profile: Resolved device profile.

        Returns:
            Handshake result.
        """
        return cls(
            vid=vid,
            pid=pid,
            pm=profile.pm,
            sub=profile.sub,
            resolution=profile.resolution,
        )
