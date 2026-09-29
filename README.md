# OledWebUI

Web interface for controlling ChiZhu Tech USB display panels (VID:PID `87AD:70DB`)
from a browser. Protocol and transport are ported from the original
[`oled`](../Oled) CLI project; the web layer is new.

## Features

- **Device** — connect/disconnect over raw USB bulk transfers, handshake,
  panel info (PM/SUB, resolution).
- **Image** — upload an image, tune rotation / fit, live preview before and
  after sending.
- **Color** — fill the panel with a solid color, quick swatches.
- **Text** — multi-line text with size, colors, alignment, padding and
  optional custom TTF/OTF fonts (drop them into `data/fonts/`).
- **Video** — upload a video, stream it to the panel via ffmpeg at a chosen
  FPS, loop, stop anytime.
- **Display settings** — one global dialog (⚙ in the status bar) for
  keepalive, brightness and JPEG quality plus an energy-saving option that
  blanks the panel when the Windows display powers off and restores the
  content when it turns back on. Settings persist across restarts and
  apply to every content type.
- **Scenes** — declarative YAML layouts: a static background collage plus
  live widgets (text, bar, ring, graph, image) driven by system metrics
  (CPU, RAM, disk, network, temps, clock; GPU via NVML when available).
  Reusable components, value-transition animations with named easing
  curves and sandboxed procedural expressions (`t`, `dt`, `v`). Scenes are
  stored under `data/scenes/<id>/` with their assets; the tab offers a
  YAML editor with validation, a hardware-free frame preview and a scene
  library. A bundled dashboard example can be added with one click.
- **Keepalive** — the panel reverts to its built-in logo after ~2–3 seconds
  without frames; the server re-sends the last frame in the background.
- **Presets** — save the currently displayed content (image, color or text
  plus all render parameters) as a named preset and re-apply it later.
- **Live preview** — the UI mirrors the last frame sent to the panel,
  updated in real time over SSE.

Brightness is software-only (gamma-correct pixel LUT, 0–200 %, global
setting) — this panel has no hardware backlight control. The percentage
targets physical luminance (50 % ≈ half maximum brightness) instead of
raw pixel values, so dark tones keep their separation at low settings
instead of collapsing into black. "Off" sends a black frame kept alive
by the keepalive loop; actual USB power cut is out of scope.

## Stack

- **Backend**: Python 3.11+, FastAPI (async) + Uvicorn, PyUSB, Pillow,
  psutil, PyYAML, pydantic-settings, structlog. src-layout package
  `oled_webui`.
- **Frontend**: Vue 3 + Vite + TypeScript, hand-written dark theme,
  SSE for real-time updates. Build output is served by FastAPI itself.
- **External tool**: `ffmpeg` on PATH (only needed for video playback).

## Quick start (Windows)

```bat
start.bat
```

This creates `.venv`, installs the package, builds the frontend (first run
only) and starts the server at http://127.0.0.1:8090.

