"""
File:   scenes.py
Brief:  Scene CRUD, asset upload, preview render and playback endpoints.
Author: Mistress-Lukutar
Date:   2026-09-30
Version: v0.5.2
"""

import mimetypes
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import FileResponse, Response

from luminaflowui.core.models import Resolution
from luminaflowui.dependencies import (
    DisplayDep,
    SceneRuntimeDep,
    ScenesDep,
)
from luminaflowui.exceptions import ValidationError
from luminaflowui.models.schemas import SaveSceneRequest, StatusResponse
from luminaflowui.scene.loader import load_scene_from_text
from luminaflowui.scene.runner import SceneRenderer
from luminaflowui.scene.schema import SceneDocument

router = APIRouter(prefix="/api/scenes", tags=["scenes"])

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
EXAMPLE_DIR: Path = PROJECT_ROOT / "examples" / "scenes" / "dashboard"


def _scene_response(scenes: ScenesDep, scene_id: str) -> dict[str, Any]:
    """Build the scene detail payload (meta, YAML, assets and components)."""
    meta = scenes.get_meta(scene_id)
    return {
        "scene": meta.model_dump(),
        "yaml": scenes.read_yaml(scene_id),
        "assets": scenes.list_assets(scene_id),
        "components": scenes.list_components(scene_id),
    }


@router.get("", response_model=StatusResponse)
async def list_scenes(scenes: ScenesDep) -> StatusResponse:
    """List all stored scenes."""
    items = [meta.model_dump() for meta in scenes.list_scenes()]
    return StatusResponse(data={"scenes": items})


@router.post("", response_model=StatusResponse)
async def create_scene(
    scenes: ScenesDep,
    name: str = Form(..., min_length=1, max_length=100),
    file: Annotated[UploadFile | None, Form()] = None,
) -> StatusResponse:
    """Create a scene, optionally uploading a ``.yaml``/``.yml`` file."""
    yaml_text: str | None = None
    if file is not None:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".yaml", ".yml"):
            raise ValidationError(f"Unsupported scene extension: {suffix or '(none)'}")
        yaml_text = (await file.read()).decode("utf-8")
    meta = scenes.create_scene(name, yaml_text)
    return StatusResponse(data=_scene_response(scenes, meta.id))


@router.post("/seed-example", response_model=StatusResponse)
async def seed_example(scenes: ScenesDep) -> StatusResponse:
    """Create a scene from the bundled dashboard example."""
    meta = scenes.seed_example(EXAMPLE_DIR)
    return StatusResponse(data=_scene_response(scenes, meta.id))


@router.post("/stop", response_model=StatusResponse)
async def stop_scene(
    display: DisplayDep, runtime: SceneRuntimeDep
) -> StatusResponse:
    """Stop the running scene on every device it drives."""
    await runtime.deactivate()
    return StatusResponse(data=display.status()["scene"])


@router.post("/preview")
async def preview_yaml(
    scenes: ScenesDep,
    display: DisplayDep,
    file: UploadFile,
    scene_id: Annotated[str | None, Form()] = None,
) -> Response:
    """Render one frame from uploaded YAML as JPEG, without sending it.

    When ``scene_id`` is given, relative asset, font and component paths
    are resolved against that stored scene's directory, so the editor can
    preview scenes together with their uploaded assets.
    """
    yaml_text = (await file.read()).decode("utf-8")
    base_dir = scenes._scene_dir(scene_id) if scene_id else scenes.scenes_dir
    document = load_scene_from_text(
        yaml_text, base_dir, fonts_dir=scenes.font_library_dir
    )
    payload = await _render_preview(document, display)
    return Response(content=payload, media_type="image/jpeg")


@router.get("/{scene_id}", response_model=StatusResponse)
async def get_scene(scene_id: str, scenes: ScenesDep) -> StatusResponse:
    """Return one scene's metadata, YAML source, assets and components."""
    return StatusResponse(data=_scene_response(scenes, scene_id))


@router.get("/{scene_id}/assets/{asset_name}")
async def get_asset(
    scene_id: str, asset_name: str, scenes: ScenesDep
) -> FileResponse:
    """Serve a stored asset file (image or font) to the client.

    The scene editor fetches images and fonts through this endpoint to
    draw the canvas preview in the browser.
    """
    path = scenes.read_asset_path(scene_id, asset_name)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.put("/{scene_id}", response_model=StatusResponse)
async def save_scene(
    scene_id: str,
    req: SaveSceneRequest,
    scenes: ScenesDep,
    runtime: SceneRuntimeDep,
) -> StatusResponse:
    """Validate and save the YAML source of a scene.

    When the saved scene is currently active, it is re-applied with the
    fresh document so editor changes show up without a manual re-apply.
    """
    meta = scenes.save_yaml(scene_id, req.yaml, name=req.name)
    if runtime.active_scene_id == scene_id:
        await runtime.activate(scene_id)
    return StatusResponse(data={"scene": meta.model_dump()})


@router.delete("/{scene_id}", response_model=StatusResponse)
async def delete_scene(scene_id: str, scenes: ScenesDep) -> StatusResponse:
    """Delete a scene with its assets."""
    scenes.delete_scene(scene_id)
    return StatusResponse()


@router.post("/{scene_id}/assets", response_model=StatusResponse)
async def upload_assets(
    scene_id: str, scenes: ScenesDep, files: list[UploadFile]
) -> StatusResponse:
    """Store uploaded asset files (images, fonts) for a scene."""
    payload = [(file.filename or "", file.file) for file in files if file.filename]
    if not payload:
        raise ValidationError("No asset files provided")
    stored = scenes.add_assets(scene_id, payload)
    return StatusResponse(data={"assets": stored})


@router.delete("/{scene_id}/assets/{asset_name}", response_model=StatusResponse)
async def delete_asset(
    scene_id: str, asset_name: str, scenes: ScenesDep
) -> StatusResponse:
    """Delete one stored asset file."""
    scenes.delete_asset(scene_id, asset_name)
    return StatusResponse(data={"assets": scenes.list_assets(scene_id)})


@router.post("/{scene_id}/apply", response_model=StatusResponse)
async def apply_scene(
    scene_id: str, scenes: ScenesDep, runtime: SceneRuntimeDep
) -> StatusResponse:
    """Activate a stored scene on every device its sections describe."""
    devices = await runtime.activate(scene_id)
    return StatusResponse(data={"devices": devices, "scene_id": scene_id})


@router.post("/{scene_id}/preview")
async def preview_scene(
    scene_id: str, scenes: ScenesDep, display: DisplayDep
) -> Response:
    """Render one frame of a stored scene as JPEG without sending it."""
    document = scenes.load_document(scene_id)
    payload = await _render_preview(document, display)
    return Response(content=payload, media_type="image/jpeg")


async def _render_preview(document: SceneDocument, display: DisplayDep) -> bytes:
    """Render a single preview frame off the event loop.

    Args:
        document: Validated scene document (root with device sections).
        display: Display service providing the panel resolution.

    Returns:
        Encoded JPEG bytes.

    Raises:
        ValidationError: If the scene has no screen section to render.
    """
    screen = document.screen
    if screen is None:
        raise ValidationError("Scene has no screen section to preview")
    width, height = display.panel_resolution()
    renderer = SceneRenderer(
        screen,
        Resolution(width=width, height=height),
        brightness=display.brightness,
        quality=display.quality,
        video_cache_dir=display.video_cache_dir,
    )
    return await anyio.to_thread.run_sync(renderer.render_frame)
