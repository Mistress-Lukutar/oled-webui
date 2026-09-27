<script setup lang="ts">
/**
 * Scene viewport: canvas mirror of the server renderer with zoom/pan,
 * widget selection, drag/resize/rotate, marquee and snap guides.
 * Component instances behave as locked groups (moved via `at`).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { expandDocument } from '../../scene-editor/expand'
import { evaluateEntries, makePlaceholderProvider } from '../../scene-editor/runtime'
import { createImageCache, drawScene } from '../../scene-editor/render/draw'
import { ensureFont } from '../../scene-editor/render/fonts'
import {
  handleAt,
  handleCursor,
  handlePositions,
  pointInBox,
  resizeBox,
  rotationFor,
  snapBox,
  snapResize,
  unionBox,
} from '../../scene-editor/geometry'
import type { HandleId, SnapGuide, WidgetBox } from '../../scene-editor/geometry'
import { isComponentInstance } from '../../scene-editor/types'
import type { EntryRaw, SceneDocumentRaw } from '../../scene-editor/types'
import type { EvalEntry } from '../../scene-editor/runtime'
import { viewState } from '../../scene-editor/viewState'

const { state: appState } = useDisplayStore()
const { state } = editor

const container = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)

const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const spaceHeld = ref(false)
const redrawTick = ref(0)

const provider = makePlaceholderProvider()
const images = createImageCache(() => {
  redrawTick.value += 1
})

const panelWidth = computed(
  () => state.resolutionOverride?.width ?? appState.resolution.width,
)
const panelHeight = computed(
  () => state.resolutionOverride?.height ?? appState.resolution.height,
)

const expansion = computed(() => {
  void redrawTick.value
  if (state.doc === null) return { entries: [], errors: [] as string[] }
  return expandDocument(state.doc as SceneDocumentRaw, state.components)
})

/** Evaluated entries from the last frame, reused for hit-testing. */
let lastEvaluated: EvalEntry[] = []

watchEffect(() => {
  const doc = state.doc
  if (doc === null) return
  for (const widget of editor.getWidgets()) {
    const style = widget['style']
    const family =
      style !== null && typeof style === 'object'
        ? (style as Record<string, unknown>)['family']
        : null
    if (typeof family === 'string' && family !== '') {
      void ensureFont(state.sceneId, family).then((family_) => {
        if (family_ !== null) redrawTick.value += 1
      })
    }
  }
})

// ----------------------------------------------------------------------
// Boxes: scene-space boxes per raw entry index (instances = union of
// expanded children).
// ----------------------------------------------------------------------

interface BoxInfo {
  sourceIndex: number
  box: WidgetBox
  isInstance: boolean
  isImage: boolean
  locked: boolean
}

const boxes = computed<BoxInfo[]>(() => {
  const bySource = new Map<number, WidgetBox[]>()
  for (const entry of lastEvaluated) {
    const rect = entry.expanded.widget['rect']
    if (!Array.isArray(rect) || rect.length !== 4) continue
    const box: WidgetBox = {
      x: Math.trunc(Number(rect[0])) + entry.offsetX,
      y: Math.trunc(Number(rect[1])) + entry.offsetY,
      w: Math.max(1, Math.trunc(Number(rect[2]))),
      h: Math.max(1, Math.trunc(Number(rect[3]))),
    }
    const list = bySource.get(entry.expanded.sourceIndex) ?? []
    list.push(box)
    bySource.set(entry.expanded.sourceIndex, list)
  }
  const result: BoxInfo[] = []
  editor.getWidgets().forEach((entry, index) => {
    const list = bySource.get(index)
    if (list === undefined) return
    const union = unionBox(list)
    if (union === null) return
    result.push({
      sourceIndex: index,
      box: union,
      isInstance: isComponentInstance(entry),
      isImage: entry['type'] === 'image',
      locked: entry['locked'] === true,
    })
  })
  return result
})

