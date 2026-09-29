"""
File:   exceptions.py
Brief:  Exception hierarchy and JSON error handlers for the WebUI.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


class OledWebUIError(Exception):
    """Base exception for all application errors."""


class TransportError(OledWebUIError):
    """Raised when a USB transport operation fails."""


class HandshakeError(TransportError):
    """Raised when the device handshake does not complete as expected."""


class DeviceNotFoundError(TransportError):
    """Raised when the requested USB device is not found."""


class DeviceNotConnectedError(OledWebUIError):
    """Raised when an operation requires a connected display."""


class RenderError(OledWebUIError):
    """Raised when image rendering or encoding fails."""


class ValidationError(OledWebUIError):
    """Raised when user input fails validation."""


class VideoError(OledWebUIError):
    """Raised when video decoding or playback fails."""


class PresetNotFoundError(OledWebUIError):
    """Raised when the requested preset does not exist."""


class SceneNotFoundError(OledWebUIError):
    """Raised when the requested scene does not exist."""


class SceneError(OledWebUIError):
    """Raised when a scene document or widget rendering is invalid."""


class ArgbError(OledWebUIError):
    """Raised when an ARGB layout or effect operation is invalid."""


class OpenRgbError(OledWebUIError):
    """Raised when the OpenRGB SDK server cannot be reached or misbehaves."""


def setup_exception_handlers(app: FastAPI) -> None:
    """Register JSON error handlers normalizing errors to a uniform shape.

    Args:
        app: FastAPI application instance.
    """
    from fastapi import Request, status
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(
            str(part) for part in first.get("loc", []) if part != "body"
        )
        message = first.get("msg", "Invalid request")
        text = f"{location}: {message}" if location else message
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"success": False, "error": text, "data": None},
        )

    @app.exception_handler(DeviceNotConnectedError)
    async def _not_connected(
        _request: Request, exc: DeviceNotConnectedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(DeviceNotFoundError)
    async def _not_found_device(
        _request: Request, exc: DeviceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(HandshakeError)
    async def _handshake(_request: Request, exc: HandshakeError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(PresetNotFoundError)
    async def _preset_not_found(
        _request: Request, exc: PresetNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(SceneNotFoundError)
    async def _scene_not_found(
        _request: Request, exc: SceneNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(SceneError)
    async def _scene_error(_request: Request, exc: SceneError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(ArgbError)
    async def _argb_error(_request: Request, exc: ArgbError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(OpenRgbError)
    async def _openrgb_error(_request: Request, exc: OpenRgbError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(ValidationError)
    async def _validation(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(OledWebUIError)
    async def _generic(_request: Request, exc: OledWebUIError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": str(exc), "data": None},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": str(exc.detail), "data": None},
        )
