/**
 * Singleton reactive store for the ARGB tooling: connection status,
 * device library, selection, mask painting and live preview buffers.
 *
 * The working layout (``state.layout``) is a projection: inside the
 * scene editor it aliases the scene file's ``argb`` section (bind via
 * :func:`bindSceneSection`), everywhere else it mirrors the active
 * engine layout from the server (refreshActiveLayout). Layout mutations
 * always funnel through the scene editor store so YAML text, validation
 * and undo stay in sync; outside the editor nothing mutates.
 */

import { reactive } from 'vue'
import { API } from '../api'
import { editor } from '../scene-editor/docStore'
import {
  cloneLayout,
  defaultLayout,
  makeDevice,
  makeLayer,
} from './types'
import type {
  ArgbDevice,
  ArgbHeader,
  ArgbLayer,
  ArgbLayout,
  ArgbSettings,
  ArgbStatus,
  DeviceDefinition,
  DeviceSummary,
  EffectType,
} from './types'

interface Selection {
  kind: 'device' | 'layer' | 'header' | null
  id: string | null
}

interface ArgbState {
  status: ArgbStatus
  /** Persisted ARGB settings (display-power behaviour). */
  settings: ArgbSettings
  layout: ArgbLayout
  /** True while layout aliases the scene file's argb section. */
  bound: boolean
  loaded: boolean
  dirty: boolean
  /** Installed device definitions (library summaries with full shapes). */
  library: DeviceSummary[]
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
  frames_sent: 0,
  process: null,
}

const state = reactive<ArgbState>({
  status: { ...EMPTY_STATUS },
  settings: { off_on_display_off: false },
  layout: defaultLayout(),
  bound: false,
  loaded: false,
  dirty: false,
  library: [],
  selection: { kind: null, id: null },
  deviceSelection: [],
  maskLayerId: null,
  preview: {},
  error: null,
})

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Resolve the definition a device instance references. */
function definitionOf(device: ArgbDevice): DeviceDefinition | undefined {
  return state.library.find((item) => item.id === device.device)?.definition
}

/** LED count of a device instance (0 when its definition is missing). */
function deviceLeds(device: ArgbDevice): number {
  return definitionOf(device)?.leds.length ?? 0
}

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

function pruneSelection(): void {
  const ids = new Set(state.layout.devices.map((item) => item.id))
  state.deviceSelection = state.deviceSelection.filter((id) => ids.has(id))
  if (
    state.selection.kind === 'device' &&
    (state.selection.id === null || !ids.has(state.selection.id))
  ) {
    state.selection = { kind: null, id: null }
  }
  if (
    state.selection.kind !== null &&
    state.selection.id !== null &&
    !poolFor(state.selection.kind).some((item) => item.id === state.selection.id)
  ) {
    state.selection = { kind: null, id: null }
  }
}

