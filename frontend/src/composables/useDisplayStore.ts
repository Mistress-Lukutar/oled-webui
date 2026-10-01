/**
 * Singleton reactive store: device state, SSE subscription, actions.
 */

import { computed, reactive, readonly } from 'vue'
import { API } from '../api'
import { useArgbStore } from '../argb/store'
import { usePanelsStore } from './usePanelsStore'
import type {
  DisplaySettings,
  LastContent,
  SceneInfo,
  SceneState,
  StatusData,
} from '../api'

interface StoreState {
  connected: boolean
  device: StatusData['device']
  resolution: StatusData['resolution']
  settings: DisplaySettings
  scene: SceneState
  hasFrame: boolean
  lastContent: LastContent | null
  frameTs: number
  scenes: SceneInfo[]
  fonts: string[]
  error: string | null
  sseUp: boolean
}

const NO_SCENE: SceneState = {
  running: false,
  scene_id: null,
  name: null,
  refresh: 0,
  max_fps: 0,
  frames_sent: 0,
}

const state = reactive<StoreState>({
  connected: false,
  device: null,
  resolution: { width: 480, height: 480 },
  settings: {
    keepalive_enabled: true,
    keepalive_interval: 1.5,
    brightness: 100,
    quality: 95,
    blank_on_display_off: false,
  },
  scene: { ...NO_SCENE },
  hasFrame: false,
  lastContent: null,
  frameTs: Date.now(),
  scenes: [],
  fonts: [],
  error: null,
  sseUp: false,
})

function applyStatus(status: StatusData): void {
  state.connected = status.connected
  state.device = status.device
  state.resolution = status.resolution
  state.settings = status.settings
  state.scene = status.scene
  state.hasFrame = status.has_frame
  state.lastContent = status.last_content
}

function showError(message: string): void {
  state.error = message
  window.setTimeout(() => {
    if (state.error === message) state.error = null
  }, 5000)
}

async function refreshStatus(): Promise<void> {
  try {
    applyStatus(await API.getStatus())
  } catch (err) {
    showError(String(err))
  }
}

// ---------------------------------------------------------------------
// SSE: named events with manual exponential backoff reconnect.
// ---------------------------------------------------------------------

const MAX_RETRY_DELAY_MS = 30000
let eventSource: EventSource | null = null
let retryDelayMs = 1000

function handleFrameUpdated(): void {
  state.hasFrame = true
  state.frameTs = Date.now()
}

function handleSseEvent(event: MessageEvent): void {
  if (event.type === 'frame_updated') {
    handleFrameUpdated()
    return
  }
  if (event.type === 'connection') {
    void refreshStatus()
    // Device availability (registry connection flags) may have changed.
    void usePanelsStore().refreshDevices()
    return
  }
  if (event.type === 'display_settings') {
    void refreshStatus()
    return
  }
  if (event.type === 'scene') {
    void refreshStatus()
    void actions.loadScenes()
    return
  }
  if (event.type === 'argb') {
    void useArgbStore().actions.refreshStatus()
    void usePanelsStore().refreshDevices()
    return
  }
  if (event.type === 'error') {
    try {
      const payload = JSON.parse(event.data) as { error?: string }
      showError(payload.error ?? 'Device error')
    } catch {
      showError('Device error')
    }
  }
}

function startSse(): void {
  if (eventSource !== null) eventSource.close()
  eventSource = new EventSource('/events')
  eventSource.onopen = () => {
    retryDelayMs = 1000
    state.sseUp = true
  }
  for (const type of [
    'connection',
    'frame_updated',
    'display_settings',
    'scene',
    'argb',
    'error',
  ]) {
    eventSource.addEventListener(type, handleSseEvent as EventListener)
  }
  eventSource.onerror = () => {
    state.sseUp = false
    eventSource?.close()
    eventSource = null
    window.setTimeout(startSse, retryDelayMs)
    retryDelayMs = Math.min(retryDelayMs * 2, MAX_RETRY_DELAY_MS)
  }
}

// ---------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------

async function wrap(action: () => Promise<void>): Promise<boolean> {
  try {
    await action()
    return true
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
    return false
  }
}

const actions = {
  async init(): Promise<void> {
    await refreshStatus()
    await Promise.all([actions.loadFonts(), actions.loadScenes()])
    startSse()
  },

  async connect(): Promise<boolean> {
    return wrap(async () => {
      state.device = await API.connect()
      state.connected = true
      await refreshStatus()
    })
  },

  async disconnect(): Promise<boolean> {
    return wrap(async () => {
      await API.disconnect()
      await refreshStatus()
    })
  },

  async setDisplaySettings(patch: Partial<DisplaySettings>): Promise<boolean> {
    return wrap(async () => {
      state.settings = await API.setDisplaySettings(patch)
    })
  },

  async loadScenes(): Promise<void> {
    try {
      state.scenes = (await API.listScenes()).scenes
    } catch {
      state.scenes = []
    }
  },

  async applyScene(id: string): Promise<boolean> {
    return wrap(async () => {
      const result = await API.applyScene(id)
      await refreshStatus()
      // Per-device failures arrive as a success payload with "error:" marks.
      const failed = Object.entries(result.devices).filter(([, mark]) =>
        mark.startsWith('error:'),
      )
      if (failed.length > 0) {
        throw new Error(
          failed.map(([key, mark]) => `${key}: ${mark.slice('error: '.length)}`).join('; '),
        )
      }
    })
  },

  async stopScene(): Promise<boolean> {
    return wrap(async () => {
      state.scene = await API.stopScene()
    })
  },

  async deleteScene(id: string): Promise<boolean> {
    return wrap(async () => {
      await API.deleteScene(id)
      if (state.scene.scene_id === id && state.scene.running) {
        state.scene = { ...NO_SCENE }
      }
      await actions.loadScenes()
    })
  },

  async loadFonts(): Promise<void> {
    try {
      state.fonts = (await API.listFonts()).fonts
    } catch {
      state.fonts = []
    }
  },
}

const previewUrl = computed(() =>
  state.hasFrame ? `/api/frame/preview?t=${state.frameTs}` : null,
)

export function useDisplayStore() {
  return {
    state: readonly(state),
    previewUrl,
    actions,
    applyStatus,
    refreshStatus,
    showError,
  }
}
