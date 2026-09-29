/**
 * Device definition helpers: local-space geometry, shape generators for the
 * designer, and static thumbnails for the device library.
 * Pure functions over a DeviceDefinition; no store access.
 */

import type {
  DecorShape,
  DeviceDefinition,
  LedShape,
} from './types'

export interface Bounds {
  x: number
  y: number
  w: number
  h: number
}

/** Center point of any shape in definition coordinates. */
export function shapeCenter(shape: LedShape | DecorShape): {
  x: number
  y: number
} {
  if (shape.type === 'circle') {
    return { x: shape.center[0], y: shape.center[1] }
  }
  if (shape.type === 'rect') {
    return { x: shape.rect[0] + shape.rect[2] / 2, y: shape.rect[1] + shape.rect[3] / 2 }
  }
  let sx = 0
  let sy = 0
  for (const [px, py] of shape.points) {
    sx += px
    sy += py
  }
  return { x: sx / shape.points.length, y: sy / shape.points.length }
}

/** Max distance from the shape center to its outline (hit radius). */
export function shapeExtent(shape: LedShape | DecorShape): number {
  if (shape.type === 'circle') return shape.radius
  if (shape.type === 'rect') {
    return Math.hypot(shape.rect[2], shape.rect[3]) / 2
  }
  const center = shapeCenter(shape)
  let max = 0
  for (const [px, py] of shape.points) {
    max = Math.max(max, Math.hypot(px - center.x, py - center.y))
  }
  return Math.max(max, 1)
}

