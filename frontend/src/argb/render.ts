/**
 * Workspace geometry and Canvas2D drawing for the ARGB editor.
 * Pure functions over the layout; the Vue component supplies pixels.
 */

import type { ArgbDevice, ArgbLayout } from './types'
import { deviceTotalLeds, WORKSPACE_HEIGHT, WORKSPACE_WIDTH } from './types'
import type { WidgetBox } from '../canvas/geometry'

/** LED cell pitch/size in workspace units at scale 1. */
const PITCH = 16
const CELL = 11
const DOT = 5.5

export interface Cell {
  /** Center in workspace coordinates. */
  x: number
  y: number
  /** Hit radius in workspace units. */
  r: number
  deviceId: string
  /** Pixel index within the device. */
  index: number
  shape: 'rect' | 'dot'
}

export interface DeviceGeometry {
  cells: Cell[]
  cx: number
  cy: number
  radius: number
}

function rotate(x: number, y: number, cx: number, cy: number, deg: number): {
  x: number
  y: number
} {
  if (deg === 0) return { x, y }
  const rad = (deg * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const dx = x - cx
  const dy = y - cy
  return { x: cx + dx * cos - dy * sin, y: cy + dx * sin + dy * cos }
}

/** Compute LED cell centers for one device (local pixel order preserved). */
export function deviceGeometry(device: ArgbDevice): DeviceGeometry {
  const cells: Cell[] = []
  const s = device.scale
  const push = (
    x: number,
    y: number,
    index: number,
    shape: Cell['shape'],
    r: number,
  ): void => {
    const p = rotate(x, y, device.x, device.y, device.rotation)
    cells.push({ x: p.x, y: p.y, r, deviceId: device.id, index, shape })
  }

  if (device.type === 'strip') {
    const n = device.leds
    const start = device.x - ((n - 1) * PITCH * s) / 2
    for (let i = 0; i < n; i += 1) {
      push(start + i * PITCH * s, device.y, i, 'rect', (CELL / 2) * s + 2)
    }
  } else if (device.type === 'ring') {
    const n = device.leds
    const radius = clampRingRadius(n, s)
    for (let i = 0; i < n; i += 1) {
      const angle = (device.rotation * Math.PI) / 180 + (i / n) * Math.PI * 2
      push(
        device.x + Math.cos(angle) * radius,
        device.y + Math.sin(angle) * radius,
        i,
        'dot',
        DOT * s + 3,
      )
    }
  } else {
    const n = device.leds
    const side = device.leds_side
    const radius = clampRingRadius(n, s)
    for (let i = 0; i < n; i += 1) {
      const angle = (device.rotation * Math.PI) / 180 + (i / n) * Math.PI * 2
      push(
        device.x + Math.cos(angle) * radius,
        device.y + Math.sin(angle) * radius,
        i,
        'dot',
        DOT * s + 3,
      )
    }
    const stripeX = radius + 16 * s
    for (const sign of [-1, 1] as const) {
      const x = device.x + sign * stripeX
      const start = device.y - ((side - 1) * PITCH * s) / 2
      for (let i = 0; i < side; i += 1) {
        push(x, start + i * PITCH * s, n + (sign === -1 ? i : side + i), 'rect', (CELL / 2) * s + 2)
      }
    }
  }

  let radius = 0
  for (const cell of cells) {
    radius = Math.max(radius, Math.hypot(cell.x - device.x, cell.y - device.y))
  }
  return { cells, cx: device.x, cy: device.y, radius: radius + 10 }
}

function clampRingRadius(leds: number, scale: number): number {
  const natural = (leds * PITCH) / (2 * Math.PI)
  return Math.min(Math.max(natural, 26), 84) * scale
}

/** Build the cell map for the whole layout plus header buffer offsets. */
export function layoutGeometry(layout: ArgbLayout): {
  byDevice: Map<string, DeviceGeometry>
  offsets: Map<string, number>
} {
  const byDevice = new Map<string, DeviceGeometry>()
  const offsets = new Map<string, number>()
  for (const header of layout.headers) {
    let offset = 0
    for (const id of header.devices) {
      const device = layout.devices.find((item) => item.id === id)
      if (device === undefined) continue
      byDevice.set(id, deviceGeometry(device))
      offsets.set(id, offset)
      offset += deviceTotalLeds(device)
    }
  }
  for (const device of layout.devices) {
    if (!byDevice.has(device.id)) byDevice.set(device.id, deviceGeometry(device))
  }
  return { byDevice, offsets }
}

/** Nearest cell to a workspace point, within its hit radius. */
export function hitCell(
  cells: Cell[],
  x: number,
  y: number,
  tolerance = 6,
): Cell | null {
  let best: Cell | null = null
  let bestDist = Infinity
  for (const cell of cells) {
    const dist = Math.hypot(cell.x - x, cell.y - y)
    const limit = cell.r + tolerance
    if (dist <= limit && dist < bestDist) {
      best = cell
      bestDist = dist
    }
  }
  return best
}

/** Tight axis-aligned bounding box of a device's LED cells. */
export function deviceBox(geo: DeviceGeometry): WidgetBox {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const cell of geo.cells) {
    minX = Math.min(minX, cell.x - cell.r)
    minY = Math.min(minY, cell.y - cell.r)
    maxX = Math.max(maxX, cell.x + cell.r)
    maxY = Math.max(maxY, cell.y + cell.r)
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

/** Convert '#RRGGBB[AA]' hex to a CSS color (falls back to dim gray). */
function cssColor(hex: string | undefined): string {
  if (hex === undefined) return '#2b2b2b'
  return hex.startsWith('#') ? hex.slice(0, 7) : `#${hex.slice(0, 6)}`
}

export interface DrawOptions {
  preview: Record<string, string>
  /** When painting, cells outside this layer's mask are dimmed. */
  maskCoverage: ((deviceId: string, index: number) => boolean) | null
}

/** Draw one LED cell in workspace space (transform applied by caller). */
function drawCell(ctx: CanvasRenderingContext2D, cell: Cell, fill: string): void {
  ctx.fillStyle = fill
  if (cell.shape === 'rect') {
    const half = CELL / 2
    ctx.beginPath()
    ctx.roundRect(cell.x - half, cell.y - half, CELL, CELL, 3)
    ctx.fill()
  } else {
    ctx.beginPath()
    ctx.arc(cell.x, cell.y, DOT, 0, Math.PI * 2)
    ctx.fill()
  }
}

/** Draw the full ARGB workspace: devices, live colors, selection, mask. */
export function drawWorkspace(
  ctx: CanvasRenderingContext2D,
  layout: ArgbLayout,
  options: DrawOptions,
): void {
  const { byDevice, offsets } = layoutGeometry(layout)
  ctx.clearRect(0, 0, WORKSPACE_WIDTH, WORKSPACE_HEIGHT)
  ctx.fillStyle = '#101210'
  ctx.fillRect(0, 0, WORKSPACE_WIDTH, WORKSPACE_HEIGHT)

  // Subtle grid to anchor the "physical layout" feel.
  ctx.strokeStyle = 'rgba(255,255,255,0.04)'
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let gx = 0; gx <= WORKSPACE_WIDTH; gx += 40) {
    ctx.moveTo(gx, 0)
    ctx.lineTo(gx, WORKSPACE_HEIGHT)
  }
  for (let gy = 0; gy <= WORKSPACE_HEIGHT; gy += 40) {
    ctx.moveTo(0, gy)
    ctx.lineTo(WORKSPACE_WIDTH, gy)
  }
  ctx.stroke()

  for (const device of layout.devices) {
    const geo = byDevice.get(device.id)
    if (geo === undefined) continue
    const buffer = options.preview[device.header_id]
    const offset = offsets.get(device.id) ?? 0

    if (device.type !== 'strip') {
      // Faint guide circle behind ring fans.
      ctx.strokeStyle = 'rgba(255,255,255,0.07)'
      ctx.beginPath()
      const ringRadius = clampRingRadius(device.leds, device.scale)
      ctx.arc(device.x, device.y, ringRadius, 0, Math.PI * 2)
      ctx.stroke()
    }

    for (const cell of geo.cells) {
      let fill = '#2b2b2b'
      if (buffer !== undefined) {
        const base = (offset + cell.index) * 3
        const hex = buffer.slice(base * 2, base * 2 + 6)
        fill = cssColor(`#${hex}`)
      }
      if (options.maskCoverage !== null) {
        const covered = options.maskCoverage(cell.deviceId, cell.index)
        if (!covered) {
          ctx.globalAlpha = 0.22
          drawCell(ctx, cell, fill)
          ctx.globalAlpha = 1
          continue
        }
      }
      drawCell(ctx, cell, fill)
    }

    ctx.fillStyle = 'rgba(255,255,255,0.45)'
    ctx.font = '10px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(device.name, device.x, device.y + (device.type === 'strip' ? 26 : clampRingRadius(device.leds, device.scale) + 26))
  }
}

/**
 * Server preview buffers carry raw effect colors; the engine applies the
 * brightness LUT only when dispatching to hardware. Mirror that exact
 * transform here (frame_builder.brightness_scale: gamma 2.2, round to
 * nearest level) so the tab preview shows what the LEDs will show.
 */
const PREVIEW_GAMMA = 2.2

function shadedColor(
  buffer: string,
  base: number,
  mult: number,
  cache: Map<string, string>,
): string {
  const hex = buffer.slice(base * 2, base * 2 + 6)
  if (hex.length < 6) return '#1c1f1c'
  const cached = cache.get(hex)
  if (cached !== undefined) return cached
  const channel = (slice: string): number =>
    Math.min(255, Math.round(parseInt(slice, 16) * mult))
  const out = `rgb(${channel(hex.slice(0, 2))},${channel(hex.slice(2, 4))},${channel(hex.slice(4, 6))})`
  cache.set(hex, out)
  return out
}

/**
 * Draw a read-only output preview into a canvas of width x height: the
 * workspace fit and centered, devices with brightness-scaled live colors,
 * no editing chrome (grid, labels, selection).
 */
export function drawPreview(
  ctx: CanvasRenderingContext2D,
  layout: ArgbLayout,
  preview: Record<string, string>,
  brightness: number,
  width: number,
  height: number,
): void {
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0b0d0b'
  ctx.fillRect(0, 0, width, height)

  const { byDevice, offsets } = layoutGeometry(layout)
  const scale = Math.min(width / WORKSPACE_WIDTH, height / WORKSPACE_HEIGHT)
  ctx.save()
  ctx.translate(
    (width - WORKSPACE_WIDTH * scale) / 2,
    (height - WORKSPACE_HEIGHT * scale) / 2,
  )
  ctx.scale(scale, scale)

  const mult = (Math.max(0, brightness) / 100) ** (1 / PREVIEW_GAMMA)
  const cache = new Map<string, string>()

  for (const device of layout.devices) {
    const geo = byDevice.get(device.id)
    if (geo === undefined) continue
    const buffer = preview[device.header_id]
    const offset = offsets.get(device.id) ?? 0
    for (const cell of geo.cells) {
      const fill =
        buffer !== undefined
          ? shadedColor(buffer, (offset + cell.index) * 3, mult, cache)
          : '#1c1f1c'
      drawCell(ctx, cell, fill)
    }
  }
  ctx.restore()
}
