"""
File:   frame.py
Brief:  Frame endpoints: preview and the font library.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Response, UploadFile
from fastapi.responses import FileResponse

from oled_webui.dependencies import ConnectedDisplayDep, SettingsDep
from oled_webui.exceptions import SceneNotFoundError, ValidationError
from oled_webui.models.schemas import StatusResponse

router = APIRouter(prefix="/api/frame", tags=["frame"])

ALLOWED_FONT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".otf"})


@router.get("/preview")
async def get_preview(display: ConnectedDisplayDep) -> Response:
    """Return the last sent frame as JPEG for browser preview."""
    data = display.get_preview()
    if data is None:
        return Response(status_code=404, media_type="text/plain", content="no frame")
    return Response(content=data, media_type="image/jpeg")


@router.get("/fonts", response_model=StatusResponse)
async def list_fonts(settings: SettingsDep) -> StatusResponse:
    """List user-provided font files available for text rendering."""
    return StatusResponse(data={"fonts": _list_library_fonts(settings)})


@router.post("/fonts", response_model=StatusResponse)
async def upload_fonts(
    settings: SettingsDep, files: list[UploadFile]
) -> StatusResponse:
    """Add TTF/OTF font files to the shared font library.

    Scenes reference library fonts as ``fonts/<name>.ttf``; the editor's
    font picker lists this library, so uploads here become selectable
    everywhere without re-uploading per scene.
    """
    stored: list[str] = []
    for file in files:
        original = Path(file.filename or "")
        suffix = original.suffix.lower()
        if suffix not in ALLOWED_FONT_EXTENSIONS:
            raise ValidationError(f"Unsupported font extension: {suffix or '(none)'}")
        stem = original.stem or "font"
        safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:60]
        dest = settings.fonts_dir / f"{safe_stem}{suffix}"
        counter = 1
        while dest.exists():
            dest = settings.fonts_dir / f"{safe_stem}-{counter}{suffix}"
            counter += 1
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        stored.append(dest.name)
    if not stored:
        raise ValidationError("No font files provided")
    return StatusResponse(data={"fonts": _list_library_fonts(settings)})


@router.get("/fonts/{name}")
async def get_font(name: str, settings: SettingsDep) -> FileResponse:
    """Serve a shared font file for browser-side canvas rendering."""
    safe = _safe_font_name(name)
    if safe is None:
        raise ValidationError(f"Invalid font name: {name!r}")
    path = settings.fonts_dir / safe
    if not path.is_file():
        raise SceneNotFoundError(f"Font not found: {name}")
    media_type = "font/ttf" if path.suffix.lower() == ".ttf" else "font/otf"
    return FileResponse(path, media_type=media_type)


@router.delete("/fonts/{name}", response_model=StatusResponse)
async def delete_font(name: str, settings: SettingsDep) -> StatusResponse:
    """Remove one font file from the shared library."""
    safe = _safe_font_name(name)
    if safe is None:
        raise ValidationError(f"Invalid font name: {name!r}")
    path = settings.fonts_dir / safe
    if not path.is_file():
        raise SceneNotFoundError(f"Font not found: {name}")
    path.unlink()
    return StatusResponse(data={"fonts": _list_library_fonts(settings)})


def _list_library_fonts(settings: SettingsDep) -> list[str]:
    """Return sorted font file names stored in the shared library."""
    return sorted(
        p.name
        for p in settings.fonts_dir.glob("*")
        if p.suffix.lower() in ALLOWED_FONT_EXTENSIONS
    )


def _safe_font_name(name: str) -> str | None:
    """Validate a library font file name, returning None when unsafe.

    Args:
        name: Client-provided file name.

    Returns:
        The name when it is a flat file name, else None.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    return name
