/**
 * Interaction controller for box-based canvas stages: selection,
 * drag/move, resize/rotate handles, marquee and pan state machine.
 * Framework-agnostic; a host component wires the DOM events and draws
 * the overlay. The adapter applies every change to its own document.
 */

import { ref } from 'vue'
import type { Ref } from 'vue'
import {
  angleDelta,
  angleTo,
  handleAt,
  handleCursor,
  pointInRotatedBox,
  resizeBoxRotated,
  rotateZoneAt,
  snapBox,
  snapResize,
  unionBox,
} from './geometry'
import type { HandleId, SnapGuide, WidgetBox } from './geometry'
import { rotateCursor } from './cursors'

export interface StageBox {
  id: string
  box: WidgetBox
  /** Rotation in degrees for frame drawing and resize/rotate math. */
  rotation: number
  /** Rotation for hit-testing; defaults to `rotation`. */
  hitRotation?: number
  /** Locked: mouse-transparent, gray dashed frame. */
  locked?: boolean
  /** Group-like: dashed frame, no handles/rotation on canvas. */
  handleless?: boolean
}

export interface StageAdapter {
  /** All boxes in z-order (last = topmost). */
  getBoxes(): StageBox[]
  /** Currently selected ids (may include locked entries). */
  getSelection(): string[]
  /** Apply a new selection (full list, already resolved). */
  setSelection(ids: string[]): void
  /** Capture per-id origins before the first move of a drag gesture. */
  dragStart?(ids: string[]): void
  /** Apply a snapped, rounded delta to the given ids. */
  moveBy(ids: string[], dx: number, dy: number): void
  /** Apply a resized box in logical canvas pixels. */
  resizeTo(id: string, box: WidgetBox): void
  /** Apply an absolute rotation in degrees. */
  rotateTo(id: string, degrees: number): void
  /** One undo snapshot per gesture. */
  beginBatch(): void
  endBatch(): void
  /**
   * Custom pointer handling (e.g. mask painting). When pointerDown
   * returns true the stage idles out of its own state machine and
   * forwards moves/ups to the remaining hooks until release.
   */
  pointerDown?(x: number, y: number, event: PointerEvent): boolean
  pointerMove?(x: number, y: number, event: PointerEvent): void
  pointerUp?(x: number, y: number, event: PointerEvent): void
}

type InteractionMode =
  | { kind: 'idle' }
  | { kind: 'custom' }
  | {
      kind: 'pan'
      startX: number
      startY: number
      startPanX: number
      startPanY: number
    }
  | {
      kind: 'drag'
      startX: number
      startY: number
      ids: string[]
      origins: Map<string, WidgetBox>
      /**
       * Id to deselect if this gesture ends as a click (Figma-style
       * deferred toggle): Shift+pointerdown on an already-selected box
       * must still allow Shift+drag to move it.
       */
      toggleCandidate: string | null
    }
  | {
      kind: 'resize'
      handle: HandleId
      id: string
      origin: WidgetBox
      rotation: number
      startX: number
      startY: number
    }
  | {
      kind: 'rotate'
      id: string
      center: { x: number; y: number }
      startAngle: number
      startRotation: number
    }
  | { kind: 'marquee'; startX: number; startY: number }

export interface MarqueeRect {
  x1: number
  y1: number
  x2: number
  y2: number
}

/** Snap threshold in screen pixels (divided by zoom per event). */
export const SNAP_THRESHOLD = 5

export interface StageController {
  guides: Ref<SnapGuide[]>
  marquee: Ref<MarqueeRect | null>
  hoverCursor: Ref<string | null>
  toCanvas: (event: PointerEvent | MouseEvent) => { x: number; y: number }
  onPointerdown: (event: PointerEvent) => void
  onPointermove: (event: PointerEvent) => void
  onPointerup: (event: PointerEvent) => void
}

