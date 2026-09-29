/**
 * Workspace geometry and Canvas2D drawing for the ARGB editor.
 * Pure functions over the layout + device definition library; the Vue
 * component supplies pixels. Device shapes come from their definition:
 * decor is drawn with its own paint, LED shape fills carry the effect
 * color of the matching LED index.
 */

import type { ArgbDevice, ArgbLayout, DecorShape, DeviceDefinition, LedShape } from './types'
import { WORKSPACE_HEIGHT, WORKSPACE_WIDTH } from './types'
import { defBounds, defCenter, shapeCenter, shapeExtent } from './deviceDef'
import type { WidgetBox } from '../canvas/geometry'

export interface Cell {
  /** Center in workspace coordinates. */
  x: number
  y: number
  /** Hit radius in workspace units. */
  r: number
  deviceId: string
  /** Pixel index within the device (LED list position). */
  index: number
}

export interface DeviceGeometry {
  cells: Cell[]
  /** Bounding box of the whole device incl. decor (world coordinates). */
  bbox: WidgetBox
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

/** World-space geometry of one device instance. */
export function deviceGeometry(
  device: ArgbDevice,
  def: DeviceDefinition | undefined,
): DeviceGeometry {
  const cells: Cell[] = []
  const s = device.scale
  if (def !== undefined) {
    const center = defCenter(def)
    def.leds.forEach((shape, index) => {
      const local = shapeCenter(shape)
      const p = rotate(
        device.x + (local.x - center.x) * s,
        device.y + (local.y - center.y) * s,
        device.x,
        device.y,
        device.rotation,
      )
      cells.push({
        x: p.x,
        y: p.y,
        r: shapeExtent(shape) * s + 2,
        deviceId: device.id,
        index,
      })
    })
  }

  // Bounding box: rotate the local design box around the device center.
  let bbox: WidgetBox = { x: device.x - 20, y: device.y - 20, w: 40, h: 40 }
  if (def !== undefined) {
    const b = def.size !== null
      ? { x: 0, y: 0, w: def.size[0], h: def.size[1] }
      : defBounds(def)
    const center = defCenter(def)
    const corners = [
      [b.x, b.y],
      [b.x + b.w, b.y],
      [b.x + b.w, b.y + b.h],
      [b.x, b.y + b.h],
    ].map(([lx, ly]) =>
      rotate(
        device.x + (lx - center.x) * s,
        device.y + (ly - center.y) * s,
        device.x,
        device.y,
        device.rotation,
      ),
    )
    const xs = corners.map((p) => p.x)
    const ys = corners.map((p) => p.y)
    bbox = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    }
  }

  let radius = 0
  for (const cell of cells) {
    radius = Math.max(radius, Math.hypot(cell.x - device.x, cell.y - device.y))
  }
  return { cells, bbox, cx: device.x, cy: device.y, radius: radius + 10 }
}

