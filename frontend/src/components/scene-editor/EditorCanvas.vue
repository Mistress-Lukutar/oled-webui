<script setup lang="ts">
/**
 * Scene viewport on the shared CanvasStage: evaluates and renders the
 * document (Pillow-approximating drawScene) and adapts scene widgets to
 * stage boxes. Component instances behave as locked groups (moved via
 * `at`); the stage owns zoom/pan, selection and all interactions.
 */
import { computed, ref, watch, watchEffect } from 'vue'
import CanvasStage from '../canvas/CanvasStage.vue'
import { snapBox, unionBox } from '../../canvas/geometry'
import { SNAP_THRESHOLD } from '../../canvas/stage'
import type { StageAdapter, StageBox } from '../../canvas/stage'
import type { WidgetBox } from '../../canvas/geometry'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { expandDocument } from '../../scene-editor/expand'
import { evaluateEntries, makePlaceholderProvider } from '../../scene-editor/runtime'
import type { EvalEntry } from '../../scene-editor/runtime'
import { createImageCache, createVideoCache, drawScene } from '../../scene-editor/render/draw'
import { ensureFont } from '../../scene-editor/render/fonts'
import { isComponentInstance } from '../../scene-editor/types'
import type { EntryRaw, SceneDocumentRaw, ShapeKind } from '../../scene-editor/types'
import { viewState } from '../../scene-editor/viewState'

const props = defineProps<{ drawShape?: ShapeKind | null }>()

const { state: appState } = useDisplayStore()
const { state } = editor

const stage = ref<InstanceType<typeof CanvasStage> | null>(null)
const redrawTick = ref(0)

const provider = makePlaceholderProvider()
const images = createImageCache(() => {
  redrawTick.value += 1
})
const videos = createVideoCache(() => {
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
  locked: boolean
}

/** Evaluated entries from the last frame, reused for hit-testing. */
let lastEvaluated: EvalEntry[] = []

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
      locked: entry['locked'] === true,
    })
  })
  return result
})

// ----------------------------------------------------------------------
// Raw document mutation helpers
// ----------------------------------------------------------------------

function rawEntry(index: number): EntryRaw | null {
  const widgets = state.doc?.widgets
  const entry = widgets?.[index]
  return entry === undefined ? null : (entry as EntryRaw)
}