/** Tight bounding box over every LED and decor shape. */
export function defBounds(def: DeviceDefinition): Bounds {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  const grow = (x0: number, y0: number, x1: number, y1: number): void => {
    minX = Math.min(minX, x0, x1)
    minY = Math.min(minY, y0, y1)
    maxX = Math.max(maxX, x0, x1)
    maxY = Math.max(maxY, y0, y1)
  }
  for (const shape of [...def.leds, ...def.decor]) {
    if (shape.type === 'circle') {
      grow(
        shape.center[0] - shape.radius,
        shape.center[1] - shape.radius,
        shape.center[0] + shape.radius,
        shape.center[1] + shape.radius,
      )
    } else if (shape.type === 'rect') {
      grow(shape.rect[0], shape.rect[1], shape.rect[0] + shape.rect[2], shape.rect[1] + shape.rect[3])
    } else {
      for (const [px, py] of shape.points) grow(px, py, px, py)
    }
  }
  if (!Number.isFinite(minX)) return { x: 0, y: 0, w: 0, h: 0 }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

/** The local point an instance's x/y anchors to: size/2 or bounds center. */
export function defCenter(def: DeviceDefinition): { x: number; y: number } {
  if (def.size !== null) {
    return { x: def.size[0] / 2, y: def.size[1] / 2 }
  }
  const b = defBounds(def)
  return { x: b.x + b.w / 2, y: b.y + b.h / 2 }
}

// ---------------------------------------------------------------------------
// Shape generators (designer): emit LED + decor lists in the built-in style.
// ---------------------------------------------------------------------------

function circleLeds(
  cx: number,
  cy: number,
  radius: number,
  count: number,
  dotRadius: number,
): LedShape[] {
  const leds: LedShape[] = []
  for (let i = 0; i < count; i += 1) {
    const angle = (i / count) * Math.PI * 2
    leds.push({
      type: 'circle',
      center: [
        Math.round((cx + radius * Math.cos(angle)) * 100) / 100,
        Math.round((cy + radius * Math.sin(angle)) * 100) / 100,
      ],
      radius: dotRadius,
    })
  }
  return leds
}

function stripeLeds(
  cx: number,
  top: number,
  count: number,
  pitch = 16,
  size = 11,
): LedShape[] {
  const leds: LedShape[] = []
  for (let i = 0; i < count; i += 1) {
    leds.push({
      type: 'rect',
      rect: [
        Math.round((cx - size / 2) * 100) / 100,
        Math.round((top + i * pitch) * 100) / 100,
        size,
        size,
      ],
      radius: 2,
    })
  }
  return leds
}

/** Generate a straight strip: `count` square LEDs on a housing. */
export function generateStrip(count: number, pitch = 16, size = 11): {
  leds: LedShape[]
  decor: DecorShape[]
} {
  const pad = 12
  const width = (count - 1) * pitch + size + pad * 2
  const height = size + pad * 2
  return {
    leds: stripeLeds(pad + size / 2, pad, count, pitch, size),
    decor: [
      {
        type: 'rect',
        rect: [0, 0, Math.round(width), Math.round(height)],
        radius: 8,
        fill: true,
        fill_color: '#161616',
        stroke_color: '#3a3a3a',
        stroke_width: 2,
        stroke_align: 'inside',
        opacity: 1,
      },
    ],
  }
}

/** Generate a fan ring: `count` dot LEDs inside a framed circle. */
export function generateRing(count: number, dotRadius = 5.5): {
  leds: LedShape[]
  decor: DecorShape[]
} {
  const pad = 10
  const frameRadius = Math.max((count * 16) / (2 * Math.PI), 26)
  const size = (frameRadius + dotRadius + pad) * 2
  const cx = size / 2
  const cy = size / 2
  const ringRadius = frameRadius
  return {
    leds: circleLeds(cx, cy, ringRadius, count, dotRadius),
    decor: [
      {
        type: 'circle',
        center: [Math.round(cx), Math.round(cy)],
        radius: Math.round(frameRadius + dotRadius + 2),
        fill: false,
        fill_color: '#222222',
        stroke_color: '#3a3a3a',
        stroke_width: 2,
        stroke_align: 'inside',
        opacity: 1,
      },
      {
        type: 'circle',
        center: [Math.round(cx), Math.round(cy)],
        radius: 14,
        fill: true,
        fill_color: '#161616',
        stroke_color: '#333333',
        stroke_width: 1,
        stroke_align: 'inside',
        opacity: 1,
      },
    ],
  }
}

/** Generate a dual-ring fan: ring dots plus two side LED stripes. */
export function generateDual(
  ringCount: number,
  sideCount: number,
  dotRadius = 5.5,
): { leds: LedShape[]; decor: DecorShape[] } {
  const pitch = 16
  const size = 11
  const ringRadius = Math.max((ringCount * pitch) / (2 * Math.PI), 26)
  const stripeOffset = ringRadius + 16
  const stripeH = (sideCount - 1) * pitch + size
  const pad = 4
  const width = Math.ceil((stripeOffset + size / 2 + pad) * 2)
  const height = Math.ceil(stripeH + pad * 2)
  const cx = width / 2
  const cy = height / 2
  const stripeTop = (height - stripeH) / 2
  const leds: LedShape[] = [
    ...circleLeds(cx, cy, ringRadius, ringCount, dotRadius),
    ...stripeLeds(cx - stripeOffset, stripeTop, sideCount),
    ...stripeLeds(cx + stripeOffset, stripeTop, sideCount),
  ]
  return {
    leds,
    decor: [
      {
        type: 'rect',
        rect: [0, 0, width, height],
        radius: 10,
        fill: false,
        fill_color: '#222222',
        stroke_color: '#2a2a2a',
        stroke_width: 2,
        stroke_align: 'inside',
        opacity: 1,
      },
      {
        type: 'circle',
        center: [Math.round(cx), Math.round(cy)],
        radius: Math.round(ringRadius + 9),
        fill: false,
        fill_color: '#222222',
        stroke_color: '#3a3a3a',
        stroke_width: 2,
        stroke_align: 'inside',
        opacity: 1,
      },
      {
        type: 'circle',
        center: [Math.round(cx), Math.round(cy)],
        radius: 9,
        fill: true,
        fill_color: '#161616',
        stroke_color: '#333333',
        stroke_width: 1,
        stroke_align: 'inside',
        opacity: 1,
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// Thumbnails: static definition render for the library list.
// ---------------------------------------------------------------------------

function paintDecor(
  ctx: CanvasRenderingContext2D,
  shape: DecorShape,
): void {
  ctx.globalAlpha = shape.opacity
  ctx.beginPath()
  if (shape.type === 'rect') {
    ctx.roundRect(shape.rect[0], shape.rect[1], shape.rect[2], shape.rect[3], shape.radius ?? 0)
  } else if (shape.type === 'circle') {
    ctx.arc(shape.center[0], shape.center[1], shape.radius, 0, Math.PI * 2)
  } else {
    ctx.moveTo(shape.points[0][0], shape.points[0][1])
    for (let i = 1; i < shape.points.length; i += 1) {
      ctx.lineTo(shape.points[i][0], shape.points[i][1])
    }
    if (shape.type === 'polygon') ctx.closePath()
  }
  if (shape.type !== 'polyline') {
    if (shape.fill) {
      ctx.fillStyle = shape.fill_color
      ctx.fill()
    }
    if (shape.stroke_width > 0) {
      ctx.strokeStyle = shape.stroke_color
      ctx.lineWidth = shape.stroke_width
      ctx.stroke()
    }
  } else if (shape.stroke_width > 0) {
    ctx.strokeStyle = shape.stroke_color
    ctx.lineWidth = shape.stroke_width
    ctx.stroke()
  }
  ctx.globalAlpha = 1
}

/** Hue for LED index i out of n: shows the chain order in thumbnails. */
export function ledHue(i: number, n: number): string {
  return `hsl(${Math.round((i / Math.max(n, 1)) * 300)},85%,55%)`
}

/** Draw a definition into a canvas of width x height, fit and centered. */
export function drawDefinitionThumbnail(
  ctx: CanvasRenderingContext2D,
  def: DeviceDefinition,
  width: number,
  height: number,
): void {
  ctx.clearRect(0, 0, width, height)
  const b = def.size !== null
    ? { x: 0, y: 0, w: def.size[0], h: def.size[1] }
    : defBounds(def)
  const scale = Math.min(
    (width - 8) / Math.max(b.w, 1),
    (height - 8) / Math.max(b.h, 1),
    6,
  )
  ctx.save()
  ctx.translate(
    width / 2 - (b.x + b.w / 2) * scale,
    height / 2 - (b.y + b.h / 2) * scale,
  )
  ctx.scale(scale, scale)
  for (const shape of def.decor) paintDecor(ctx, shape)
  def.leds.forEach((led, i) => {
    ctx.beginPath()
    if (led.type === 'rect') {
      ctx.roundRect(led.rect[0], led.rect[1], led.rect[2], led.rect[3], led.radius ?? 0)
    } else if (led.type === 'circle') {
      ctx.arc(led.center[0], led.center[1], led.radius, 0, Math.PI * 2)
    } else {
      ctx.moveTo(led.points[0][0], led.points[0][1])
      for (let k = 1; k < led.points.length; k += 1) {
        ctx.lineTo(led.points[k][0], led.points[k][1])
      }
      ctx.closePath()
    }
    ctx.fillStyle = ledHue(i, def.leds.length)
    ctx.fill()
    if (led.stroke_color && (led.stroke_width ?? 0) > 0) {
      ctx.strokeStyle = led.stroke_color
      ctx.lineWidth = led.stroke_width ?? 1
      ctx.stroke()
    }
  })
  ctx.restore()
}