const guides = ref<SnapGuide[]>([])
const marquee = ref<{ x1: number; y1: number; x2: number; y2: number } | null>(null)

type InteractionMode =
  | { kind: 'idle' }
  | { kind: 'pan'; startX: number; startY: number; panX: number; panY: number }
  | {
      kind: 'drag'
      startX: number
      startY: number
      origins: Map<number, DragOrigin>
    }
  | {
      kind: 'resize'
      handle: HandleId
      sourceIndex: number
      origin: WidgetBox
      startX: number
      startY: number
    }
  | { kind: 'rotate'; sourceIndex: number; center: { x: number; y: number } }
  | { kind: 'marquee'; startX: number; startY: number }

interface DragOrigin {
  /** Raw rect top-left at drag start (plain widgets). */
  rectX: number
  rectY: number
  /** Evaluated box top-left at drag start (snapping reference). */
  boxX: number
  boxY: number
  /** Instance `at` at drag start, null for plain widgets. */
  at: [number, number] | null
}

let interaction: InteractionMode = { kind: 'idle' }
const hoverCursor = ref<string | null>(null)

// ----------------------------------------------------------------------
// Coordinate helpers
// ----------------------------------------------------------------------

function toScene(event: PointerEvent | MouseEvent): { x: number; y: number } {
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: ((event.clientX - rect.left) / rect.width) * panelWidth.value,
    y: ((event.clientY - rect.top) / rect.height) * panelHeight.value,
  }
}

function selectedBoxes(): BoxInfo[] {
  return boxes.value.filter((info) => state.selection.includes(info.sourceIndex))
}

/** Selection as seen by canvas interactions: locked entries are skipped. */
function interactiveBoxes(): BoxInfo[] {
  return selectedBoxes().filter((info) => !info.locked)
}

// ----------------------------------------------------------------------
// Raw document mutation helpers
// ----------------------------------------------------------------------

function rawEntry(index: number): EntryRaw | null {
  const widgets = state.doc?.widgets
  const entry = widgets?.[index]
  return entry === undefined ? null : (entry as EntryRaw)
}

function moveRawBy(index: number, dx: number, dy: number, origin: DragOrigin): void {
  editor.mutate((doc) => {
    const entry = doc.widgets?.[index] as Record<string, unknown> | undefined
    if (entry === undefined) return
    if (origin.at !== null) {
      entry['at'] = [origin.at[0] + dx, origin.at[1] + dy]
    } else {
      const rect = entry['rect']
      if (Array.isArray(rect) && rect.length === 4) {
        entry['rect'] = [
          Math.round(origin.rectX) + dx,
          Math.round(origin.rectY) + dy,
          rect[2],
          rect[3],
        ]
      }
    }
  })
}

function resizeRawTo(sourceIndex: number, next: WidgetBox): void {
  editor.mutate((doc) => {
    const entry = doc.widgets?.[sourceIndex] as Record<string, unknown> | undefined
    if (entry === undefined || isComponentInstance(entry as EntryRaw)) return
    entry['rect'] = [
      Math.round(next.x),
      Math.round(next.y),
      Math.max(1, Math.round(next.w)),
      Math.max(1, Math.round(next.h)),
    ]
  })
}

function rotateRawTo(sourceIndex: number, degrees: number): void {
  editor.mutate((doc) => {
    const entry = doc.widgets?.[sourceIndex] as Record<string, unknown> | undefined
    if (entry === undefined) return
    entry['rotation'] = Math.round(degrees * 10) / 10
  })
}

// ----------------------------------------------------------------------
// Pointer interactions
// ----------------------------------------------------------------------

const SNAP_THRESHOLD = 5 / 1 // screen px; converted per event

function capturePointer(panel: HTMLCanvasElement, event: PointerEvent): void {
  try {
    panel.setPointerCapture(event.pointerId)
  } catch {
    // Synthetic pointers (tests) have no active pointer to capture.
  }
}

