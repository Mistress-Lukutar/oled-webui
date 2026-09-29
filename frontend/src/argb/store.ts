/**
 * Singleton reactive store for the ARGB editor: draft layout, status,
 * selection, mask painting and live preview buffers.
 */

import { reactive, ref } from 'vue'
import { API } from '../api'
import {
  cloneLayout,
  defaultLayout,
  deviceTotalLeds,
  makeDevice,
  makeLayer,
} from './types'
import type {
  ArgbDevice,
  ArgbHeader,
  ArgbLayer,
  ArgbLayout,
  ArgbStatus,
  DeviceType,
  EffectType,
} from './types'

interface Selection {
  kind: 'device' | 'layer' | 'header' | null
  id: string | null
}

interface ArgbState {
  status: ArgbStatus
  layout: ArgbLayout
  loaded: boolean
  dirty: boolean
  /** Inspector focus (single item); devices on canvas sync into it. */
  selection: Selection
  /** Canvas multi-selection of device ids. */
  deviceSelection: string[]
  /** When set, canvas clicks paint this layer's pixel mask. */
  maskLayerId: string | null
  /** headerId -> packed RGB hex of the latest preview frame. */
  preview: Record<string, string>
  error: string | null
}

const EMPTY_STATUS: ArgbStatus = {
  connected: false,
  controller: null,
  zones: [],
  running: false,
  fps: 30,
  brightness: 100,
  autostart: false,
  frames_sent: 0,
}

const state = reactive<ArgbState>({
  status: { ...EMPTY_STATUS },
  layout: defaultLayout(),
  loaded: false,
  dirty: false,
  selection: { kind: null, id: null },
  deviceSelection: [],
  maskLayerId: null,
  preview: {},
  error: null,
})

let previewBusy = false

/**
 * Shared live-preview poller: every mounted consumer (tab preview, editor
 * canvas) holds one reference; the 66 ms interval runs while any exist.
 */
let previewTimer = 0
let previewRefCount = 0

function startPreviewPolling(): void {
  previewRefCount += 1
  if (previewTimer !== 0) return
  void actions.fetchPreview()
  previewTimer = window.setInterval(() => {
    void actions.fetchPreview()
  }, 66)
}

function stopPreviewPolling(): void {
  previewRefCount = Math.max(0, previewRefCount - 1)
  if (previewRefCount === 0 && previewTimer !== 0) {
    window.clearInterval(previewTimer)
    previewTimer = 0
  }
}

// ----------------------------------------------------------------------
// Undo/redo: JSON snapshots of the whole layout. Batches (drag/paint
// gestures) push exactly one snapshot via beginBatch()/endBatch().
// ----------------------------------------------------------------------

const MAX_HISTORY = 100
let undoStack: string[] = []
let redoStack: string[] = []
let batchDepth = 0
/** Bump whenever history contents change, for reactive canUndo/canRedo. */
const historyVersion = ref(0)

function pruneSelection(): void {
  const ids = new Set(state.layout.devices.map((item) => item.id))
  state.deviceSelection = state.deviceSelection.filter((id) => ids.has(id))
  if (
    state.selection.kind === 'device' &&
    (state.selection.id === null || !ids.has(state.selection.id))
  ) {
    state.selection = { kind: null, id: null }
  }
}

function pushHistory(): void {
  undoStack.push(JSON.stringify(state.layout))
  if (undoStack.length > MAX_HISTORY) undoStack.shift()
  redoStack = []
  historyVersion.value += 1
}

function restore(snapshotText: string): void {
  const doc = JSON.parse(snapshotText) as ArgbLayout
  for (const key of Object.keys(state.layout)) {
    delete (state.layout as Record<string, unknown>)[key]
  }
  Object.assign(state.layout, doc)
  pruneSelection()
  state.dirty = true
  historyVersion.value += 1
}

function beginBatch(): void {
  if (batchDepth === 0) pushHistory()
  batchDepth += 1
}

function endBatch(): void {
  batchDepth = Math.max(0, batchDepth - 1)
}

function undo(): void {
  if (undoStack.length === 0 || batchDepth > 0) return
  redoStack.push(JSON.stringify(state.layout))
  restore(undoStack.pop()!)
}

function redo(): void {
  if (redoStack.length === 0 || batchDepth > 0) return
  undoStack.push(JSON.stringify(state.layout))
  restore(redoStack.pop()!)
}

