"""
File:   scenes.py
Brief:  Scene CRUD, asset upload, preview render and playback endpoints.
Author: Mistress-Lukutar
Date:   2026-09-27
Version: v0.2.0
"""

import mimetypes
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import FileResponse, Response

from oled_webui.core.models import Resolution
from oled_webui.dependencies import (
    ConnectedDisplayDep,
    DisplayDep,
    ScenesDep,
)
from oled_webui.exceptions import ValidationError
from oled_webui.models.schemas import SaveSceneRequest, StatusResponse
from oled_webui.scene.loader import load_scene_from_text
from oled_webui.scene.runner import SceneRenderer

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
async def stop_scene(display: ConnectedDisplayDep) -> StatusResponse:
    """Stop the running scene."""
    await display.stop_scene()
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
    document = load_scene_from_text(yaml_text, base_dir)
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
    scene_id: str, req: SaveSceneRequest, scenes: ScenesDep
) -> StatusResponse:
    """Validate and save the YAML source of a scene."""
    meta = scenes.save_yaml(scene_id, req.yaml, name=req.name)
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
    scene_id: str, scenes: ScenesDep, display: ConnectedDisplayDep
) -> StatusResponse:
    """Start rendering a stored scene on the display."""
    meta = scenes.get_meta(scene_id)
    document = scenes.load_document(scene_id)
    state = await display.start_scene(document, scene_id, meta.name)
    return StatusResponse(data=state)


@router.post("/{scene_id}/preview")
async def preview_scene(
    scene_id: str, scenes: ScenesDep, display: DisplayDep
) -> Response:
    """Render one frame of a stored scene as JPEG without sending it."""
    document = scenes.load_document(scene_id)
    payload = await _render_preview(document, display)
    return Response(content=payload, media_type="image/jpeg")


async def _render_preview(document: Any, display: DisplayDep) -> bytes:
    """Render a single preview frame off the event loop.

    Args:
        document: Validated scene document.
        display: Display service providing the panel resolution.

    Returns:
        Encoded JPEG bytes.
    """
    width, height = display.panel_resolution()
    renderer = SceneRenderer(document, Resolution(width=width, height=height))
    return await anyio.to_thread.run_sync(renderer.render_frame)