### Manual

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
.venv/Scripts/python run.py
```

### Configuration

Environment variables (prefix `OLED_`, `.env` supported):

| Variable              | Default         | Description                              |
|-----------------------|-----------------|------------------------------------------|
| `OLED_HOST`           | `127.0.0.1`     | HTTP bind interface                      |
| `OLED_PORT`           | `8090`          | HTTP port                                |
| `OLED_DATA_DIR`       | `./data`        | Presets, scenes, uploads, fonts, last frame |
| `OLED_KEEPALIVE_ENABLED` | `true`       | Keepalive auto-start on connect          |
| `OLED_KEEPALIVE_INTERVAL` | `1.5`       | Keepalive resend interval, seconds       |
| `OLED_BRIGHTNESS`     | `100`           | Initial global brightness percent        |
| `OLED_JPEG_QUALITY`   | `95`            | Initial global JPEG quality              |
| `OLED_BLANK_ON_DISPLAY_OFF` | `false`   | Blank panel when the Windows display powers off |
| `OLED_AUTO_CONNECT`   | `true`          | Connect to USB device on startup         |

Env vars seed the defaults on first run; values changed in the settings
dialog are stored in `data/display_settings.json` and take precedence.

## USB driver

The panel exposes vendor-specific bulk endpoints and needs a WinUSB driver
on Windows (install once with [Zadig](https://zadig.akeo.ie/), selecting the
device and *WinUSB*). On Linux, install `libusb-1.0` and add a udev rule for
`87AD:70DB`.

## API overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/device/status` | GET | Full status snapshot |
| `/api/device/connect` `/disconnect` | POST | Connection control |
| `/api/device/settings` | GET/POST | Read / update display settings `{keepalive_enabled, keepalive_interval, brightness, quality, blank_on_display_off}` |
| `/api/frame/image` | POST | multipart `file` + render params |
| `/api/frame/color` | POST | multipart `color` |
| `/api/frame/text` | POST | JSON `TextRequest` |
| `/api/frame/off` `/on` `/test` | POST | Power / test pattern |
| `/api/frame/preview` | GET | Last frame as JPEG |
| `/api/frame/fonts` | GET | Custom fonts available |
| `/api/video` `/video/stop` | POST | Playback control |
| `/api/scenes` | GET/POST | Scene library (multipart create) |
| `/api/scenes/{id}` | GET/PUT/DELETE | Scene YAML source management |
| `/api/scenes/{id}/assets` | POST/DELETE | Scene asset files |
| `/api/scenes/{id}/apply` `/stop` | POST | Scene playback control |
| `/api/scenes/{id}/preview` `/preview` | POST | Render one frame as JPEG |
| `/api/presets` | GET | List presets |
| `/api/presets/save-current` | POST | Snapshot last content |
| `/api/presets/{id}` `/apply` | POST/DELETE | Manage presets |
| `/events` | GET | SSE stream |
| `/health` | GET | Liveness probe |

## Preset format

One JSON file per preset in `data/presets/`, binary assets stored alongside:

```json
{
  "id": "9f2c41a8b0d3",
  "name": "Living room",
  "type": "image",
  "params": {"rotation": 0, "fit": "contain"},
  "payload": {"file": "9f2c41a8b0d3.png"},
  "created_at": 1769500000.0,
  "has_asset": true
}
```

## Development

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
cd frontend && npm run dev   # Vite dev server with /api proxy
```

After code changes run `python scripts/bump-version.py` to bump file headers.

## ARGB lighting (Devices → ARGB tab)

The second device tab drives ARGB strips and fans connected to the
motherboard's 5V 3-pin headers through [OpenRGB](https://openrgb.org):

1. Install and start OpenRGB (it detects the board's RGB controller).
   The SDK server must listen on `127.0.0.1:6742` (default when the app
   runs; enable *SDK* in its settings if you changed it).
2. Close Gigabyte Control Center / RGB Fusion — they fight over the
   controller.
3. In the WebUI open the **ARGB** tab, press **Connect**, then add your
   strips/fans, arrange them on the workspace to mirror the case, set
   LED counts and the header each device hangs on (chain order matters),
   stack effect layers (fill, gradient, rainbow, breathing, comet,
   scanner, meter) with per-layer opacity and pixel masks, and press
   **Apply**.

The workspace preview is rendered by the same engine that feeds the
LEDs, so it is exactly what the hardware shows. Enable *Run
automatically on server start* in the inspector (nothing selected) to
restore the lighting on boot. Host/port can be overridden with
`OLED_OPENRGB_HOST` / `OLED_OPENRGB_PORT`. The layout persists in
`data/argb/layout.json`.

## Tests

186 pytest tests cover the wire header layout, resolution profile lookup,
the render pipeline (fit/rotation/brightness/text), preset storage and a
full API smoke suite with a fake USB device. The real hardware is not
required. Scene engine tests cover the expression sandbox, easing curves,
widget renderers, component expansion, the rendering state machine
(dirty-detection, keepalive re-yield) and the scenes API. ARGB tests
cover the effect engine math (masks, alpha blending, chain mapping), the
layout schema validation and the API with a fake OpenRGB transport.
