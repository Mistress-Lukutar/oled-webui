# LuminaFlowUI

A browser dashboard for a ChiZhu Tech USB display
panel (From AIO system, VID:PID `87AD:70DB`) and the motherboard's ARGB lighting, driven
together from declarative scene files.

One YAML scene describes the whole computer's appearance — the panel
shows a live dashboard of system metrics, and the fans and strips run a
layered lighting layout. Switching a scene switches everything at once.

## Highlights

- **Unified scenes** — one YAML file per scene, one section per device:
  `screen:` (collage background + widgets: text, bar, ring, graph,
  image, shape, video) and `argb:` (lighting layout). Widgets are fed by
  live system metrics (CPU, RAM, disk, network, temps, clock, GPU via
  NVML), support value-transition animations with named easing curves
  and sandboxed procedural expressions. Reusable components keep
  recurring pieces in one place.
- **Visual editors** — a unified scene editor with a tab per device
  section plus a raw-YAML view: validation, hardware-free frame
  preview, and an ARGB designer where strips and fans are laid out on a
  canvas to mirror the case and stacked into effect layers (fill,
  gradient, rainbow, breathing, comet, scanner, meter).
- **Masonry dashboard** — draggable, auto-balanced panels (preview,
  quick settings, scenes, ARGB); the layout persists across restarts.
- **Energy saving** — blanks the panel (and dims the lighting) when the
  Windows display powers off, restores everything on wake.
- **Live preview** — the UI mirrors the last frame sent to the panel in
  real time over SSE.

Brightness is software-only (gamma-correct pixel LUT, 0–200 %) — the
panel has no hardware control. The percentage targets physical
luminance rather than raw pixel values, so dark tones keep their
separation at low settings. "Off" sends a black frame kept alive by the
keepalive loop; an actual USB power cut is out of scope.

## Requirements