function onPointerdown(event: PointerEvent): void {
  const panel = canvas.value
  if (panel === null) return
  if (spaceHeld.value || event.button === 1) {
    interaction = {
      kind: 'pan',
      startX: event.clientX,
      startY: event.clientY,
      panX: panX.value,
      panY: panY.value,
    }
    capturePointer(panel, event)
    event.preventDefault()
    return
  }
  if (event.button !== 0) return
  const point = toScene(event)
  const selection = interactiveBoxes()
  const single = selection.length === 1 ? selection[0]! : null

  // Handles first (single selection only).
  if (single !== null) {
    const handle = handleAt(point.x, point.y, single.box, zoom.value, single.isImage)
    if (handle === 'rot') {
      interaction = {
        kind: 'rotate',
        sourceIndex: single.sourceIndex,
        center: { x: single.box.x + single.box.w / 2, y: single.box.y + single.box.h / 2 },
      }
      editor.beginBatch()
      capturePointer(panel, event)
      return
    }
    if (handle !== null && !single.isInstance) {
      interaction = {
        kind: 'resize',
        handle,
        sourceIndex: single.sourceIndex,
        origin: { ...single.box },
        startX: point.x,
        startY: point.y,
      }
      editor.beginBatch()
      capturePointer(panel, event)
      return
    }
  }

  // Widget hit-test, topmost first. Locked widgets are mouse-transparent.
  for (let i = boxes.value.length - 1; i >= 0; i -= 1) {
    const info = boxes.value[i]!
    if (info.locked) continue
    if (pointInBox(point.x, point.y, info.box)) {
      let selection: number[]
      if (event.shiftKey) {
        selection = state.selection.includes(info.sourceIndex)
          ? state.selection.filter((s) => s !== info.sourceIndex)
          : [...state.selection, info.sourceIndex]
        editor.setSelection([...selection])
        if (!selection.includes(info.sourceIndex)) return
      } else if (!state.selection.includes(info.sourceIndex)) {
        selection = [info.sourceIndex]
        editor.setSelection([...selection])
      } else {
        selection = [...state.selection]
      }
      const origins = new Map<number, DragOrigin>()
      for (const selected of interactiveBoxes()) {
        const raw = rawEntry(selected.sourceIndex)
        let at: [number, number] | null = null
        let rectX = selected.box.x
        let rectY = selected.box.y
        if (raw !== null && isComponentInstance(raw)) {
          const atValue = raw['at']
          at = Array.isArray(atValue) && atValue.length === 2
            ? [Number(atValue[0]) || 0, Number(atValue[1]) || 0]
            : [0, 0]
        } else if (raw !== null) {
          const rect = raw['rect']
          if (Array.isArray(rect) && rect.length === 4) {
            rectX = Number(rect[0]) || 0
            rectY = Number(rect[1]) || 0
          }
        }
        origins.set(selected.sourceIndex, {
          rectX,
          rectY,
          boxX: selected.box.x,
          boxY: selected.box.y,
          at,
        })
      }
      interaction = { kind: 'drag', startX: point.x, startY: point.y, origins }
      editor.beginBatch()
      capturePointer(panel, event)
      return
    }
  }

  // Empty space: marquee (clears selection unless shift).
  if (!event.shiftKey) editor.setSelection([])
  interaction = { kind: 'marquee', startX: point.x, startY: point.y }
  marquee.value = { x1: point.x, y1: point.y, x2: point.x, y2: point.y }
  capturePointer(panel, event)
}

