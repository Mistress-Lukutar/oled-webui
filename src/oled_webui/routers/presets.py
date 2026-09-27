"""
File:   presets.py
Brief:  Preset CRUD, save-current and apply endpoints.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from oled_webui.dependencies import ConnectedDisplayDep, PresetsDep, ScenesDep
from oled_webui.exceptions import ValidationError
from oled_webui.models.schemas import SavePresetRequest, StatusResponse
from oled_webui.services.preset_service import Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=StatusResponse)
async def list_presets(presets: PresetsDep) -> StatusResponse:
    """List all stored presets."""
    items = [preset.model_dump() for preset in presets.list_presets()]
    return StatusResponse(data={"presets": items})


def _preset_to_dict(preset: Preset) -> dict[str, Any]:
    """Serialize a preset for API responses."""
    return preset.model_dump()


@router.post("/save-current", response_model=StatusResponse)
async def save_current(
    req: SavePresetRequest, presets: PresetsDep, display: ConnectedDisplayDep
) -> StatusResponse:
    """Save the last applied display content as a named preset."""
    content = display.last_content
    preset = presets.save_from_content(req.name, content or {})
    return StatusResponse(data=_preset_to_dict(preset))


@router.get("/{preset_id}", response_model=StatusResponse)
async def get_preset(preset_id: str, presets: PresetsDep) -> StatusResponse:
    """Return one preset by id."""
    return StatusResponse(data=_preset_to_dict(presets.get_preset(preset_id)))


@router.delete("/{preset_id}", response_model=StatusResponse)
async def delete_preset(preset_id: str, presets: PresetsDep) -> StatusResponse:
    """Delete a preset and its stored asset."""
    presets.delete_preset(preset_id)
    return StatusResponse()


@router.post("/{preset_id}/apply", response_model=StatusResponse)
async def apply_preset(
    preset_id: str,
    presets: PresetsDep,
    scenes: ScenesDep,
    display: ConnectedDisplayDep,
) -> StatusResponse:
    """Re-render and send a stored preset to the display."""
    preset = presets.get_preset(preset_id)
    result = await _apply(presets, scenes, display, preset)
    return StatusResponse(data=result)


async def _apply(
    presets: PresetsDep,
    scenes: ScenesDep,
    display: ConnectedDisplayDep,
    preset: Preset,
) -> dict[str, Any]:
    """Dispatch a preset to the matching display service call.

    Args:
        presets: Preset service for asset lookup.
        scenes: Scene service for scene preset lookup.
        display: Display service used to render and send.
        preset: The preset to apply.

    Returns:
        Summary dict from the display service call.

    Raises:
        ValidationError: If the preset references a missing asset file.
    """
    params = preset.params
    if preset.type == "image":
        asset = presets.asset_path(preset)
        if asset is None or not asset.is_file():
            raise ValidationError(f"Preset asset missing for {preset.id}")
        return await display.send_image(
            asset,
            rotation=int(params.get("rotation", 0)),
            brightness=int(params.get("brightness", 100)),
            fit=str(params.get("fit", "contain")),
            quality=int(params.get("quality", 95)),
        )

    if preset.type == "color":
        return await display.send_color(
            str(preset.payload.get("color", "000000")),
            int(params.get("brightness", 100)),
        )

    if preset.type == "scene":
        scene_id = str(preset.payload.get("scene_id", ""))
        meta = scenes.get_meta(scene_id)
        document = scenes.load_document(scene_id)
        return await display.start_scene(document, scene_id, meta.name)

    font_name = preset.payload.get("font_name")
    return await display.send_text(
        text=str(preset.payload.get("text", "")),
        font_size=int(preset.payload.get("font_size", 48)),
        color=str(preset.payload.get("color", "ffffff")),
        background=str(preset.payload.get("background", "000000")),
        align=str(preset.payload.get("align", "center")),
        valign=str(preset.payload.get("valign", "middle")),
        padding=int(preset.payload.get("padding", 20)),
        rotation=int(params.get("rotation", 0)),
        brightness=int(params.get("brightness", 100)),
        quality=int(params.get("quality", 95)),
        font_name=str(font_name) if font_name else None,
    )
