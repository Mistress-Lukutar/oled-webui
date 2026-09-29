<script setup lang="ts">
/**
 * ARGB workspace on the shared CanvasStage: device boxes with live LED
 * colors, multi-select/drag/resize/rotate with smart snapping, and mask
 * painting mode (stage interactions yield via the pointerDown hook).
 */
import { onBeforeUnmount, onMounted } from 'vue'
import CanvasStage from '../canvas/CanvasStage.vue'
import type { WidgetBox } from '../../canvas/geometry'
import type { StageAdapter, StageBox } from '../../canvas/stage'
import { useKeydown } from '../../canvas/shortcuts'
import {
  deviceBox,
  drawWorkspace,
  hitCell,
  layoutGeometry,
} from '../../argb/render'
import type { Cell, DeviceGeometry } from '../../argb/render'
import { WORKSPACE_HEIGHT, WORKSPACE_WIDTH } from '../../argb/types'
import type { DeviceDefinition } from '../../argb/types'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

/** Definition lookup for geometry and drawing. */
function defsMap(): Map<string, DeviceDefinition> {
  return new Map(state.library.map((item) => [item.id, item.definition]))
}

// Workspace geometry from the last drawn frame, reused for hit-testing.
let geometry: Map<string, DeviceGeometry> = new Map()
let allCells: Cell[] = []

// Gesture base: box, scale and position at gesture start. The stage
// passes absolute deltas from the start point, so both move and the
// uniform-scale mapping of resize are computed against this snapshot.
const baseBoxes = new Map<
  string,
  { box: WidgetBox; scale: number; x: number; y: number }
>()

let paint: { mode: 'add' | 'remove' } | null = null

function clampScale(value: number): number {
  return Math.min(5, Math.max(0.2, value))
}

/** Snapshot a device as the base for the active gesture (once). */
function ensureBase(id: string): void {
  if (baseBoxes.has(id)) return
  const geo = geometry.get(id)
  const device = state.layout.devices.find((item) => item.id === id)
  if (geo !== undefined && device !== undefined) {
    baseBoxes.set(id, {
      box: deviceBox(geo),
      scale: device.scale,
      x: device.x,
      y: device.y,
    })
  }
}

// ----------------------------------------------------------------------
// Stage adapter: devices as boxes
// ----------------------------------------------------------------------

const adapter: StageAdapter = {
  getBoxes(): StageBox[] {
    return state.layout.devices.flatMap((device) => {
      const geo = geometry.get(device.id)
      if (geo === undefined) return []
      return [
        {
          id: device.id,
          box: deviceBox(geo),
          rotation: device.rotation,
          locked: false,
        },
      ]
    })
  },

  getSelection(): string[] {
    return state.deviceSelection
  },

  setSelection(ids: string[]): void {
    store.actions.setDeviceSelection(ids)
  },

  dragStart(ids: string[]): void {
    baseBoxes.clear()
    for (const id of ids) ensureBase(id)
  },

  moveBy(ids: string[], dx: number, dy: number): void {
    // dx/dy are absolute from the drag start, so place each device at
    // its snapshotted origin plus the delta (not incrementally).
    for (const id of ids) {
      const base = baseBoxes.get(id)
      if (base !== undefined) {
        store.actions.updateDevice(id, { x: base.x + dx, y: base.y + dy })
      }
    }
  },

  resizeTo(id: string, box: WidgetBox): void {
    // Devices scale uniformly: map the resized width back onto `scale`,
    // keeping the device center anchored.
    ensureBase(id)
    const device = state.layout.devices.find((item) => item.id === id)
    const base = baseBoxes.get(id)
    if (device === undefined || base === undefined || base.box.w <= 0) return
    const scale = clampScale(base.scale * (box.w / base.box.w))
    const rounded = Math.round(scale * 100) / 100
    if (rounded !== device.scale) {
      store.actions.updateDevice(id, { scale: rounded })
    }
  },

  rotateTo(id: string, degrees: number): void {
    store.actions.updateDevice(id, { rotation: Math.round(degrees * 10) / 10 })
  },

  beginBatch(): void {
    store.beginBatch()
  },

  endBatch(): void {
    store.endBatch()
  },

  // Mask painting: takes over the pointer gesture entirely.
  pointerDown(x: number, y: number): boolean {
    if (state.maskLayerId === null) return false
    const cell = hitCell(allCells, x, y)
    if (cell !== null) {
      const layer = state.layout.layers.find(
        (item) => item.id === state.maskLayerId,
      )
      const covered =
        store.maskCoverage(layer, cell.deviceId)?.[cell.index] ?? false
      paint = { mode: covered ? 'remove' : 'add' }
      store.beginBatch()
      applyPaint(cell)
    }
    return true
  },

  pointerMove(x: number, y: number): void {
    if (paint === null) return
    const cell = hitCell(allCells, x, y)
    if (cell !== null) applyPaint(cell)
  },

  pointerUp(): void {
    if (paint !== null) {
      store.endBatch()
      paint = null
    }
  },
}

