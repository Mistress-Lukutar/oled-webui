/**
 * Singleton reactive store: dashboard panel layout, device registry,
 * add/remove/reorder actions with server-side persistence.
 */

import { computed, reactive, readonly } from 'vue'
import { API } from '../api'
import { PANEL_DEFS, isPanelType } from '../panels/registry'
import type { PanelType } from '../panels/registry'

interface PanelsState {
  devices: Awaited<ReturnType<typeof API.getSystemDevices>>['devices']
  panels: Array<{ id: string; type: PanelType; device: string | null; aspect: number }>
  loaded: boolean
}

const state = reactive<PanelsState>({
  devices: [],
  panels: [],
  loaded: false,
})

/** One entry of the "+ panel" menu: a placeable panel instance. */
export interface AvailablePanel {
  type: PanelType
  title: string
  device: string | null
  deviceName: string | null
}

// Coalesce bursts of layout edits (drag reorder) into
// trailing saves instead of one request per mutation.
let saveTimer = 0
function persist(): void {
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    void API.savePanelLayout({ version: 1, panels: state.panels.map((p) => ({ ...p })) })
  }, 300)
}

export function usePanelsStore() {
  const deviceById = computed(() => {
    const map = new Map<string, (typeof state.devices)[number]>()
    for (const device of state.devices) map.set(device.id, device)
    return (id: string | null) => (id === null ? null : map.get(id) ?? null)
  })

  const availablePanels = computed<AvailablePanel[]>(() => {
    const result: AvailablePanel[] = []
    for (const entry of Object.entries(PANEL_DEFS) as [PanelType, (typeof PANEL_DEFS)[PanelType]][]) {
      const [type, def] = entry
      if (def.deviceKind === null) {
        if (!state.panels.some((p) => p.type === type)) {
          result.push({ type, title: def.title, device: null, deviceName: null })
        }
        continue
      }
      for (const device of state.devices.filter((d) => d.kind === def.deviceKind)) {
        if (!state.panels.some((p) => p.type === type && p.device === device.id)) {
          result.push({ type, title: def.title, device: device.id, deviceName: device.name })
        }
      }
    }
    return result
  })

  async function refreshDevices(): Promise<void> {
    try {
      state.devices = (await API.getSystemDevices()).devices
    } catch {
      // Keep the last known registry; the UI shows stale connection state.
    }
  }

  async function init(): Promise<void> {
    await refreshDevices()
    try {
      const layout = await API.getPanelLayout()
      state.panels = layout.panels
        .filter((panel) => isPanelType(panel.type))
        .map((panel) => ({ ...panel, type: panel.type as PanelType }))
    } catch {
      state.panels = []
    }
    state.loaded = true
  }

  function addPanel(available: AvailablePanel): void {
    const def = PANEL_DEFS[available.type]
    const taken = (candidate: string) => state.panels.some((p) => p.id === candidate)
    let id = available.device ? `${available.type}-${available.device}` : available.type
    for (let n = 2; taken(id); n += 1) id = `${available.type}-${n}`
    state.panels.push({
      id,
      type: available.type,
      device: available.device,
      aspect: def.defaultAspect,
    })
    persist()
  }

  function removePanel(id: string): void {
    const index = state.panels.findIndex((panel) => panel.id === id)
    if (index >= 0) {
      state.panels.splice(index, 1)
      persist()
    }
  }

  /** Reorder after a drag-and-drop gesture (target = dropped-before index). */
  function reorderPanel(id: string, toIndex: number): void {
    const from = state.panels.findIndex((panel) => panel.id === id)
    if (from < 0) return
    const target = Math.max(0, Math.min(state.panels.length - 1, toIndex))
    if (from === target) return
    const [panel] = state.panels.splice(from, 1)
    state.panels.splice(target, 0, panel)
    persist()
  }

  async function resetLayout(): Promise<void> {
    const layout = await API.resetPanelLayout()
    state.panels = layout.panels
      .filter((panel) => isPanelType(panel.type))
      .map((panel) => ({ ...panel, type: panel.type as PanelType }))
  }

  return {
    state: readonly(state),
    deviceById,
    availablePanels,
    refreshDevices,
    init,
    addPanel,
    removePanel,
    reorderPanel,
    resetLayout,
  }
}
