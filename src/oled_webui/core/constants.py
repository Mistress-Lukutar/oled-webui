"""
File:   constants.py
Brief:  USB protocol constants and resolution profiles for 87AD:70DB.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.1.0

Protocol layout ported from the reverse-engineered CLI project; the byte
offsets below are verified against a real wire capture.
"""

from __future__ import annotations

from dataclasses import dataclass

# USB device identifiers for ChiZhu Tech USBDISPLAY.
VID: int = 0x87AD
PID: int = 0x70DB

# Bulk endpoints.
ENDPOINT_OUT: int = 0x01
ENDPOINT_IN: int = 0x81

# USB transfer timeouts in milliseconds.
DEFAULT_TIMEOUT_MS: int = 5000

# Handshake packet layout.
HANDSHAKE_SIZE: int = 64
HANDSHAKE_MAGIC: bytes = b"\x12\x34\x56\x78"
HANDSHAKE_CMD_DEV_INFO: int = 0x01
HANDSHAKE_CMD_OFFSET: int = 56

# Response layout for device info.
RESPONSE_SIZE: int = 1024
RESPONSE_VALID_INDEX: int = 24
RESPONSE_PM_INDEX: int = 24
RESPONSE_SUB_INDEX: int = 36

# Frame header layout.
FRAME_HEADER_SIZE: int = 64
FRAME_MAGIC: bytes = b"\x12\x34\x56\x78"
FRAME_CMD_JPEG: int = 2
FRAME_CMD_RGB565: int = 3
FRAME_FLAG_VALUE: int = 2

# Header offsets.
HEADER_MAGIC_OFFSET: int = 0
HEADER_CMD_OFFSET: int = 4
HEADER_WIDTH_OFFSET: int = 8
HEADER_HEIGHT_OFFSET: int = 12
HEADER_FLAG_OFFSET: int = 56
HEADER_LENGTH_OFFSET: int = 60

# USB bulk packet size for ZLP decision.
BULK_PACKET_SIZE: int = 512


@dataclass(frozen=True, slots=True)
class ResolutionSpec:
    """Width and height tuple for a panel profile."""

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PanelProfile:
    """Known panel configuration for 87AD:70DB."""

    pm: int
    sub: int | None
    resolution: ResolutionSpec


# Known PM/SUB combinations observed in the wild.
PANEL_PROFILES: tuple[PanelProfile, ...] = (
    PanelProfile(pm=63, sub=None, resolution=ResolutionSpec(1600, 720)),
    PanelProfile(pm=64, sub=None, resolution=ResolutionSpec(1600, 720)),
    PanelProfile(pm=65, sub=None, resolution=ResolutionSpec(1920, 462)),
    PanelProfile(pm=66, sub=None, resolution=ResolutionSpec(1920, 462)),
    PanelProfile(pm=1, sub=48, resolution=ResolutionSpec(1600, 720)),
    PanelProfile(pm=1, sub=49, resolution=ResolutionSpec(1920, 462)),
)

DEFAULT_RESOLUTION: ResolutionSpec = ResolutionSpec(480, 480)

# Fit modes supported by the render pipeline.
FIT_WIDTH: str = "width"
FIT_HEIGHT: str = "height"
FIT_STRETCH: str = "stretch"
FIT_CONTAIN: str = "contain"
FIT_MODES: tuple[str, ...] = (FIT_WIDTH, FIT_HEIGHT, FIT_STRETCH, FIT_CONTAIN)
DEFAULT_FIT: str = FIT_CONTAIN

# Rotation base applied by the reference C# implementation; the panel is
# natively mounted upside-down, so every frame gets this on top of the
# user-requested rotation.
DEFAULT_BASE_ROTATION: int = 180

# Encoding defaults.
DEFAULT_JPEG_QUALITY: int = 95


def resolve_resolution(pm: int, sub: int) -> ResolutionSpec:
    """Return the panel resolution for a PM/SUB pair.

    Args:
        pm: Panel model byte from the handshake response.
        sub: Sub-model byte from the handshake response.

    Returns:
        Matched resolution or the default 480x480 fallback.
    """
    for profile in PANEL_PROFILES:
        if profile.pm != pm:
            continue
        if profile.sub is not None and profile.sub != sub:
            continue
        return profile.resolution
    return DEFAULT_RESOLUTION
