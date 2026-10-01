# AGENTS.md

Guide for coding agents working on LuminaFlowUI — a web UI that drives a
ChiZhu Tech USB display panel (`87AD:70DB`) and motherboard ARGB lighting
(via OpenRGB) from scenes. The project was renamed from **OledWebUI** to
**LuminaFlowUI** (2026-10-01): the package, env prefix and docs use the new
name, but the Task Scheduler task, supervisor task and the repo/directory
keep the old `oled-webui` / `OledWebUI` names.

## Commands

```bash
# `python` is NOT on Git Bash PATH on this machine — always use the venv:
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff format src tests && ./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m mypy src
cd frontend && npm run build        # vue-tsc --noEmit && vite build → static/dist/
./.venv/Scripts/python.exe scripts/bump-version.py   # after code changes: bumps File-header blocks
```

The server runs at http://127.0.0.1:8090 (port 8080 is taken by another
service on this machine). A rebuilt `static/dist/` is served without a
backend restart; backend changes require restarting the server process
(it is supervised: `taskkill` the uvicorn/python process and let the
supervisor task restart it — do not create a second supervisor).

## Backend layout (`src/luminaflowui/`)

- `main.py` — app factory + lifespan. Wires `EventBus` topics
  (`connection`, `frame_updated`, `display_settings`, `scene`, `argb`,
  `error`) 1:1 to SSE, creates services, optionally auto-connects and
  restores the last content (`data/last_content.json`), starts the
  Windows `DisplayPowerWatcher` (GUID_CONSOLE_DISPLAY_STATE only; the
  user is on RDP, so session events must not wake the panel).
- `config.py` — `LUMINA_*` env settings (pydantic-settings, `.env`).
- `routers/` — thin HTTP layer: `device`, `frame` (preview + font
  library), `scenes`, `argb`, `system` (device registry for the
  dashboard), `ui` (panel layout persistence).
- `services/` — stateful singletons: `display_service` (USB panel
  lifecycle, keepalive, brightness LUT), `scene_runtime` (drives BOTH
  devices from one scene document; a missing section stops that device),
  `scene_service` (storage), `sse_manager`, `display_settings`,
  `display_power_watcher`, `content_state` (last-content snapshot),
  `ui_layout`, `video_extract` (ffmpeg → JPEG cache in
  `data/cache/video/`).
- `scene/` — scene schema, expression sandbox, providers (metrics),
  widget renderers (Pillow), runner state machine, loader (components).
- `argb/` — ARGB schema, effect engine (fill/gradient/rainbow/breathing/
  comet/scanner/meter layers with masks + alpha), device definitions,
  service. `infrastructure/` — `usb_transport`, `openrgb_transport`,
  `openrgb_process` (app owns the OpenRGB lifecycle when
  `LUMINA_OPENRGB_EXE`/`LUMINA_OPENRGB_TASK` is set).
- There is **no** direct content API anymore (image/color/text/video/
  presets endpoints were removed): everything renders through scenes.

## Frontend layout (`frontend/src/`)

- `canvas/` + `components/canvas/CanvasStage.vue` — shared interactive
  canvas kit (geometry, viewport, shortcuts, stage, overlay) used by
  both the scene editor and the ARGB designer via stage adapters.
- `scene-editor/` + `components/scene-editor/` — unified per-device
  scene editor modal: registry-driven sections (`sectionSpecs.ts` /
  `sectionViews.ts`), raw-YAML truth with CST comment grafting
  (`yamlSync.ts`), browser-side preview rendering.
- `argb/` — ARGB designer store, device definitions, client-side render.
- `components/panels/` + `panels/registry.ts` + `MasonryLayout.vue` —
  the dashboard: masonry tiles, auto-height balanced by measured
  heights, layout persisted via `/api/ui/panels`.
- State lives in composables (`composables/`, `argb/store.ts`); no
  vue-router / pinia. Dark theme is a hand-written `style.css`
  (`color-scheme: dark` + generic input selectors).

## Conventions

- Every file starts a header block: `File:` / `Brief:` / `Author:` /
  `Date:` / `Version:`. Run `scripts/bump-version.py` after code changes.
- English docstrings/comments in code; strict mypy (`pydantic` plugin);
  ruff line-length 88.
- `data/` is user content and gitignored: `scenes/<id>/`, `fonts/`,
  `argb/devices/*.yaml` (user's real device definitions — do not commit
  or overwrite without request), `display_settings.json`,
  `last_content.json`, `ui/panels.json`, `cache/video/`.
- Breaking schema/YAML changes are welcome — the user has no real scenes
  besides tests; migrate `examples/scenes/` and `data/scenes/` instead
  of adding compat shims.
- Video widget pipeline: frames must be exact panel WxH; rotation is
  applied before fit; ffmpeg must be reachable on PATH (WinGet Links
  dir on this machine) and the filter chain ends with
  `format=yuvj420p`.

## Testing

Tests run hardware-free: fake USB device and fake OpenRGB transport
(`tests/api`, `tests/unit`). Known flaky, do not chase on first failure:
`test_scene_renderer_yields_on_change` (fails ~20 % of runs,
psutil-dependent) and a rare Win32 access violation in
`DisplayPowerWatcher` during `tests/api` (~1/3 of runs) — rerun before
investigating.