/** Raw widget rotation in degrees (expressions count as 0 for interaction). */
function widgetRotation(sourceIndex: number): number {
  const value = rawEntry(sourceIndex)?.['rotation']
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

interface DragOrigin {
  /** Raw rect top-left at drag start (plain widgets). */
  rectX: number
  rectY: number
  /** Instance `at` at drag start, null for plain widgets. */
  at: [number, number] | null
}

const dragOrigins = new Map<number, DragOrigin>()

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

// ----------------------------------------------------------------------
// Draw-shape tool: dragging on the canvas creates a shape widget with
// the dragged box. Uses the stage's custom-gesture hooks, so the tool
// takes precedence over selection/marquee while armed.
// ----------------------------------------------------------------------

const ghostRect = ref<WidgetBox | null>(null)
let drawStart: { x: number; y: number } | null = null

function normalizedRect(
  start: { x: number; y: number },
  current: { x: number; y: number },
  square: boolean,
): WidgetBox {
  let w = current.x - start.x
  let h = current.y - start.y
  if (square) {
    const size = Math.max(Math.abs(w), Math.abs(h))
    w = Math.sign(w) * size
    h = Math.sign(h) * size
  }
  return {
    x: Math.min(start.x, start.x + w),
    y: Math.min(start.y, start.y + h),
    w: Math.abs(w),
    h: Math.abs(h),
  }
}

function snapGhost(box: WidgetBox): WidgetBox {
  const snapped = snapBox(
    box,
    boxes.value.map((info) => info.box),
    panelWidth.value,
    panelHeight.value,
    SNAP_THRESHOLD / Math.max(0.05, viewState.zoom),
  )
  return { ...box, x: snapped.x, y: snapped.y }
}

// ----------------------------------------------------------------------
// Stage adapter
// ----------------------------------------------------------------------

const adapter: StageAdapter = {
  getBoxes(): StageBox[] {
    return boxes.value.map((info) => ({
      id: String(info.sourceIndex),
      box: info.box,
      rotation: widgetRotation(info.sourceIndex),
      hitRotation: info.isInstance ? 0 : widgetRotation(info.sourceIndex),
      locked: info.locked,
      handleless: info.isInstance,
    }))
  },

  getSelection(): string[] {
    return state.selection.map(String)
  },

  setSelection(ids: string[]): void {
    editor.setSelection(ids.map(Number))
  },

  dragStart(ids: string[]): void {
    dragOrigins.clear()
    for (const id of ids) {
      const sourceIndex = Number(id)
      const raw = rawEntry(sourceIndex)
      let at: [number, number] | null = null
      let rectX = 0
      let rectY = 0
      const info = boxes.value.find((b) => b.sourceIndex === sourceIndex)
      if (info !== undefined) {
        rectX = info.box.x
        rectY = info.box.y
      }
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
      dragOrigins.set(sourceIndex, { rectX, rectY, at })
    }
  },

  moveBy(ids: string[], dx: number, dy: number): void {
    for (const id of ids) {
      const origin = dragOrigins.get(Number(id))
      if (origin !== undefined) moveRawBy(Number(id), dx, dy, origin)
    }
  },

  resizeTo(id: string, box: WidgetBox): void {
    const sourceIndex = Number(id)
    editor.mutate((doc) => {
      const entry = doc.widgets?.[sourceIndex] as Record<string, unknown> | undefined
      if (entry === undefined || isComponentInstance(entry as EntryRaw)) return
      entry['rect'] = [
        Math.round(box.x),
        Math.round(box.y),
        Math.max(1, Math.round(box.w)),
        Math.max(1, Math.round(box.h)),
      ]
    })
  },

  rotateTo(id: string, degrees: number): void {
    editor.mutate((doc) => {
      const entry = doc.widgets?.[Number(id)] as Record<string, unknown> | undefined
      if (entry === undefined) return
      entry['rotation'] = Math.round(degrees * 10) / 10
    })
  },

  beginBatch(): void {
    editor.beginBatch()
  },

  endBatch(): void {
    editor.endBatch()
  },

  pointerDown(x: number, y: number): boolean {
    if (props.drawShape === null || props.drawShape === undefined) return false
    drawStart = { x, y }
    ghostRect.value = null
    editor.setSelection([])
    return true
  },

  pointerMove(x: number, y: number, event: PointerEvent): void {
    if (drawStart === null || props.drawShape === null || props.drawShape === undefined) return
    const box = normalizedRect(drawStart, { x, y }, event.shiftKey)
    ghostRect.value = box.w >= 1 || box.h >= 1 ? snapGhost(box) : box
  },

  pointerUp(x: number, y: number, event: PointerEvent): void {
    if (drawStart === null || props.drawShape === null || props.drawShape === undefined) return
    const kind = props.drawShape
    const box = snapGhost(normalizedRect(drawStart, { x, y }, event.shiftKey))
    drawStart = null
    ghostRect.value = null
    if (box.w >= 1 && box.h >= 1) {
      editor.addWidgetRect('shape', [box.x, box.y, Math.round(box.w), Math.round(box.h)], {
        shape: kind,
      })
    }
  },
}

// Publish the view state for other panels (widget insertion).
watchEffect(() => {
  const view = stage.value
  if (view === null) return
  viewState.zoom = view.zoom
  viewState.panX = view.panX
  viewState.panY = view.panY
})

watch(
  () => state.sceneId,
  () => {
    stage.value?.fit()
  },
)

function drawContent(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
): void {
  void redrawTick.value
  void state.time
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
    videos,
    time: state.time,
    showGrid: true,
    gridPixelSize: 20,
  })
  // In-progress shape ghost: dashed outline plus translucent fill.
  const ghost = ghostRect.value
  if (ghost !== null && ghost.w >= 1 && ghost.h >= 1) {
    ctx.save()
    ctx.globalAlpha = 0.35
    ctx.fillStyle = '#35c98e'
    ctx.fillRect(ghost.x, ghost.y, ghost.w, ghost.h)
    ctx.globalAlpha = 1
    ctx.strokeStyle = '#35c98e'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 3])
    ctx.strokeRect(ghost.x + 0.5, ghost.y + 0.5, ghost.w, ghost.h)
    ctx.restore()
  }
}
</script>

<template>
  <CanvasStage
    ref="stage"
    :width="panelWidth"
    :height="panelHeight"
    :adapter="adapter"
    :draw-content="drawContent"
    pixelated
  />
</template>