function onPointermove(event: PointerEvent): void {
  const point = toScene(event)
  switch (interaction.kind) {
    case 'pan': {
      panX.value = interaction.panX + (event.clientX - interaction.startX)
      panY.value = interaction.panY + (event.clientY - interaction.startY)
      return
    }
    case 'drag': {
      const mode = interaction
      const rawDx = point.x - mode.startX
      const rawDy = point.y - mode.startY
      // Snap the union of the moving (evaluated) boxes.
      const moving = selectedBoxes()
      const union = unionBox(
        moving.map((info) => {
          const origin = mode.origins.get(info.sourceIndex)
          return {
            x: (origin?.boxX ?? info.box.x) + rawDx,
            y: (origin?.boxY ?? info.box.y) + rawDy,
            w: info.box.w,
            h: info.box.h,
          }
        }),
      )
      let dx = rawDx
      let dy = rawDy
      if (union !== null && !event.altKey) {
        const others = boxes.value
          .filter((info) => !mode.origins.has(info.sourceIndex))
          .map((info) => info.box)
        const snapped = snapBox(union, others, panelWidth.value, panelHeight.value, SNAP_THRESHOLD / zoom.value)
        dx += snapped.x - union.x
        dy += snapped.y - union.y
        guides.value = snapped.guides
      } else {
        guides.value = []
      }
      const dxR = Math.round(dx)
      const dyR = Math.round(dy)
      for (const [index, origin] of mode.origins) {
        moveRawBy(index, dxR, dyR, origin)
      }
      return
    }
    case 'resize': {
      const mode = interaction
      const origin = mode.origin
      const next = resizeBox(origin, mode.handle, point.x - mode.startX, point.y - mode.startY)
      let box = next
      if (!event.altKey) {
        const others = boxes.value
          .filter((info) => info.sourceIndex !== mode.sourceIndex)
          .map((info) => info.box)
        const snapped = snapResize(next, mode.handle, others, panelWidth.value, panelHeight.value, SNAP_THRESHOLD / zoom.value)
        box = snapped.box
        guides.value = snapped.guides
      } else {
        guides.value = []
      }
      resizeRawTo(mode.sourceIndex, box)
      return
    }
    case 'rotate': {
      let degrees = rotationFor(
        { x: interaction.center.x - 0, y: interaction.center.y - 0, w: 0, h: 0 },
        point.x,
        point.y,
      )
      if (event.shiftKey) degrees = Math.round(degrees / 15) * 15
      rotateRawTo(interaction.sourceIndex, degrees)
      return
    }
    case 'marquee': {
      marquee.value = { x1: interaction.startX, y1: interaction.startY, x2: point.x, y2: point.y }
      return
    }
    case 'idle': {
      updateCursor(point)
      return
    }
  }
}

function onPointerup(event: PointerEvent): void {
  if (interaction.kind === 'marquee' && marquee.value !== null) {
    const m = marquee.value
    const x1 = Math.min(m.x1, m.x2)
    const x2 = Math.max(m.x1, m.x2)
    const y1 = Math.min(m.y1, m.y2)
    const y2 = Math.max(m.y1, m.y2)
    const hits = boxes.value
      .filter((info) => !info.locked)
      .filter((info) => {
        const b = info.box
        return b.x < x2 && b.x + b.w > x1 && b.y < y2 && b.y + b.h > y1
      })
      .map((info) => info.sourceIndex)
    editor.setSelection([...new Set([...state.selection, ...hits])].sort((a, b) => a - b))
    marquee.value = null
  }
  if (interaction.kind !== 'idle' && interaction.kind !== 'pan') {
    editor.endBatch()
  }
  guides.value = []
  interaction = { kind: 'idle' }
  canvas.value?.releasePointerCapture?.(event.pointerId)
}

function updateCursor(point: { x: number; y: number }): void {
  if (spaceHeld.value) {
    hoverCursor.value = 'grab'
    return
  }
  const selection = interactiveBoxes()
  if (selection.length === 1) {
    const single = selection[0]!
    const handle = handleAt(point.x, point.y, single.box, zoom.value, single.isImage)
    if (handle !== null) {
      hoverCursor.value = handleCursor(handle)
      return
    }
  }
  for (let i = boxes.value.length - 1; i >= 0; i -= 1) {
    if (pointInBox(point.x, point.y, boxes.value[i]!.box)) {
      hoverCursor.value = 'move'
      return
    }
  }
  hoverCursor.value = null
}