function applyPaint(cell: Cell): void {
  if (state.maskLayerId === null || paint === null) return
  store.actions.maskSetPixel(
    state.maskLayerId,
    cell.deviceId,
    cell.index,
    paint.mode === 'add',
  )
}

// ----------------------------------------------------------------------
// Drawing: devices with live colors (selection frames come from the
// stage overlay).
// ----------------------------------------------------------------------

function drawContent(ctx: CanvasRenderingContext2D): void {
  const defs = defsMap()
  const geo = layoutGeometry(state.layout, defs)
  geometry = geo.byDevice
  allCells = [...geo.byDevice.values()].flatMap((item) => item.cells)

  const layer =
    state.maskLayerId !== null
      ? state.layout.layers.find((item) => item.id === state.maskLayerId)
      : undefined
  const coverage =
    layer !== undefined
      ? (deviceId: string, index: number): boolean =>
          store.maskCoverage(layer, deviceId)?.[index] ?? false
      : null

  drawWorkspace(ctx, state.layout, defs, {
    preview: state.preview,
    maskCoverage: state.maskLayerId !== null ? coverage : null,
  })
}

// ----------------------------------------------------------------------
// Keyboard: editor-wide shortcuts (layout independent, event.code).
// Escape and Ctrl+S are owned by the designer modal.
// ----------------------------------------------------------------------

function deleteSelection(): void {
  if (state.deviceSelection.length > 0) {
    store.actions.deleteDevices([...state.deviceSelection])
    return
  }
  const { kind, id } = state.selection
  if (kind === 'layer' && id !== null) store.actions.deleteLayer(id)
  if (kind === 'device' && id !== null) store.actions.deleteDevice(id)
}

function nudge(dx: number, dy: number): void {
  if (state.deviceSelection.length === 0) return
  store.actions.moveDevicesBy([...state.deviceSelection], dx, dy)
}

const detachShortcuts = useKeydown([
  { key: 'Delete', handler: deleteSelection },
  { key: 'Backspace', handler: deleteSelection },
  {
    code: 'KeyC',
    ctrl: true,
    handler: () => store.actions.copyDevices([...state.deviceSelection]),
  },
  {
    code: 'KeyX',
    ctrl: true,
    handler: () => store.actions.cutDevices([...state.deviceSelection]),
  },
  { code: 'KeyV', ctrl: true, handler: () => store.actions.pasteDevices() },
  {
    code: 'KeyD',
    ctrl: true,
    handler: () => store.actions.duplicateDevices([...state.deviceSelection]),
  },
  { code: 'KeyZ', ctrl: true, shift: false, handler: () => store.undo() },
  { code: 'KeyZ', ctrl: true, shift: true, handler: () => store.redo() },
  { code: 'KeyY', ctrl: true, handler: () => store.redo() },
  { key: 'ArrowLeft', ignoreShift: true, handler: (e) => nudge(e.shiftKey ? -10 : -1, 0) },
  { key: 'ArrowRight', ignoreShift: true, handler: (e) => nudge(e.shiftKey ? 10 : 1, 0) },
  { key: 'ArrowUp', ignoreShift: true, handler: (e) => nudge(0, e.shiftKey ? -10 : -1) },
  { key: 'ArrowDown', ignoreShift: true, handler: (e) => nudge(0, e.shiftKey ? 10 : 1) },
])

onMounted(() => {
  store.startPreviewPolling()
})

onBeforeUnmount(() => {
  store.stopPreviewPolling()
  detachShortcuts()
})
</script>

<template>
  <div class="canvas-wrap">
    <CanvasStage
      :width="WORKSPACE_WIDTH"
      :height="WORKSPACE_HEIGHT"
      :adapter="adapter"
      :draw-content="drawContent"
    />
    <div v-if="state.maskLayerId !== null" class="mask-hint">
      <span>Painting mask: drag over LEDs — the first cell picks add vs remove.</span>
      <button @click="store.actions.stopMaskPaint()">Done</button>
    </div>
  </div>
</template>

<style scoped>
.canvas-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.mask-hint {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: var(--bg-panel);
  border: 1px solid var(--accent-dim);
  border-radius: var(--radius);
  font-size: 12px;
  color: var(--text-dim);
}
</style>