export function createStageController(options: {
  adapter: StageAdapter
  canvas: () => HTMLCanvasElement | null
  zoom: () => number
  canvasWidth: () => number
  canvasHeight: () => number
  /** Set the viewport pan (logical screen px, absolute). */
  pan?: (x: number, y: number) => void
  getPan?: () => { x: number; y: number }
  /** Extra pan trigger (viewport Space key), beyond middle-button drag. */
  spaceHeld?: () => boolean
}): StageController {
  const { adapter } = options
  const guides = ref<SnapGuide[]>([])
  const marquee = ref<MarqueeRect | null>(null)
  const hoverCursor = ref<string | null>(null)

  let interaction: InteractionMode = { kind: 'idle' }

  function toCanvas(event: PointerEvent | MouseEvent): { x: number; y: number } {
    const rect = options.canvas()?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return {
      x: ((event.clientX - rect.left) / rect.width) * options.canvasWidth(),
      y: ((event.clientY - rect.top) / rect.height) * options.canvasHeight(),
    }
  }

  function capturePointer(event: PointerEvent): void {
    const panel = options.canvas()
    if (panel === null) return
    try {
      panel.setPointerCapture(event.pointerId)
    } catch {
      // Synthetic pointers (tests) have no active pointer to capture.
    }
  }

  /** Selected, unlocked boxes: the ones interactions can act on. */
  function interactiveBoxes(): StageBox[] {
    const selection = adapter.getSelection()
    return adapter
      .getBoxes()
      .filter((info) => selection.includes(info.id) && !info.locked)
  }

  function onPointerdown(event: PointerEvent): void {
    if (options.canvas() === null) return
    if (event.button === 1 || (event.button === 0 && options.spaceHeld?.() === true)) {
      startPan(event)
      return
    }
    if (event.button !== 0) return
    const point = toCanvas(event)

    if (adapter.pointerDown?.(point.x, point.y, event) === true) {
      interaction = { kind: 'custom' }
      capturePointer(event)
      return
    }

    const selection = interactiveBoxes()
    const single = selection.length === 1 ? selection[0]! : null

    // Handles first (single selection only). Handleless groups have no
    // individual handles; they move as a unit.
    if (single !== null && !single.handleless) {
      const rotation = single.rotation
      const handle = handleAt(point.x, point.y, single.box, options.zoom(), rotation)
      if (handle !== null) {
        interaction = {
          kind: 'resize',
          handle,
          id: single.id,
          origin: { ...single.box },
          rotation,
          startX: point.x,
          startY: point.y,
        }
        hoverCursor.value = handleCursor(handle, rotation)
        adapter.beginBatch()
        capturePointer(event)
        return
      }
      // Photoshop-style rotation: grab just outside a corner of the frame.
      const corner = rotateZoneAt(point.x, point.y, single.box, options.zoom(), rotation)
      if (corner !== null) {
        interaction = {
          kind: 'rotate',
          id: single.id,
          center: {
            x: single.box.x + single.box.w / 2,
            y: single.box.y + single.box.h / 2,
          },
          startAngle: angleTo(
            single.box.x + single.box.w / 2,
            single.box.y + single.box.h / 2,
            point.x,
            point.y,
          ),
          startRotation: rotation,
        }
        hoverCursor.value = rotateCursor(corner)
        adapter.beginBatch()
        capturePointer(event)
        return
      }
    }

    // Box hit-test, topmost first. Locked boxes are mouse-transparent.
    const boxes = adapter.getBoxes()
    for (let i = boxes.length - 1; i >= 0; i -= 1) {
      const info = boxes[i]!
      if (info.locked) continue
      if (pointInRotatedBox(point.x, point.y, info.box, info.hitRotation ?? info.rotation)) {
        startDrag(info.id, point, event)
        capturePointer(event)
        return
      }
    }

    // Empty space: marquee (clears selection unless shift).
    if (!event.shiftKey) adapter.setSelection([])
    interaction = { kind: 'marquee', startX: point.x, startY: point.y }
    marquee.value = { x1: point.x, y1: point.y, x2: point.x, y2: point.y }
    capturePointer(event)
  }

  function startPan(event: PointerEvent): void {
    const pan = options.getPan?.() ?? { x: 0, y: 0 }
    interaction = {
      kind: 'pan',
      startX: event.clientX,
      startY: event.clientY,
      startPanX: pan.x,
      startPanY: pan.y,
    }
    capturePointer(event)
    event.preventDefault()
  }

  function startDrag(id: string, point: { x: number; y: number }, event: PointerEvent): void {
    const priorSelection = adapter.getSelection()
    let ids: string[]
    let toggleCandidate: string | null = null
    if (event.shiftKey) {
      if (priorSelection.includes(id)) {
        // Deferred deselect: Shift+drag must move the selection, only
        // a click without movement toggles the box off (pointerup).
        ids = [...priorSelection]
        toggleCandidate = id
      } else {
        ids = [...priorSelection, id]
        adapter.setSelection(ids)
      }
    } else if (!priorSelection.includes(id)) {
      ids = [id]
      adapter.setSelection(ids)
    } else {
      ids = [...priorSelection]
    }
    const origins = new Map<string, WidgetBox>()
    for (const info of interactiveBoxes()) {
      origins.set(info.id, { ...info.box })
    }
    adapter.dragStart?.([...origins.keys()])
    interaction = {
      kind: 'drag',
      startX: point.x,
      startY: point.y,
      ids: [...origins.keys()],
      origins,
      toggleCandidate,
    }
    adapter.beginBatch()
  }

  function onPointermove(event: PointerEvent): void {
    const point = toCanvas(event)
    switch (interaction.kind) {
      case 'pan': {
        options.pan?.(
          interaction.startPanX + (event.clientX - interaction.startX),
          interaction.startPanY + (event.clientY - interaction.startY),
        )
        return
      }
      case 'custom': {
        adapter.pointerMove?.(point.x, point.y, event)
        return
      }
      case 'drag': {
        const mode = interaction
        const rawDx = point.x - mode.startX
        const rawDy = point.y - mode.startY
        // Shift constrains the move to 45° directions (standard editors).
        let dx = rawDx
        let dy = rawDy
        if (event.shiftKey && (rawDx !== 0 || rawDy !== 0)) {
          const angle =
            Math.round(Math.atan2(rawDy, rawDx) / (Math.PI / 4)) * (Math.PI / 4)
          const length = Math.hypot(rawDx, rawDy)
          dx = Math.cos(angle) * length
          dy = Math.sin(angle) * length
        }
        // Snap the union of the moving boxes.
        const moving = mode.ids
        const union = unionBox(
          moving.map((id) => {
            const origin = mode.origins.get(id)
            return origin !== undefined
              ? { x: origin.x + dx, y: origin.y + dy, w: origin.w, h: origin.h }
              : { x: 0, y: 0, w: 0, h: 0 }
          }),
        )
        if (union !== null && !event.altKey && !event.shiftKey) {
          const originIds = new Set(moving)
          const others = adapter
            .getBoxes()
            .filter((info) => !originIds.has(info.id))
            .map((info) => info.box)
          const snapped = snapBox(
            union,
            others,
            options.canvasWidth(),
            options.canvasHeight(),
            SNAP_THRESHOLD / options.zoom(),
          )
          dx += snapped.x - union.x
          dy += snapped.y - union.y
          guides.value = snapped.guides
        } else {
          guides.value = []
        }
        adapter.moveBy(moving, Math.round(dx), Math.round(dy))
        return
      }
      case 'resize': {
        const mode = interaction
        const next = resizeBoxRotated(
          mode.origin,
          mode.handle,
          point.x - mode.startX,
          point.y - mode.startY,
          mode.rotation,
        )
        let box = next
        // Smart guides only exist in the axis-aligned frame.
        if (mode.rotation % 360 === 0 && !event.altKey) {
          const others = adapter
            .getBoxes()
            .filter((info) => info.id !== mode.id)
            .map((info) => info.box)
          const snapped = snapResize(
            next,
            mode.handle,
            others,
            options.canvasWidth(),
            options.canvasHeight(),
            SNAP_THRESHOLD / options.zoom(),
          )
          box = snapped.box
          guides.value = snapped.guides
        } else {
          guides.value = []
        }
        adapter.resizeTo(mode.id, box)
        return
      }
      case 'rotate': {
        // Delta-based: the grabbed corner stays under the cursor.
        const angle = angleTo(interaction.center.x, interaction.center.y, point.x, point.y)
        let degrees = interaction.startRotation + angleDelta(interaction.startAngle, angle)
        if (event.shiftKey) degrees = Math.round(degrees / 15) * 15
        adapter.rotateTo(interaction.id, degrees)
        return
      }
      case 'marquee': {
        marquee.value = {
          x1: interaction.startX,
          y1: interaction.startY,
          x2: point.x,
          y2: point.y,
        }
        return
      }
      case 'idle': {
        updateCursor(point)
        return
      }
    }
  }

  function onPointerup(event: PointerEvent): void {
    if (interaction.kind === 'custom') {
      const point = toCanvas(event)
      adapter.pointerUp?.(point.x, point.y, event)
    }
    if (interaction.kind === 'drag' && interaction.toggleCandidate !== null) {
      // A Shift+pointerdown on an already-selected box only deselects
      // when the gesture ends without movement (a click, not a drag).
      const point = toCanvas(event)
      const movedPx =
        Math.hypot(point.x - interaction.startX, point.y - interaction.startY) *
        options.zoom()
      if (movedPx < 4) {
        const candidate = interaction.toggleCandidate
        adapter.setSelection(
          adapter.getSelection().filter((s) => s !== candidate),
        )
      }
    }
    if (interaction.kind === 'marquee' && marquee.value !== null) {
      commitMarquee(marquee.value)
      marquee.value = null
    }
    if (interaction.kind !== 'idle' && interaction.kind !== 'pan') {
      adapter.endBatch()
    }
    guides.value = []
    interaction = { kind: 'idle' }
    options.canvas()?.releasePointerCapture?.(event.pointerId)
  }

  /** Intersecting (not just contained) unlocked boxes, in z-order. */
  function commitMarquee(m: MarqueeRect): void {
    const x1 = Math.min(m.x1, m.x2)
    const x2 = Math.max(m.x1, m.x2)
    const y1 = Math.min(m.y1, m.y2)
    const y2 = Math.max(m.y1, m.y2)
    const hits = adapter
      .getBoxes()
      .filter((info) => !info.locked)
      .filter((info) => {
        const b = info.box
        return b.x < x2 && b.x + b.w > x1 && b.y < y2 && b.y + b.h > y1
      })
      .map((info) => info.id)
    adapter.setSelection([...new Set([...adapter.getSelection(), ...hits])])
  }

  function updateCursor(point: { x: number; y: number }): void {
    const selection = interactiveBoxes()
    if (selection.length === 1 && !selection[0]!.handleless) {
      const single = selection[0]!
      const rotation = single.rotation
      const handle = handleAt(point.x, point.y, single.box, options.zoom(), rotation)
      if (handle !== null) {
        hoverCursor.value = handleCursor(handle, rotation)
        return
      }
      const corner = rotateZoneAt(point.x, point.y, single.box, options.zoom(), rotation)
      if (corner !== null) {
        hoverCursor.value = rotateCursor(corner)
        return
      }
    }
    const boxes = adapter.getBoxes()
    for (let i = boxes.length - 1; i >= 0; i -= 1) {
      const info = boxes[i]!
      if (info.locked) continue
      if (
        pointInRotatedBox(point.x, point.y, info.box, info.hitRotation ?? info.rotation)
      ) {
        hoverCursor.value = 'move'
        return
      }
    }
    hoverCursor.value = null
  }

  return { guides, marquee, hoverCursor, toCanvas, onPointerdown, onPointermove, onPointerup }
}