// ----------------------------------------------------------------------
// Zoom / pan basics
// ----------------------------------------------------------------------

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
  const next = Math.max(0.05, Math.min(12, zoom.value * factor))
  const rect = canvas.value?.getBoundingClientRect()
  if (rect) {
    const cx = event.clientX - (rect.left + rect.width / 2)
    const cy = event.clientY - (rect.top + rect.height / 2)
    const scale = next / zoom.value
    panX.value = cx - (cx - panX.value) * scale
    panY.value = cy - (cy - panY.value) * scale
  }
  zoom.value = next
}

function fit(): void {
  const box = container.value
  if (box === null) return
  const margin = 32
  const zw = (box.clientWidth - margin) / panelWidth.value
  const zh = (box.clientHeight - margin) / panelHeight.value
  zoom.value = Math.max(0.05, Math.min(zw, zh))
  panX.value = 0
  panY.value = 0
}

let observer: ResizeObserver | null = null

watch([panelWidth, panelHeight], () => fit())

onMounted(() => {
  fit()
  requestAnimationFrame(() => fit())
  void document.fonts.ready.then(() => fit())
  observer = new ResizeObserver(() => fit())
  if (container.value !== null) observer.observe(container.value)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
})

function onKeydown(event: KeyboardEvent): void {
  if (event.code === 'Space' && isCanvasTarget(event)) {
    spaceHeld.value = true
    event.preventDefault()
  }
}

function onKeyup(event: KeyboardEvent): void {
  if (event.code === 'Space') spaceHeld.value = false
}

function isCanvasTarget(event: Event): boolean {
  return (
    container.value !== null &&
    container.value.contains(event.target as Node) &&
    !isFormTarget(event.target)
  )
}

function isFormTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

const transformStyle = computed(() => ({
  width: `${panelWidth.value * zoom.value}px`,
  height: `${panelHeight.value * zoom.value}px`,
  transform: `translate(${panX.value}px, ${panY.value}px)`,
}))

// Publish the view state for other panels (widget insertion).
watchEffect(() => {
  viewState.zoom = zoom.value
  viewState.panX = panX.value
  viewState.panY = panY.value
})

// ----------------------------------------------------------------------
// Drawing: scene + interaction overlay
// ----------------------------------------------------------------------

const ACCENT = '#35c98e'

function drawOverlay(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
): void {
  const selection = selectedBoxes()
  const line = 1.5 / zoom.value
  const handleSize = 8 / zoom.value

  if (marquee.value !== null) {
    const m = marquee.value
    ctx.save()
    ctx.fillStyle = 'rgba(53, 201, 142, 0.12)'
    ctx.strokeStyle = ACCENT
    ctx.lineWidth = line
    ctx.fillRect(
      Math.min(m.x1, m.x2),
      Math.min(m.y1, m.y2),
      Math.abs(m.x2 - m.x1),
      Math.abs(m.y2 - m.y1),
    )
    ctx.strokeRect(
      Math.min(m.x1, m.x2),
      Math.min(m.y1, m.y2),
      Math.abs(m.x2 - m.x1),
      Math.abs(m.y2 - m.y1),
    )
    ctx.restore()
  }

  for (const guide of guides.value) {
    ctx.save()
    ctx.strokeStyle = ACCENT
    ctx.lineWidth = line
    ctx.setLineDash([6 / zoom.value, 4 / zoom.value])
    ctx.beginPath()
    if (guide.axis === 'x') {
      ctx.moveTo(guide.at, 0)
      ctx.lineTo(guide.at, height)
    } else {
      ctx.moveTo(0, guide.at)
      ctx.lineTo(width, guide.at)
    }
    ctx.stroke()
    ctx.restore()
  }

  for (const info of selection) {
    const { box } = info
    ctx.save()
    ctx.strokeStyle = info.locked ? '#8a8a8a' : ACCENT
    ctx.lineWidth = line
    if (info.isInstance || info.locked) ctx.setLineDash([5 / zoom.value, 3 / zoom.value])
    ctx.strokeRect(box.x, box.y, box.w, box.h)
    ctx.restore()
    if (info.isInstance || info.locked) continue
    // Handles: white squares with accent border, screen-constant size.
    const positions = handlePositions(box)
    const ids: HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
    for (const id of ids) {
      const p = positions[id]
      ctx.save()
      ctx.fillStyle = '#ffffff'
      ctx.strokeStyle = ACCENT
      ctx.lineWidth = line
      ctx.beginPath()
      ctx.rect(p.x - handleSize / 2, p.y - handleSize / 2, handleSize, handleSize)
      ctx.fill()
      ctx.stroke()
      ctx.restore()
    }
    if (info.isImage && selection.length === 1) {
      const rot = positions['rot']
      ctx.save()
      ctx.strokeStyle = ACCENT
      ctx.lineWidth = line
      ctx.beginPath()
      ctx.moveTo(box.x + box.w / 2, box.y)
      ctx.lineTo(rot.x, rot.y)
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(rot.x, rot.y, handleSize / 1.6, 0, Math.PI * 2)
      ctx.fillStyle = '#ffffff'
      ctx.fill()
      ctx.stroke()
      ctx.restore()
    }
  }
}