function canUndo(): boolean {
  void historyVersion.value
  return undoStack.length > 0
}

function canRedo(): boolean {
  void historyVersion.value
  return redoStack.length > 0
}

function showError(message: string): void {
  state.error = message
  window.setTimeout(() => {
    if (state.error === message) state.error = null
  }, 5000)
}

async function wrap(action: () => Promise<void>): Promise<boolean> {
  try {
    await action()
    return true
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
    return false
  }
}

/**
 * Every draft edit goes through here: apply fn, then mark dirty.
 * Standalone calls capture one history snapshot automatically; gesture
 * code wraps itself in beginBatch()/endBatch().
 */
function mutate(fn: (layout: ArgbLayout) => void): void {
  if (batchDepth === 0) pushHistory()
  fn(state.layout)
  state.dirty = true
}

function nextOrdinal(prefix: string): number {
  let count = 0
  for (const device of state.layout.devices) {
    if (device.name.startsWith(prefix)) count += 1
  }
  return count + 1
}

/** Internal device clipboard (editor-session scope), deep copies. */
let deviceClipboard: ArgbDevice[] = []

const actions = {
  async init(): Promise<void> {
    if (state.loaded) return
    await actions.refreshStatus()
    try {
      const { layout } = await API.getArgbLayout()
      state.layout = layout
    } catch {
      state.layout = defaultLayout()
    }
    state.dirty = false
    state.loaded = true
    undoStack = []
    redoStack = []
    batchDepth = 0
    historyVersion.value += 1
  },

  async refreshStatus(): Promise<void> {
    try {
      state.status = await API.getArgbStatus()
    } catch {
      // Keep the last known status; the panel shows a stale indicator.
    }
  },

  async fetchPreview(): Promise<void> {
    if (previewBusy) return
    previewBusy = true
    try {
      const { buffers } = await API.renderArgbPreview(state.layout)
      state.preview = buffers
    } catch {
      // Transient preview failure: keep the previous frame.
    } finally {
      previewBusy = false
    }
  },

  // -----------------------------------------------------------------
  // Engine and connection
  // -----------------------------------------------------------------

  async connect(): Promise<boolean> {
    return wrap(async () => {
      state.status = await API.connectArgb()
    })
  },

  async disconnect(): Promise<boolean> {
    return wrap(async () => {
      state.status = await API.disconnectArgb()
    })
  },

  async apply(): Promise<boolean> {
    return wrap(async () => {
      state.status = await API.applyArgb(cloneLayout(state.layout))
      state.dirty = false
    })
  },

  async save(): Promise<boolean> {
    return wrap(async () => {
      await API.saveArgbLayout(cloneLayout(state.layout))
      state.dirty = false
    })
  },

  async stop(): Promise<boolean> {
    return wrap(async () => {
      state.status = await API.stopArgb()
    })
  },

  async setAutostart(value: boolean): Promise<boolean> {
    mutate((layout) => {
      layout.autostart = value
    })
    return actions.save()
  },

  // -----------------------------------------------------------------
  // Devices (CRUD)
  // -----------------------------------------------------------------

  addDevice(type: DeviceType): void {
    const header = state.layout.headers[0]
    if (header === undefined) {
      showError('Create a header first')
      return
    }
    // Stagger spawn positions so consecutive devices do not overlap.
    const n = state.layout.devices.length
    const x = WORKSPACE_CENTER.x + ((n % 4) - 1.5) * 110
    const y = WORKSPACE_CENTER.y + (Math.floor(n / 4) % 3) * 80 - 80
    const device = makeDevice(
      type,
      header.id,
      x,
      y,
      nextOrdinal(type === 'strip' ? 'Strip' : 'Fan'),
    )
    mutate((layout) => {
      layout.devices.push(device)
      layout.headers[0].devices.push(device.id)
    })
    actions.select('device', device.id)
  },

  updateDevice(id: string, patch: Partial<ArgbDevice>): void {
    mutate((layout) => {
      const device = layout.devices.find((item) => item.id === id)
      if (device !== undefined) Object.assign(device, patch)
    })
  },

  deleteDevice(id: string): void {
    actions.deleteDevices([id])
  },

  deleteDevices(ids: string[]): void {
    if (ids.length === 0) return
    const doomed = new Set(ids)
    mutate((layout) => {
      layout.devices = layout.devices.filter((item) => !doomed.has(item.id))
      for (const header of layout.headers) {
        header.devices = header.devices.filter((item) => !doomed.has(item))
      }
      for (const layer of layout.layers) {
        for (const id of doomed) delete layer.mask.runs[id]
      }
    })
    if (state.selection.kind === 'device' && state.selection.id !== null && doomed.has(state.selection.id)) {
      state.selection = { kind: null, id: null }
    }
    state.deviceSelection = state.deviceSelection.filter((id) => !doomed.has(id))
  },

  duplicateDevice(id: string): void {
    actions.duplicateDevices([id])
  },

  duplicateDevices(ids: string[]): void {
    const sources = state.layout.devices.filter((item) => ids.includes(item.id))
    if (sources.length === 0) return
    const copies: ArgbDevice[] = sources.map((source, i) => ({
      ...cloneLayout({ ...state.layout, devices: [source] }).devices[0],
      id: `d_${crypto.randomUUID().slice(0, 8)}`,
      x: source.x + 40 + i * 12,
      y: source.y + 40 + i * 12,
      name: `${source.name} copy`,
    }))
    mutate((layout) => {
      for (const copy of copies) {
        layout.devices.push(copy)
        const header = layout.headers.find(
          (item) => item.id === copy.header_id,
        )
        const fallback = layout.headers[0]
        const target = header ?? fallback
        if (target !== undefined) {
          copy.header_id = target.id
          target.devices.push(copy.id)
        }
      }
    })
    actions.setDeviceSelection(copies.map((copy) => copy.id))
  },

  /** Move devices by a delta (canvas drag and arrow-key nudge). */
  moveDevicesBy(ids: string[], dx: number, dy: number): void {
    const moving = new Set(ids)
    mutate((layout) => {
      for (const device of layout.devices) {
        if (moving.has(device.id)) {
          device.x += dx
          device.y += dy
        }
      }
    })
  },

  /** Copy device ids into the internal clipboard (deep copies). */
  copyDevices(ids: string[]): void {
    const sources = state.layout.devices.filter((item) => ids.includes(item.id))
    if (sources.length === 0) return
    deviceClipboard = cloneLayout({ ...state.layout, devices: sources }).devices
  },

  /** Copy, then delete. */
  cutDevices(ids: string[]): void {
    actions.copyDevices(ids)
    actions.deleteDevices(ids)
  },

  /** Paste clipboard devices with fresh ids, offset and selected. */
  pasteDevices(): void {
    if (deviceClipboard.length === 0) return
    const copies: ArgbDevice[] = deviceClipboard.map((source, i) => ({
      ...source,
      id: `d_${crypto.randomUUID().slice(0, 8)}`,
      x: source.x + 24 + i * 12,
      y: source.y + 24 + i * 12,
    }))
    mutate((layout) => {
      for (const copy of copies) {
        layout.devices.push(copy)
        const header =
          layout.headers.find((item) => item.id === copy.header_id) ??
          layout.headers[0]
        if (header !== undefined) {
          copy.header_id = header.id
          header.devices.push(copy.id)
        }
      }
    })
    actions.setDeviceSelection(copies.map((copy) => copy.id))
  },

  /** Move a device within its header chain (direction: -1 or +1). */
  reorderDevice(id: string, direction: number): void {
    mutate((layout) => {
      const header = layout.headers.find((item) =>
        item.devices.includes(id),
      )
      if (header === undefined) return
      const index = header.devices.indexOf(id)
      const target = index + direction
      if (target < 0 || target >= header.devices.length) return
      header.devices.splice(index, 1)
      header.devices.splice(target, 0, id)
    })
  },

  assignDeviceToHeader(id: string, headerId: string): void {
    mutate((layout) => {
      const device = layout.devices.find((item) => item.id === id)
      if (device === undefined) return
      for (const header of layout.headers) {
        header.devices = header.devices.filter((item) => item !== id)
      }
      device.header_id = headerId
      const target = layout.headers.find((item) => item.id === headerId)
      if (target !== undefined) target.devices.push(id)
    })
  },

  // -----------------------------------------------------------------
  // Headers (CRUD)
  // -----------------------------------------------------------------

  addHeader(): void {
    const header: ArgbHeader = {
      id: `h_${crypto.randomUUID().slice(0, 8)}`,
      name: `ARGB ${state.layout.headers.length + 1}`,
      zone_index: state.layout.headers.length,
      size: null,
      devices: [],
    }
    mutate((layout) => {
      layout.headers.push(header)
    })
    actions.select('header', header.id)
  },

  updateHeader(id: string, patch: Partial<ArgbHeader>): void {
    mutate((layout) => {
      const header = layout.headers.find((item) => item.id === id)
      if (header !== undefined) Object.assign(header, patch)
    })
  },

  deleteHeader(id: string): void {
    const header = state.layout.headers.find((item) => item.id === id)
    if (header === undefined || header.devices.length > 0) {
      showError('Header is not empty')
      return
    }
    mutate((layout) => {
      layout.headers = layout.headers.filter((item) => item.id !== id)
    })
    if (state.selection.id === id) state.selection = { kind: null, id: null }
  },

  // -----------------------------------------------------------------
  // Layers (CRUD)
  // -----------------------------------------------------------------

  addLayer(type: EffectType): void {
    const layer = makeLayer(type, state.layout.layers.length + 1)
    mutate((layout) => {
      layout.layers.push(layer)
    })
    actions.select('layer', layer.id)
  },

  updateLayer(id: string, patch: Partial<ArgbLayer>): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === id)
      if (layer !== undefined) Object.assign(layer, patch)
    })
  },

  updateEffect(layerId: string, patch: Record<string, unknown>): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      if (layer !== undefined) {
        Object.assign(layer.effect, patch)
      }
    })
  },

  /** Replace a layer's effect type, keeping layer identity. */
  setEffectType(layerId: string, type: EffectType): void {
    const layer = state.layout.layers.find((item) => item.id === layerId)
    if (layer === undefined) return
    const fresh = makeLayer(type, 1)
    mutate((layout) => {
      const target = layout.layers.find((item) => item.id === layerId)
      if (target !== undefined) target.effect = fresh.effect
    })
  },

  deleteLayer(id: string): void {
    mutate((layout) => {
      layout.layers = layout.layers.filter((item) => item.id !== id)
    })
    if (state.maskLayerId === id) state.maskLayerId = null
    if (state.selection.id === id) state.selection = { kind: null, id: null }
  },

  reorderLayer(id: string, direction: number): void {
    mutate((layout) => {
      const index = layout.layers.findIndex((item) => item.id === id)
      const target = index + direction
      if (index < 0 || target < 0 || target >= layout.layers.length) return
      const [layer] = layout.layers.splice(index, 1)
      layout.layers.splice(target, 0, layer)
    })
  },

  /** Replace the whole draft layout (JSON view). One history snapshot. */
  replaceLayout(doc: ArgbLayout): void {
    mutate(() => {
      for (const key of Object.keys(state.layout)) {
        delete (state.layout as Record<string, unknown>)[key]
      }
      Object.assign(state.layout, doc)
    })
    pruneSelection()
    if (
      state.maskLayerId !== null &&
      !state.layout.layers.some((item) => item.id === state.maskLayerId)
    ) {
      state.maskLayerId = null
    }
    if (state.selection.kind === 'layer' || state.selection.kind === 'header') {
      const pool =
        state.selection.kind === 'layer'
          ? state.layout.layers
          : state.layout.headers
      if (!pool.some((item) => item.id === state.selection.id)) {
        state.selection = { kind: null, id: null }
      }
    }
  },

  select(kind: Selection['kind'], id: string | null): void {
    if (kind === 'device' && id !== null) {
      state.deviceSelection = [id]
    } else {
      state.deviceSelection = []
    }
    state.selection = { kind, id }
  },

  /** Canvas multi-selection: focus follows the last id. */
  setDeviceSelection(ids: string[]): void {
    const unique = [...new Set(ids)]
    state.deviceSelection = unique
    const focus = unique[unique.length - 1] ?? null
    state.selection = {
      kind: focus !== null ? 'device' : null,
      id: focus,
    }
  },

  // -----------------------------------------------------------------
  // Mask editing
  // -----------------------------------------------------------------

  startMaskPaint(layerId: string): void {
    state.maskLayerId = layerId
  },

  stopMaskPaint(): void {
    state.maskLayerId = null
  },

  maskSetAll(layerId: string, all: boolean): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      if (layer === undefined) return
      layer.mask.all = all
      if (all) layer.mask.runs = {}
    })
  },

  /** Reset a custom mask to cover every pixel of every device. */
  maskFillAll(layerId: string): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      if (layer === undefined) return
      const runs: Record<string, [number, number][]> = {}
      for (const device of layout.devices) {
        runs[device.id] = [[0, deviceTotalLeds(device) - 1]]
      }
      layer.mask.all = false
      layer.mask.runs = runs
    })
  },

  maskClear(layerId: string): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      if (layer === undefined) return
      layer.mask.all = false
      layer.mask.runs = {}
    })
  },

  maskInvert(layerId: string): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      if (layer === undefined) return
      const runs: Record<string, [number, number][]> = {}
      for (const device of layout.devices) {
        const total = deviceTotalLeds(device)
        const covered = new Array<boolean>(total).fill(false)
        for (const [start, end] of layer.mask.runs[device.id] ?? []) {
          for (let i = start; i <= Math.min(end, total - 1); i += 1) {
            covered[i] = true
          }
        }
        const inverted: [number, number][] = []
        let runStart: number | null = null
        for (let i = 0; i < total; i += 1) {
          if (!covered[i] && runStart === null) runStart = i
          if (covered[i] && runStart !== null) {
            inverted.push([runStart, i - 1])
            runStart = null
          }
        }
        if (runStart !== null) inverted.push([runStart, total - 1])
        if (inverted.length > 0) runs[device.id] = inverted
      }
      layer.mask.all = false
      layer.mask.runs = runs
    })
  },

  /** Include/exclude one LED in a layer mask (paint mode). */
  maskSetPixel(
    layerId: string,
    deviceId: string,
    index: number,
    include: boolean,
  ): void {
    mutate((layout) => {
      const layer = layout.layers.find((item) => item.id === layerId)
      const device = layout.devices.find((item) => item.id === deviceId)
      if (layer === undefined || device === undefined) return
      const total = deviceTotalLeds(device)
      const covered = new Array<boolean>(total).fill(false)
      for (const [start, end] of layer.mask.runs[deviceId] ?? []) {
        for (let i = start; i <= Math.min(end, total - 1); i += 1) {
          covered[i] = true
        }
      }
      covered[index] = include
      const runs: [number, number][] = []
      let runStart: number | null = null
      for (let i = 0; i < total; i += 1) {
        if (covered[i] && runStart === null) runStart = i
        if (!covered[i] && runStart !== null) {
          runs.push([runStart, i - 1])
          runStart = null
        }
      }
      if (runStart !== null) runs.push([runStart, total - 1])
      layer.mask.all = false
      if (runs.length > 0) layer.mask.runs[deviceId] = runs
      else delete layer.mask.runs[deviceId]
    })
  },
}

