"""
File:   frame.py
Brief:  Frame content endpoints: image, color, text, power, preview.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.3.0
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Response, UploadFile
from fastapi.responses import FileResponse

from oled_webui.dependencies import ConnectedDisplayDep, SettingsDep
from oled_webui.exceptions import SceneNotFoundError, ValidationError
from oled_webui.models.schemas import StatusResponse, TestRequest, TextRequest

router = APIRouter(prefix="/api/frame", tags=["frame"])

ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
)
ALLOWED_FONT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".otf"})


def _save_upload(upload: UploadFile, uploads_dir: Path, name_hint: str) -> Path:
    """Persist an uploaded file into the uploads directory.

    Args:
        upload: The uploaded multipart file.
        uploads_dir: Target directory for uploads.
        name_hint: Prefix used when the original name is unusable.

    Returns:
        Path of the stored file.

    Raises:
        ValidationError: If the file has no usable name or a bad extension.
    """
    original = Path(upload.filename or "")
    suffix = original.suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Unsupported image extension: {suffix or '(none)'}")
    stem = original.stem if original.stem else name_hint
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:60]
    dest = uploads_dir / f"{uuid.uuid4().hex[:8]}_{safe_stem}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    return dest


@router.post("/image", response_model=StatusResponse)
async def send_image(
    display: ConnectedDisplayDep,
    settings: SettingsDep,
    file: UploadFile,
    rotation: int = Form(default=0),
    fit: str = Form(default="contain"),
) -> StatusResponse:
    """Upload an image and show it on the display."""
    path = _save_upload(file, settings.uploads_dir, "image")
    result = await display.send_image(path, rotation, fit)
    return StatusResponse(data=result)


@router.post("/color", response_model=StatusResponse)
async def send_color(
    display: ConnectedDisplayDep,
    color: str = Form(default="ffffff", pattern=r"^#?[0-9a-fA-F]{6}$"),
) -> StatusResponse:
    """Fill the display with a solid color."""
    result = await display.send_color(color)
    return StatusResponse(data=result)


@router.post("/text", response_model=StatusResponse)
async def send_text(display: ConnectedDisplayDep, req: TextRequest) -> StatusResponse:
    """Render text and show it on the display."""
    result = await display.send_text(
        text=req.text,
        font_size=req.font_size,
        color=req.color,
        background=req.background,
        align=req.align,
        valign=req.valign,
        padding=req.padding,
        rotation=req.rotation,
        font_name=req.font_name,
    )
    return StatusResponse(data=result)


@router.post("/off", response_model=StatusResponse)
async def power_off(display: ConnectedDisplayDep) -> StatusResponse:
    """Blank the display with a black frame."""
    await display.power_off()
    return StatusResponse()


@router.post("/on", response_model=StatusResponse)
async def power_on(display: ConnectedDisplayDep) -> StatusResponse:
    """Restore the last cached frame."""
    await display.power_on()
    return StatusResponse()


@router.post("/test", response_model=StatusResponse)
async def run_test(display: ConnectedDisplayDep, req: TestRequest) -> StatusResponse:
    """Cycle the red/green/blue/black test pattern."""
    await display.run_test(req.delay)
    return StatusResponse()


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
