# OledWebUI

Web interface for controlling ChiZhu Tech USB display panels (VID:PID `87AD:70DB`)
from a browser. Protocol and transport are ported from the original
[`oled`](../Oled) CLI project; the web layer is new.

## Features

- **Device** — connect/disconnect over raw USB bulk transfers, handshake,
  panel info (PM/SUB, resolution).
- **Image** — upload an image, tune rotation / brightness / fit / JPEG
  quality, live preview before and after sending.
- **Color** — fill the panel with a solid color, quick swatches.
- **Text** — multi-line text with size, colors, alignment, padding and
  optional custom TTF/OTF fonts (drop them into `data/fonts/`).
- **Video** — upload a video, stream it to the panel via ffmpeg at a chosen
  FPS, loop, stop anytime.
- **Keepalive** — the panel reverts to its built-in logo after ~2–3 seconds
  without frames; the server re-sends the last frame in the background.
- **Presets** — save the currently displayed content (image, color or text
  plus all render parameters) as a named preset and re-apply it later.
- **Live preview** — the UI mirrors the last frame sent to the panel,
  updated in real time over SSE.

Brightness is software-only (pixel LUT scaling, 0–200 %) — this panel has no
hardware backlight control. "Off" sends a black frame kept alive by the
keepalive loop; actual USB power cut is out of scope.

## Stack

- **Backend**: Python 3.11+, FastAPI (async) + Uvicorn, PyUSB, Pillow,
  pydantic-settings, structlog. src-layout package `oled_webui`.
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
| `OLED_DATA_DIR`       | `./data`        | Presets, uploads, fonts, last frame      |
| `OLED_KEEPALIVE_ENABLED` | `true`       | Keepalive auto-start on connect          |
| `OLED_KEEPALIVE_INTERVAL` | `1.5`       | Keepalive resend interval, seconds       |
| `OLED_AUTO_CONNECT`   | `true`          | Connect to USB device on startup         |

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
| `/api/device/keepalive` | POST | Toggle keepalive `{enabled, interval}` |
| `/api/frame/image` | POST | multipart `file` + render params |
| `/api/frame/color` | POST | multipart `color`, `brightness` |
| `/api/frame/text` | POST | JSON `TextRequest` |
| `/api/frame/off` `/on` `/test` | POST | Power / test pattern |
| `/api/frame/preview` | GET | Last frame as JPEG |
| `/api/frame/fonts` | GET | Custom fonts available |
| `/api/video` `/video/stop` | POST | Playback control |
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
  "params": {"rotation": 0, "brightness": 100, "fit": "contain", "quality": 95},
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

## Tests

32 pytest tests cover the wire header layout, resolution profile lookup,
the render pipeline (fit/rotation/brightness/text), preset storage and a
full API smoke suite with a fake USB device. The real hardware is not
required.
