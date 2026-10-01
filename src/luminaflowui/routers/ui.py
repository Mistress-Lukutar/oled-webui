"""
File:   ui.py
Brief:  Dashboard UI state endpoints: the persistent panel layout.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

from __future__ import annotations

from fastapi import APIRouter

from luminaflowui.config import Settings, get_settings
from luminaflowui.dependencies import DisplayDep
from luminaflowui.models.schemas import PanelLayout, StatusResponse
from luminaflowui.services.ui_layout import default_panels, load_panels, panels_path, save_panels

router = APIRouter(prefix="/api/ui", tags=["ui"])


def _settings() -> Settings:
    return get_settings()


@router.get("/panels", response_model=StatusResponse)
async def get_panels(_display: DisplayDep) -> StatusResponse:
    """Return the saved panel layout, or the default when none is stored."""
    layout = load_panels(panels_path(_settings()))
    if layout is None:
        layout = default_panels()
    return StatusResponse(data=layout.model_dump())


@router.put("/panels", response_model=StatusResponse)
async def put_panels(layout: PanelLayout, _display: DisplayDep) -> StatusResponse:
    """Persist the dashboard panel layout."""
    save_panels(panels_path(_settings()), layout)
    return StatusResponse(data=layout.model_dump())


@router.delete("/panels", response_model=StatusResponse)
async def reset_panels(_display: DisplayDep) -> StatusResponse:
    """Discard the saved layout and return to the default arrangement."""
    panels_path(_settings()).unlink(missing_ok=True)
    layout = default_panels()
    return StatusResponse(data=layout.model_dump())