function poolFor(kind: Selection['kind']): Array<{ id: string }> {
  if (kind === 'device') return state.layout.devices
  if (kind === 'header') return state.layout.headers
  if (kind === 'layer') return state.layout.layers
  return []
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
 * Every draft edit goes through here: the mutation is applied to the
 * scene file's argb section by the editor store, which snapshots undo
 * history and regenerates the YAML text. Outside the editor (no scene
 * file) mutations are dropped: the working layout is read-only there.
 */
function mutate(fn: (layout: ArgbLayout) => void): void {
  editor.mutateSection(
    'argb',
    fn as unknown as (section: Record<string, unknown>) => void,
  )
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
    await actions.refreshSettings()
    await actions.loadLibrary()
    await actions.refreshActiveLayout()
    state.loaded = true
  },

  async refreshStatus(): Promise<void> {
    try {
      state.status = await API.getArgbStatus()
    } catch {
      // Keep the last known status; the panel shows a stale indicator.
    }
  },

  async refreshSettings(): Promise<void> {
    try {
      state.settings = await API.getArgbSettings()
    } catch {
      // Keep the last known settings.
    }
  },

  async setSettings(patch: Partial<ArgbSettings>): Promise<void> {
    state.settings = { ...state.settings, ...patch }
    try {
      state.settings = await API.setArgbSettings(patch)
    } catch (err) {
      showError(err instanceof Error ? err.message : String(err))
      void actions.refreshSettings()
    }
  },

  async loadLibrary(): Promise<void> {
    try {
      const { devices } = await API.listArgbDevices()
      state.library = devices
    } catch {
      // Keep the last known library; the picker will retry on demand.
    }
  },

  /**
   * Alias the working layout to the scene editor's argb section. Called
   * by the editor whenever its document (re)loads; a scene without an
   * argb section binds a detached default so the tab can offer
   * "+ Add section" without touching the file.
   */
  bindSceneSection(): void {
    const file = editor.getRawFile()
    const section = file !== null && isObject(file['argb']) ? file['argb'] : null
    if (section !== null) {
      state.layout = section as unknown as ArgbLayout
      state.bound = true
    } else {
      state.layout = defaultLayout()
      state.bound = false
    }
    state.dirty = false
    pruneSelection()
  },

  /** Drop the editor binding and mirror the active engine layout. */
  async refreshActiveLayout(): Promise<void> {
    state.bound = false
    try {
      const { layout } = await API.getActiveArgbLayout()
      state.layout = cloneLayout(layout)
    } catch {
      state.layout = defaultLayout()
    }
    state.dirty = false
    pruneSelection()
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

  // -----------------------------------------------------------------
  // Devices (CRUD)
  // -----------------------------------------------------------------

  addDevice(definitionId: string): void {
    const header = state.layout.headers[0]
    if (header === undefined) {
      showError('Create a header first')
      return
    }
    const summary = state.library.find((item) => item.id === definitionId)
    if (summary === undefined) {
      showError('Unknown device definition')
      return
    }
    // Stagger spawn positions so consecutive devices do not overlap.
    const n = state.layout.devices.length
    const x = WORKSPACE_CENTER.x + ((n % 4) - 1.5) * 110
    const y = WORKSPACE_CENTER.y + (Math.floor(n / 4) % 3) * 80 - 80
    const device = makeDevice(
      summary.definition,
      header.id,
      x,
      y,
      nextOrdinal(summary.definition.name || definitionId),
    )
    mutate((layout) => {
      layout.devices.push(device)
      layout.headers[0]?.devices.push(device.id)
    })
    actions.select('device', device.id)
  },

  /** Point an existing instance at another definition, clamping masks. */
  changeDeviceDefinition(id: string, definitionId: string): void {
    mutate((layout) => {
      const device = layout.devices.find((item) => item.id === id)
      if (device === undefined) return
      device.device = definitionId
      const leds =
        state.library.find((item) => item.id === definitionId)?.definition
          .leds.length ?? 0
      if (leds > 0) {
        for (const layer of layout.layers) {
          const runs = layer.mask.runs[id]
          if (runs === undefined) continue
          const clamped: [number, number][] = []
          for (const [start, end] of runs) {
            if (start > leds - 1) continue
            clamped.push([start, Math.min(end, leds - 1)])
          }
          if (clamped.length > 0) layer.mask.runs[id] = clamped
          else delete layer.mask.runs[id]
        }
      }
    })
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
  // Device definition library (YAML sources on the server)
  // -----------------------------------------------------------------

  async createDeviceDefinition(yamlText: string): Promise<boolean> {
    const ok = await wrap(async () => {
      await API.createArgbDevice(yamlText)
      await actions.loadLibrary()
    })
    return ok
  },

  async updateDeviceDefinition(id: string, yamlText: string): Promise<boolean> {
    return wrap(async () => {
      await API.updateArgbDevice(id, yamlText)
      await actions.loadLibrary()
    })
  },

  async deleteDeviceDefinition(id: string): Promise<boolean> {
    return wrap(async () => {
      await API.deleteArgbDevice(id)
      await actions.loadLibrary()
    })
  },

  /** Duplicate a definition under a fresh id with " copy" name. */
  async duplicateDeviceDefinition(id: string): Promise<boolean> {
    return wrap(async () => {
      const { yaml } = await API.getArgbDevice(id)
      const existing = new Set(state.library.map((item) => item.id))
      let base = `${id}-copy`
      let candidate = base
      let n = 2
      while (existing.has(candidate)) {
        candidate = `${base}-${n}`
        n += 1
      }
      base = candidate
      const nameMatch = yaml.match(/^name:\s*(.*)$/m)
      const body = yaml.replace(
        /^id:\s*.*$/m,
        `id: ${base}`,
      )
      const text = nameMatch
        ? body.replace(/^name:\s*.*$/m, `name: ${nameMatch[1]} copy`)
        : body
      await API.createArgbDevice(text)
      await actions.loadLibrary()
    })
  },

  // -----------------------------------------------------------------
  // Headers (CRUD)
  // -----------------------------------------------------------------

  /**
   * Create a channel, optionally bound to an OpenRGB zone index. The
   * zone's reported capacity is adopted only when it actually has LEDs;
   * ITE-style zones report 0 until resized.
   */
  addHeader(zoneIndex?: number): void {
    const zone =
      zoneIndex === undefined
        ? undefined
        : state.status.zones.find((item) => item.index === zoneIndex)
    const header: ArgbHeader = {
      id: `h_${crypto.randomUUID().slice(0, 8)}`,
      name: `ARGB ${state.layout.headers.length + 1}`,
      zone_index: zoneIndex ?? state.layout.headers.length,
      size: zone !== undefined && zone.leds > 0 ? zone.leds : null,
      devices: [],
    }
    mutate((layout) => {
      layout.headers.push(header)
    })
    actions.select('header', header.id)
  },

  /** Move a header within the channel stack (signed shift in positions). */
  reorderHeader(id: string, delta: number): void {
    mutate((layout) => {
      const index = layout.headers.findIndex((item) => item.id === id)
      const target = index + delta
      if (index < 0 || target < 0 || target >= layout.headers.length) return
      const [header] = layout.headers.splice(index, 1)
      layout.headers.splice(target, 0, header)
    })
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
        runs[device.id] = [[0, deviceLeds(device) - 1]]
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
        const total = deviceLeds(device)
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
      const total = deviceLeds(device)
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
    if (device !== undefined) used += deviceLeds(device)
  }
  return { used, capacity: header.size }
}

/** Pixels of a device covered by a layer mask (empty = none). */
function maskCoverage(layer: ArgbLayer | undefined, deviceId: string): boolean[] | null {
  if (layer === undefined || layer.mask.all) return null
  const device = state.layout.devices.find((item) => item.id === deviceId)
  if (device === undefined) return null
  const total = deviceLeds(device)
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
    definitionOf,
    deviceLeds,
    beginBatch: editor.beginBatch,
    endBatch: editor.endBatch,
    startPreviewPolling,
    stopPreviewPolling,
    undo: editor.undo,
    redo: editor.redo,
    canUndo: editor.canUndo,
    canRedo: editor.canRedo,
  }
}
