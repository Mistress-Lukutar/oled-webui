"""
File:   main.py
Brief:  FastAPI application factory, lifespan and entry point.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from oled_webui.config import get_settings
from oled_webui.exceptions import OledWebUIError, setup_exception_handlers
from oled_webui.routers import device as device_router
from oled_webui.routers import frame as frame_router
from oled_webui.routers import presets as presets_router
from oled_webui.routers import scenes as scenes_router
from oled_webui.routers import video as video_router
from oled_webui.services.display_service import DisplayService
from oled_webui.services.event_bus import EventBus
from oled_webui.services.preset_service import PresetService
from oled_webui.services.scene_service import SceneService
from oled_webui.services.sse_manager import sse_manager

logger = structlog.get_logger(__name__)

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
STATIC_DIR: Path = PROJECT_ROOT / "static"

# Event bus topics bridged 1:1 to SSE event names.
SSE_TOPICS: tuple[str, ...] = (
    "connection",
    "frame_updated",
    "keepalive",
    "video",
    "scene",
    "error",
)


def configure_logging() -> None:
    """Configure structlog with a readable console renderer."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create services, bridge events to SSE, optionally auto-connect.

    Args:
        app: The FastAPI application instance.

    Yields:
        None once the application is ready to serve.
    """
    configure_logging()
    settings = get_settings()
    settings.ensure_dirs()

    bus = EventBus()
    for topic in SSE_TOPICS:
        bus.subscribe(topic, _make_sse_bridge(topic))

    display = DisplayService(settings, bus)
    app.state.display = display
    app.state.presets = PresetService(settings)
    app.state.scenes = SceneService(settings)

    if settings.auto_connect:
        try:
            await display.connect()
        except OledWebUIError as exc:
            # Startup must not fail without hardware; the UI offers Connect.
            logger.warning("auto_connect_failed", error=str(exc))

    yield

    await display.shutdown()


def _make_sse_bridge(topic: str) -> Any:
    """Build an event bus handler forwarding a topic to SSE clients.

    Args:
        topic: Event bus topic to bridge.

    Returns:
        An async handler suitable for EventBus.subscribe.
    """

    async def _bridge(payload: dict[str, Any]) -> None:
        sse_manager.broadcast(topic, payload)

    return _bridge


def create_app() -> FastAPI:
    """Build the FastAPI application with routers, SSE and static files.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(title="OledWebUI", version="0.1.0", lifespan=lifespan)
    setup_exception_handlers(app)

    app.include_router(device_router.router)
    app.include_router(frame_router.router)
    app.include_router(video_router.router)
    app.include_router(presets_router.router)
    app.include_router(scenes_router.router)

    @app.get("/events")
    async def events() -> Any:
        """Server-sent events stream for real-time UI updates."""
        from fastapi.responses import StreamingResponse

        return StreamingResponse(
            sse_manager.subscribe(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        """Liveness probe independent of device state."""
        return JSONResponse(
            {"status": "ok", "connected": request.app.state.display.is_connected}
        )

    _mount_static(app)
    return app


def _mount_static(app: FastAPI) -> None:
    """Serve the built SPA from static/dist when the frontend is built."""
    dist_dir = STATIC_DIR / "dist"
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="spa")
    elif STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    """Console entry point: run the uvicorn server."""
    settings = get_settings()
    uvicorn.run(
        "oled_webui.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