// Main draw effect: re-runs whenever the document, time or view changes.
watchEffect(() => {
  const panel = canvas.value
  if (panel === null) return
  const ctx = panel.getContext('2d')
  if (ctx === null) return
  void zoom.value
  void state.time
  void redrawTick.value
  void state.selection
  void marquee.value
  void guides.value

  const width = panelWidth.value
  const height = panelHeight.value
  if (panel.width !== width || panel.height !== height) {
    panel.width = width
    panel.height = height
  }
  const doc = state.doc
  const background = (doc?.background ?? []) as readonly Record<string, unknown>[]
  const evaluated = evaluateEntries(expansion.value.entries, {
    time: state.time,
    maxFps: typeof doc?.max_fps === 'number' ? doc.max_fps : 20,
    provider,
  })
  lastEvaluated = evaluated
  drawScene({
    ctx,
    background,
    entries: evaluated,
    width,
    height,
    sceneId: state.sceneId,
    images,
    showGrid: true,
    gridPixelSize: 20,
  })
  drawOverlay(ctx, width, height)
})
</script>

<template>
  <div
    ref="container"
    class="viewport"
    :class="{ pan: spaceHeld }"
    :style="{ cursor: hoverCursor ?? (spaceHeld ? 'grab' : 'default') }"
    @wheel="onWheel"
    @pointerdown="onPointerdown"
    @pointermove="onPointermove"
    @pointerup="onPointerup"
    @pointercancel="onPointerup"
  >
    <div class="canvas-holder" :style="transformStyle">
      <canvas ref="canvas" class="scene-canvas"></canvas>
    </div>
    <div class="zoom-label">{{ Math.round(zoom * 100) }}%</div>
  </div>
</template>

<style scoped>
.viewport {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    repeating-conic-gradient(#1a1a1a 0% 25%, #151515 0% 50%) 0 0 / 24px 24px;
  touch-action: none;
}

.viewport.pan {
  cursor: grab;
}

.viewport.pan:active {
  cursor: grabbing;
}

.canvas-holder {
  position: relative;
  flex: none;
  box-shadow: 0 0 0 1px var(--border), 0 6px 30px rgba(0, 0, 0, 0.5);
}

.scene-canvas {
  display: block;
  width: 100%;
  height: 100%;
  image-rendering: pixelated;
}

.zoom-label {
  position: absolute;
  left: 10px;
  bottom: 8px;
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 8px;
  pointer-events: none;
}
</style>