const WORKSPACE_CENTER = { x: 400, y: 250 }

/** Chain LED usage for a header: used count and capacity (may be null). */
function headerUsage(header: ArgbHeader): { used: number; capacity: number | null } {
  let used = 0
  for (const id of header.devices) {
    const device = state.layout.devices.find((item) => item.id === id)
    if (device !== undefined) used += deviceTotalLeds(device)
  }
  return { used, capacity: header.size }
}

/** Pixels of a device covered by a layer mask (empty = none). */
function maskCoverage(layer: ArgbLayer | undefined, deviceId: string): boolean[] | null {
  if (layer === undefined || layer.mask.all) return null
  const device = state.layout.devices.find((item) => item.id === deviceId)
  if (device === undefined) return null
  const total = deviceTotalLeds(device)
  const covered = new Array<boolean>(total).fill(false)
  for (const [start, end] of layer.mask.runs[deviceId] ?? []) {
    for (let i = start; i <= Math.min(end, total - 1); i += 1) covered[i] = true
  }
  return covered
}

export function useArgbStore() {
  return {
    // Plain reactive state (same convention as the scene editor docStore):
    // components read it freely but only mutate through `actions`/`mutate`.
    state,
    actions,
    mutate,
    showError,
    headerUsage,
    maskCoverage,
    beginBatch,
    endBatch,
    startPreviewPolling,
    stopPreviewPolling,
    undo,
    redo,
    canUndo,
    canRedo,
  }
}