/** Build the cell map for the whole layout plus header buffer offsets. */
export function layoutGeometry(
  layout: ArgbLayout,
  defs: Map<string, DeviceDefinition>,
): {
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
      byDevice.set(id, deviceGeometry(device, defs.get(device.device)))
      offsets.set(id, offset)
      offset += defs.get(device.device)?.leds.length ?? 0
    }
  }
  for (const device of layout.devices) {
    if (!byDevice.has(device.id)) {
      byDevice.set(device.id, deviceGeometry(device, defs.get(device.device)))
    }
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

/** Tight axis-aligned bounding box of a device (kept for stage boxes). */
export function deviceBox(geo: DeviceGeometry): WidgetBox {
  return geo.bbox
}

/** Convert '#RRGGBB[AA]' hex to a CSS color (falls back to dim gray). */
function cssColor(hex: string | undefined): string {
  if (hex === undefined) return '#2b2b2b'
  return hex.startsWith('#') ? hex.slice(0, 7) : `#${hex.slice(0, 6)}`
}

// ---------------------------------------------------------------------------
// Shape painting (under the device transform, definition coordinates).
// ---------------------------------------------------------------------------

function traceShape(
  ctx: CanvasRenderingContext2D,
  shape: LedShape | DecorShape,
  inset = 0,
): void {
  ctx.beginPath()
  if (shape.type === 'rect') {
    const [x, y, w, h] = shape.rect
    if (inset !== 0) {
      ctx.roundRect(x + inset, y + inset, w - inset * 2, h - inset * 2, Math.max((shape.radius ?? 0) - inset, 0))
    } else {
      ctx.roundRect(x, y, w, h, shape.radius ?? 0)
    }
  } else if (shape.type === 'circle') {
    ctx.arc(shape.center[0], shape.center[1], Math.max(shape.radius - inset, 0.1), 0, Math.PI * 2)
  } else {
    ctx.moveTo(shape.points[0][0], shape.points[0][1])
    for (let i = 1; i < shape.points.length; i += 1) {
      ctx.lineTo(shape.points[i][0], shape.points[i][1])
    }
    if (shape.type !== 'polyline') ctx.closePath()
  }
}

function paintDecorShape(ctx: CanvasRenderingContext2D, shape: DecorShape): void {
  ctx.globalAlpha = shape.opacity
  traceShape(ctx, shape)
  if (shape.type !== 'polyline') {
    if (shape.fill) {
      ctx.fillStyle = shape.fill_color
      ctx.fill()
    }
    if (shape.stroke_width > 0) {
      const inset =
        shape.stroke_align === 'inside'
          ? shape.stroke_width / 2
          : shape.stroke_align === 'outside'
            ? -shape.stroke_width / 2
            : 0
      if (inset !== 0 && (shape.type === 'rect' || shape.type === 'circle')) {
        traceShape(ctx, shape, inset)
      } else {
        traceShape(ctx, shape)
      }
      ctx.strokeStyle = shape.stroke_color
      ctx.lineWidth = shape.stroke_width
      ctx.stroke()
    }
  } else if (shape.stroke_width > 0) {
    ctx.strokeStyle = shape.stroke_color
    ctx.lineWidth = shape.stroke_width
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.stroke()
  }
  ctx.globalAlpha = 1
}

function paintLedShape(
  ctx: CanvasRenderingContext2D,
  shape: LedShape,
  fill: string,
): void {
  traceShape(ctx, shape)
  ctx.fillStyle = fill
  ctx.fill()
  if (shape.stroke_color && (shape.stroke_width ?? 0) > 0) {
    ctx.strokeStyle = shape.stroke_color
    ctx.lineWidth = shape.stroke_width ?? 1
    ctx.stroke()
  }
}

/**
 * Draw one device under the current transform context: decor first, then
 * one shape per LED. `colorFor(index)` returns the LED fill or null for
 * the dim "unlit" state; `dim(index)` extra-fades masked-out pixels.
 */
function drawDeviceShapes(
  ctx: CanvasRenderingContext2D,
  device: ArgbDevice,
  def: DeviceDefinition,
  colorFor: (index: number) => string | null,
  dim: (index: number) => boolean,
): void {
  const s = device.scale
  const center = defCenter(def)
  ctx.save()
  ctx.translate(device.x, device.y)
  if (device.rotation !== 0) {
    ctx.rotate((device.rotation * Math.PI) / 180)
  }
  ctx.scale(s, s)
  ctx.translate(-center.x, -center.y)
  for (const shape of def.decor) paintDecorShape(ctx, shape)
  def.leds.forEach((shape, index) => {
    const color = colorFor(index)
    if (dim(index)) {
      ctx.globalAlpha = 0.22
      paintLedShape(ctx, shape, color ?? '#2b2b2b')
      ctx.globalAlpha = 1
      return
    }
    paintLedShape(ctx, shape, color ?? '#2b2b2b')
  })
  ctx.restore()
}

export interface DrawOptions {
  preview: Record<string, string>
  /** When painting, cells outside this layer's mask are dimmed. */
  maskCoverage: ((deviceId: string, index: number) => boolean) | null
}

/** Draw the full ARGB workspace: devices, live colors, labels, mask. */
export function drawWorkspace(
  ctx: CanvasRenderingContext2D,
  layout: ArgbLayout,
  defs: Map<string, DeviceDefinition>,
  options: DrawOptions,
): void {
  const { byDevice, offsets } = layoutGeometry(layout, defs)
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
    const def = defs.get(device.device)
    if (geo === undefined) continue

    if (def !== undefined) {
      const buffer = options.preview[device.header_id]
      const offset = offsets.get(device.id) ?? 0
      drawDeviceShapes(
        ctx,
        device,
        def,
        (index) => {
          if (buffer === undefined) return null
          const base = (offset + index) * 3
          return cssColor(`#${buffer.slice(base * 2, base * 2 + 6)}`)
        },
        (index) =>
          options.maskCoverage !== null &&
          !options.maskCoverage(device.id, index),
      )
    }

    ctx.fillStyle = 'rgba(255,255,255,0.45)'
    ctx.font = '10px system-ui, sans-serif'
    ctx.textAlign = 'center'
    const labelY =
      def === undefined ? device.y : geo.bbox.y + geo.bbox.h + 12
    ctx.fillText(
      def === undefined ? `${device.name} (missing ${device.device})` : device.name,
      device.x,
      labelY,
    )
  }
}

/** Identity helper removed: device id is captured in the dim closure. */

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
  defs: Map<string, DeviceDefinition>,
  preview: Record<string, string>,
  brightness: number,
  width: number,
  height: number,
): void {
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#0b0d0b'
  ctx.fillRect(0, 0, width, height)

  const { byDevice, offsets } = layoutGeometry(layout, defs)
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
    const def = defs.get(device.device)
    if (geo === undefined || def === undefined) continue
    const buffer = preview[device.header_id]
    const offset = offsets.get(device.id) ?? 0
    drawDeviceShapes(
      ctx,
      device,
      def,
      (index) =>
        buffer !== undefined
          ? shadedColor(buffer, (offset + index) * 3, mult, cache)
          : null,
      () => false,
    )
  }
  ctx.restore()
}