- Windows (developed and tested there) with Python 3.11+ and Node.js
- [OpenRGB](https://openrgb.org) for ARGB lighting (optional)
- `ffmpeg` on PATH for `video:` widgets (optional)

## Quick start

```bat
setup.bat
start.bat
```

`setup.bat` is a one-time installer for a fresh Windows machine (run it
from an elevated terminal so scheduled tasks can be registered). It:

- installs Python 3.11+, Node.js LTS, ffmpeg (`Gyan.FFmpeg`), PawnIO and
  OpenRGB when missing — via winget or a direct download into `tools\`;
- creates `.venv`, installs the backend package and builds the frontend
  into `static\dist\`;
- writes `.env` and wires `LUMINA_OPENRGB_TASK`/`LUMINA_OPENRGB_EXE`;
- registers two Task Scheduler entries: **LuminaFlowUI** (logon task
  running `scripts\supervisor.bat`, which restarts the server if it
  dies) and **LuminaFlowUI OpenRGB** (elevated, on-demand SDK server —
  the elevation is what lets OpenRGB use PawnIO for SMBus access).

Steps that cannot be automated (missing winget, no internet, declined
UAC prompt, ...) are printed at the end as manual instructions with
download URLs — complete them and re-run `setup.bat`. It is safe to
re-run: finished steps are skipped. Switches: `-SkipTasks` (touch no
scheduled tasks), `-SkipDownloads` (check and report only).

`start.bat` then starts the server at http://127.0.0.1:8090; it is also
what the logon task runs, so installing nothing is needed for daily use.

Manual setup:

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
.venv/Scripts/python run.py
```

On Linux, install `libusb-1.0` and add a udev rule for `87AD:70DB`.

### Configuration

Environment variables (prefix `LUMINA_`, `.env` supported):

| Variable                       | Default     | Description                                                 |
|--------------------------------|-------------|-------------------------------------------------------------|
| `LUMINA_HOST`                  | `127.0.0.1` | HTTP bind interface                                         |
| `LUMINA_PORT`                  | `8090`      | HTTP port                                                   |
| `LUMINA_DATA_DIR`              | `./data`    | Scenes, fonts, ARGB state, UI layout, last frame            |
| `LUMINA_KEEPALIVE_ENABLED`     | `true`      | Keepalive auto-start on connect                             |
| `LUMINA_KEEPALIVE_INTERVAL`    | `1.5`       | Keepalive resend interval, seconds                          |
| `LUMINA_BRIGHTNESS`            | `100`       | Initial global brightness percent (0–200)                   |
| `LUMINA_JPEG_QUALITY`          | `95`        | Initial global JPEG quality                                 |
| `LUMINA_BLANK_ON_DISPLAY_OFF`  | `false`     | Blank panel + lighting when the Windows display powers off  |
| `LUMINA_PREVIEW_THROTTLE`      | `0.2`       | Min seconds between video preview SSE events                |
| `LUMINA_AUTO_CONNECT`          | `true`      | Connect to USB device on startup                            |
| `LUMINA_OPENRGB_HOST`          | `127.0.0.1` | OpenRGB SDK server host                                     |
| `LUMINA_OPENRGB_PORT`          | `6742`      | OpenRGB SDK server port                                     |
| `LUMINA_OPENRGB_EXE`           | *(unset)*   | Path to `OpenRGB.exe`; the server spawns and supervises it itself |
| `LUMINA_OPENRGB_TASK`          | *(unset)*   | Scheduled task running OpenRGB elevated; started via `schtasks` when the SDK port is not served |
| `LUMINA_OPENRGB_START_TIMEOUT` | `45`        | Seconds to wait for the spawned OpenRGB SDK port            |

Env vars seed the defaults on first run; values changed in the settings
dialog are stored in `data/display_settings.json` and take precedence.

### ARGB lighting

ARGB strips and fans on the motherboard's 5V 3-pin headers are driven
through OpenRGB; the lighting state lives in the scene's `argb:`
section, so scenes switch the panel and the LEDs together.

1. Install OpenRGB and make sure its SDK server listens on
   `127.0.0.1:6742` (enable *SDK* in its settings if needed). With
   `LUMINA_OPENRGB_EXE` (or `LUMINA_OPENRGB_TASK` for an elevated
   scheduled task) the WebUI server spawns, restarts and stops OpenRGB
   itself, so you don't have to launch it manually.
2. Close Gigabyte Control Center / RGB Fusion — they fight over the
   controller.
3. Open the ARGB panel, press **Connect**, then **Designer**: add
   strips/fans, arrange them to mirror the case, set LED counts and the
   header each device hangs on (chain order matters), stack effect
   layers with per-layer opacity and pixel masks, then **Save** +
   **Apply**.

The workspace preview is rendered by the same engine that feeds the
LEDs, so it is exactly what the hardware shows. Header zone sizes are
pushed into OpenRGB on connect (ITE-style zones report 0 LEDs until
resized). Device shapes are templates in the definition library
`data/argb/devices/*.yaml`, shared by scenes.

## Scene file format

One YAML file per scene in `data/scenes/<id>/scene.yaml`, one top-level
section per device:

```yaml
screen:
  background: {color: "#000000"}
  widgets:
    - {type: text, rect: [...], text: "{value}%", source: {type: cpu}}
    - {type: bar, rect: [...], source: {type: ram}}
argb:
  headers: {h1: 300}
  devices:
    - {ref: case-strips, ...}
```

Assets (images, fonts) and reusable components live next to the scene
file; widgets reference them by relative path. The editor round-trips
this file through a YAML parser and grafts comments back onto the raw
source, so hand-written comments survive edits. Applying a scene starts
every section it describes and stops the devices it does not; the last
active scene (including its ARGB state) is restored after a restart. A
bundled dashboard example can be added with one click.

## API overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/device/status` | GET | Full status snapshot |
| `/api/device/connect` `/disconnect` `/reconnect` | POST | Connection control |
| `/api/device/info` | GET | Handshake / panel info |
| `/api/device/settings` | GET/POST | Display settings `{keepalive_enabled, keepalive_interval, brightness, quality, blank_on_display_off}` |
| `/api/frame/preview` | GET | Last frame as JPEG |
| `/api/frame/fonts` | GET/POST | Shared font library: list / upload TTF+OTF |
| `/api/frame/fonts/{name}` | GET/DELETE | Serve / remove one font file |
| `/api/scenes` | GET/POST | Scene library (multipart create with optional YAML) |
| `/api/scenes/seed-example` | POST | Create the bundled dashboard example |
| `/api/scenes/stop` | POST | Stop the running scene on all devices |
| `/api/scenes/preview` | POST | Render uploaded YAML to JPEG without saving |
| `/api/scenes/{id}` | GET/PUT/DELETE | Scene detail (meta, YAML, assets, components) / validated save / delete |
| `/api/scenes/{id}/assets` | POST | Upload scene asset files |
| `/api/scenes/{id}/assets/{name}` | GET/DELETE | Serve / remove an asset file |
| `/api/scenes/{id}/apply` | POST | Activate the scene (all sections it describes) |
| `/api/scenes/{id}/preview` | POST | Render one stored scene frame as JPEG |
| `/api/argb/status` | GET | OpenRGB connection status |
| `/api/argb/connect` `/disconnect` | POST | OpenRGB connection control |
| `/api/argb/settings` | GET/PUT | ARGB quick settings (brightness, power) |
| `/api/argb/active` | GET | Layout applied from the active scene |
| `/api/argb/devices` | GET/POST | Device definition library: list / create |
| `/api/argb/devices/{id}` | GET/PUT/DELETE | One device definition |
| `/api/argb/render_preview` | POST | Hardware-free layout frame |
| `/api/system/devices` | GET | Device registry backing the dashboard panels |
| `/api/ui/panels` | GET/PUT/DELETE | Dashboard panel layout: load / save / reset |
| `/events` | GET | SSE stream (`connection`, `frame_updated`, `display_settings`, `scene`, `argb`, `error`) |
| `/health` | GET | Liveness probe (independent of device state) |

## Development

```bash
ruff format src tests
ruff check src tests
mypy src
pytest
cd frontend && npm run dev   # Vite dev server with /api proxy
```

The backend is Python 3.11+ / FastAPI + Uvicorn in a src-layout package
`luminaflowui`; the frontend is Vue 3 + Vite + TypeScript (composables
only, no router/store frameworks) with the build output served by
FastAPI itself. After code changes run
`python scripts/bump-version.py` to bump file headers. See
[AGENTS.md](AGENTS.md) for the architecture map and agent-oriented
conventions.

210 pytest tests run hardware-free (fake USB device, fake OpenRGB
transport) and cover the wire protocol, the render pipeline, the scene
engine (expressions, easing, widgets, components, the rendering state
machine) and the ARGB effect engine (masks, alpha blending, chain
mapping).

## License

MIT
