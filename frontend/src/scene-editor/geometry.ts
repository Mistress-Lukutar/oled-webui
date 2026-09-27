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

export type HandleId = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'rot'

export function pointInBox(px: number, py: number, box: WidgetBox): boolean {
  return px >= box.x && px <= box.x + box.w && py >= box.y && py <= box.y + box.h
}

/** Handle anchor points in scene coordinates. */
export function handlePositions(box: WidgetBox): Record<HandleId, { x: number; y: number }> {
  const { x, y, w, h } = box
  const cx = x + w / 2
  return {
    nw: { x, y },
    n: { x: cx, y },
    ne: { x: x + w, y },
    e: { x: x + w, y: y + h / 2 },
    se: { x: x + w, y: y + h },
    s: { x: cx, y: y + h },
    sw: { x, y: y + h },
    w: { x, y: y + h / 2 },
    rot: { x: cx, y: y - 18 },
  }
}

const HANDLES: HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

/** Handle under a scene point, or null. */
export function handleAt(
  px: number,
  py: number,
  box: WidgetBox,
  zoom: number,
  withRotate: boolean,
): HandleId | null {
  const threshold = 6 / zoom
  if (withRotate) {
    const rot = handlePositions(box)['rot']
    if (Math.hypot(px - rot.x, py - rot.y) <= threshold) return 'rot'
  }
  const positions = handlePositions(box)
  for (const id of HANDLES) {
    const p = positions[id]
    if (Math.hypot(px - p.x, py - p.y) <= threshold) return id
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

/** CSS cursor for a handle id. */
export function handleCursor(handle: HandleId): string {
  switch (handle) {
    case 'nw':
    case 'se':
      return 'nwse-resize'
    case 'ne':
    case 'sw':
      return 'nesw-resize'
    case 'n':
    case 's':
      return 'ns-resize'
    case 'e':
    case 'w':
      return 'ew-resize'
    case 'rot':
      return 'grab'
  }
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

/** Rotation angle (degrees) from a box center to a point. */
export function rotationFor(box: WidgetBox, px: number, py: number): number {
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  // Canvas y grows downward; report counter-clockwise degrees to match PIL.
  const deg = (-Math.atan2(py - cy, px - cx) * 180) / Math.PI
  return (deg + 360) % 360
}
