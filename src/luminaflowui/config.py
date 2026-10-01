"""
File:   config.py
Brief:  Application settings loaded from environment variables and .env.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root is three levels up from src/luminaflowui/config.py.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for the OLED WebUI server.

    Attributes:
        host: Interface the HTTP server binds to.
        port: TCP port the HTTP server listens on.
        data_dir: Directory for scenes, fonts, ARGB state and the last frame.
        keepalive_interval: Seconds between keepalive frame resends.
        keepalive_enabled: Whether keepalive starts automatically on connect.
        brightness: Global software brightness percent for all content.
        jpeg_quality: Global JPEG encoding quality for all content.
        blank_on_display_off: Blank the panel when the Windows display
            powers off.
        preview_throttle: Minimum seconds between preview SSE events during video.
        auto_connect: Try to open the USB device on server startup.
    """

    model_config = SettingsConfigDict(
        env_prefix="LUMINA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", description="HTTP bind interface")
    # 8080 is permanently taken by the ZigbeeHUB service on this machine.
    port: int = Field(default=8090, ge=1, le=65535, description="HTTP listen port")
    data_dir: Path = Field(
        default=PROJECT_ROOT / "data",
        description="Directory for scenes, fonts, ARGB state and last frame",
    )
    keepalive_interval: float = Field(
        default=1.5, ge=0.1, description="Seconds between keepalive resends"
    )
    keepalive_enabled: bool = Field(
        default=True, description="Start keepalive automatically on connect"
    )
    brightness: int = Field(
        default=100, ge=0, le=200, description="Global brightness percent"
    )
    jpeg_quality: int = Field(
        default=95, ge=1, le=100, description="Global JPEG quality"
    )
    blank_on_display_off: bool = Field(
        default=False,
        description="Blank the panel when the Windows display powers off",
    )
    preview_throttle: float = Field(
        default=0.2, ge=0.1, description="Min seconds between video preview events"
    )
    auto_connect: bool = Field(
        default=True, description="Open the USB device on server startup"
    )
    openrgb_host: str = Field(
        default="127.0.0.1", description="OpenRGB SDK server host"
    )
    openrgb_port: int = Field(
        default=6742, ge=1, le=65535, description="OpenRGB SDK server port"
    )
    openrgb_exe: Path | None = Field(
        default=None,
        description="Path to OpenRGB.exe; when set, the server spawns and "
        "supervises the SDK server itself",
    )
    openrgb_task: str | None = Field(
        default=None,
        description="Task Scheduler entry that runs OpenRGB elevated; the "
        "server starts it via schtasks when the SDK port is not served",
    )
    openrgb_start_timeout: float = Field(
        default=45.0,
        ge=1.0,
        description="Seconds to wait for the spawned OpenRGB SDK port",
    )

    @property
    def argb_dir(self) -> Path:
        """Directory holding the ARGB layout state."""
        return self.data_dir / "argb"

    @property
    def argb_devices_dir(self) -> Path:
        """Directory holding ARGB device definition YAML files."""
        return self.argb_dir / "devices"

    @property
    def fonts_dir(self) -> Path:
        """Directory holding user-provided TTF/OTF fonts."""
        return self.data_dir / "fonts"

    @property
    def scenes_dir(self) -> Path:
        """Directory holding scene folders (YAML, meta, assets)."""
        return self.data_dir / "scenes"

    @property
    def last_frame_path(self) -> Path:
        """Path to the persisted last-sent JPEG frame."""
        return self.data_dir / "last_frame.jpg"

    def ensure_dirs(self) -> None:
        """Create all runtime data directories if missing."""
        for directory in (
            self.data_dir,
            self.fonts_dir,
            self.scenes_dir,
            self.argb_dir,
            self.argb_devices_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
