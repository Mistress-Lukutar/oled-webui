/**
 * Geometry helpers for canvas interactions: hit-testing, resize handles,
 * snapping. All coordinates are scene pixels unless noted.
 */

export interface WidgetBox {
  x: number
  y: number
  w: number
  h: number
}

export type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w'
export type CornerId = 'nw' | 'ne' | 'se' | 'sw'

export function pointInBox(px: number, py: number, box: WidgetBox): boolean {
  return px >= box.x && px <= box.x + box.w && py >= box.y && py <= box.y + box.h
}

/** Rotate a point around a center, CCW positive (Pillow convention, y-down canvas). */
function rotateAround(
  px: number,
  py: number,
  cx: number,
  cy: number,
  rotation: number,
): { x: number; y: number } {
  const rad = (rotation * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const ox = px - cx
  const oy = py - cy
  return { x: cx + ox * cos + oy * sin, y: cy - ox * sin + oy * cos }
}

/** Handle anchor points in scene coordinates, rotated with the widget. */
export function handlePositions(
  box: WidgetBox,
  rotation = 0,
): Record<HandleId, { x: number; y: number }> {
  const { x, y, w, h } = box
  const cx = x + w / 2
  const cy = y + h / 2
  const axisAligned: Record<HandleId, { x: number; y: number }> = {
    nw: { x, y },
    n: { x: cx, y },
    ne: { x: x + w, y },
    e: { x: x + w, y: y + h / 2 },
    se: { x: x + w, y: y + h },
    s: { x: cx, y: y + h },
    sw: { x, y: y + h },
    w: { x, y: y + h / 2 },
  }
  if (rotation % 360 === 0) return axisAligned
  const rotated = {} as Record<HandleId, { x: number; y: number }>
  for (const [id, p] of Object.entries(axisAligned)) {
    rotated[id as HandleId] = rotateAround(p.x, p.y, cx, cy, rotation)
  }
  return rotated
}

const HANDLES: HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

/** Handle under a scene point, or null. */
export function handleAt(
  px: number,
  py: number,
  box: WidgetBox,
  zoom: number,
  rotation = 0,
): HandleId | null {
  const threshold = 6 / zoom
  const positions = handlePositions(box, rotation)
  for (const id of HANDLES) {
    const p = positions[id]
    if (Math.hypot(px - p.x, py - p.y) <= threshold) return id
  }
  return null
}

/** Point-in-box test for a widget rotated around its rect center. */
export function pointInRotatedBox(
  px: number,
  py: number,
  box: WidgetBox,
  rotation = 0,
): boolean {
  if (rotation % 360 === 0) return pointInBox(px, py, box)
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  const rad = (rotation * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const ox = px - cx
  const oy = py - cy
  // Scene offset -> box-local coordinates (inverse rotation).
  const lx = ox * cos - oy * sin
  const ly = ox * sin + oy * cos
  return lx >= -box.w / 2 && lx <= box.w / 2 && ly >= -box.h / 2 && ly <= box.h / 2
}

/**
 * Corner whose "grab just outside the handle" rotate zone contains the
 * point (Photoshop-style rotation). Returns null inside the box or away
 * from the corners.
 */
export function rotateZoneAt(
  px: number,
  py: number,
  box: WidgetBox,
  zoom: number,
  rotation = 0,
): CornerId | null {
  const inner = 6 / zoom
  const outer = 22 / zoom
  const positions = handlePositions(box, rotation)
  for (const corner of ['nw', 'ne', 'se', 'sw'] as const) {
    const p = positions[corner]
    const distance = Math.hypot(px - p.x, py - p.y)
    if (
      distance > inner &&
      distance <= outer &&
      !pointInRotatedBox(px, py, box, rotation)
    ) {
      return corner
    }
  }
  return null
}

export interface ResizeResult {
  box: WidgetBox
}

/** Apply a resize drag for one handle; enforces a 1px minimum size. */
export function resizeBox(
  box: WidgetBox,
  handle: HandleId,
  dx: number,
  dy: number,
): WidgetBox {
  let { x, y, w, h } = box
  if (handle.includes('e')) w += dx
  if (handle.includes('s')) h += dy
  if (handle.includes('w')) {
    x += dx
    w -= dx
  }
  if (handle.includes('n')) {
    y += dy
    h -= dy
  }
  // Keep size >= 1 while anchoring the opposite edge/corner.
  if (w < 1) {
    if (handle.includes('w')) x -= 1 - w
    w = 1
  }
  if (h < 1) {
    if (handle.includes('n')) y -= 1 - h
    h = 1
  }
  return { x, y, w, h }
}

/** CSS cursor for a handle id, oriented by the widget rotation. */
export function handleCursor(handle: HandleId, rotation = 0): string {
  const baseAngles: Record<HandleId, number> = {
    n: 0,
    ne: 45,
    e: 90,
    se: 135,
    s: 180,
    sw: 225,
    w: 270,
    nw: 315,
  }
  const effective = (((baseAngles[handle] + rotation) % 180) + 180) % 180
  const step = Math.round(effective / 45) % 4
  return (['ns-resize', 'nesw-resize', 'ew-resize', 'nwse-resize'] as const)[step]
}

/**
 * Resize a rotated widget box: the drag delta arrives in scene
 * coordinates, is applied along the box's rotated axes, and the result
 * is re-anchored so the opposite edge/corner stays fixed on screen.
 */
export function resizeBoxRotated(
  box: WidgetBox,
  handle: HandleId,
  dx: number,
  dy: number,
  rotation = 0,
): WidgetBox {
  const rad = (rotation * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  // Scene delta -> box-local delta (inverse rotation).
  const dlx = dx * cos - dy * sin
  const dly = dx * sin + dy * cos
  const local = resizeBox(
    { x: -box.w / 2, y: -box.h / 2, w: box.w, h: box.h },
    handle,
    dlx,
    dly,
  )
  // Map the new local center back to scene space around the original
  // center, so the anchor edge/corner stays put on screen.
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  const ncxL = local.x + local.w / 2
  const ncyL = local.y + local.h / 2
  const ncx = cx + ncxL * cos + ncyL * sin
  const ncy = cy - ncxL * sin + ncyL * cos
  return { x: ncx - local.w / 2, y: ncy - local.h / 2, w: local.w, h: local.h }
}

export interface SnapGuide {
  axis: 'x' | 'y'
  /** Guide position in scene pixels (for drawing). */
  at: number
}

export interface SnapResult {
  x: number
  y: number
  guides: SnapGuide[]
}

/**
 * Snap a moving box to the canvas edges/center and other boxes'
 * edges/centers within a threshold. Returns the snapped top-left.
 */
export function snapBox(
  moving: WidgetBox,
  others: WidgetBox[],
  canvasW: number,
  canvasH: number,
  threshold: number,
): SnapResult {
  const { xs, ys } = buildTargets(others, canvasW, canvasH)
  const bestX =
    nearest(moving.x, xs, threshold) ??
    nearest(moving.x + moving.w / 2, xs, threshold) ??
    nearest(moving.x + moving.w, xs, threshold)
  const bestY =
    nearest(moving.y, ys, threshold) ??
    nearest(moving.y + moving.h / 2, ys, threshold) ??
    nearest(moving.y + moving.h, ys, threshold)

  return {
    x: moving.x + (bestX?.delta ?? 0),
    y: moving.y + (bestY?.delta ?? 0),
    guides: [...(bestX ? [{ axis: 'x' as const, at: bestX.at }] : []), ...(bestY ? [{ axis: 'y' as const, at: bestY.at }] : [])],
  }
}

/** Bounding box of a list of boxes. */
export function unionBox(boxes: WidgetBox[]): WidgetBox | null {
  if (boxes.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const b of boxes) {
    minX = Math.min(minX, b.x)
    minY = Math.min(minY, b.y)
    maxX = Math.max(maxX, b.x + b.w)
    maxY = Math.max(maxY, b.y + b.h)
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

function buildTargets(
  others: WidgetBox[],
  canvasW: number,
  canvasH: number,
): { xs: number[]; ys: number[] } {
  const xs = [0, canvasW / 2, canvasW]
  const ys = [0, canvasH / 2, canvasH]
  for (const box of others) {
    xs.push(box.x, box.x + box.w / 2, box.x + box.w)
    ys.push(box.y, box.y + box.h / 2, box.y + box.h)
  }
  return { xs, ys }
}

function nearest(pos: number, targets: number[], threshold: number): { delta: number; at: number } | null {
  let best: { delta: number; at: number } | null = null
  for (const target of targets) {
    const delta = target - pos
    if (Math.abs(delta) <= threshold && (best === null || Math.abs(delta) < Math.abs(best.delta))) {
      best = { delta, at: target }
    }
  }
  return best
}

/**
 * Snap a resizing box by its moving edges only (per the active handle).
 * Handles without an axis component keep that axis unchanged.
 */
export function snapResize(
  next: WidgetBox,
  handle: HandleId,
  others: WidgetBox[],
  canvasW: number,
  canvasH: number,
  threshold: number,
): { box: WidgetBox; guides: SnapGuide[] } {
  const { xs, ys } = buildTargets(others, canvasW, canvasH)
  const box = { ...next }
  const guides: SnapGuide[] = []
  if (handle.includes('e')) {
    const snap = nearest(box.x + box.w, xs, threshold)
    if (snap !== null) {
      box.w += snap.delta
      guides.push({ axis: 'x', at: snap.at })
    }
  }
  if (handle.includes('w')) {
    const snap = nearest(box.x, xs, threshold)
    if (snap !== null) {
      box.x += snap.delta
      box.w -= snap.delta
      guides.push({ axis: 'x', at: snap.at })
    }
  }
  if (handle.includes('s')) {
    const snap = nearest(box.y + box.h, ys, threshold)
    if (snap !== null) {
      box.h += snap.delta
      guides.push({ axis: 'y', at: snap.at })
    }
  }
  if (handle.includes('n')) {
    const snap = nearest(box.y, ys, threshold)
    if (snap !== null) {
      box.y += snap.delta
      box.h -= snap.delta
      guides.push({ axis: 'y', at: snap.at })
    }
  }
  if (box.w < 1) box.w = 1
  if (box.h < 1) box.h = 1
  return { box, guides }
}

/** Angle (degrees, counter-clockwise) from a center to a point. */
export function angleTo(cx: number, cy: number, px: number, py: number): number {
  return (-Math.atan2(py - cy, px - cx) * 180) / Math.PI
}

/** Signed shortest delta between two angles in degrees. */
export function angleDelta(from: number, to: number): number {
  let delta = (to - from) % 360
  if (delta > 180) delta -= 360
  if (delta < -180) delta += 360
  return delta
}
