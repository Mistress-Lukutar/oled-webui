/**
 * Singleton reactive store: device state, SSE subscription, actions.
 */

import { computed, reactive, readonly } from 'vue'
import { API } from '../api'
import type {
  LastContent,
  Preset,
  RenderOptions,
  StatusData,
  TextRequest,
} from '../api'

interface StoreState {
  connected: boolean
  device: StatusData['device']
  keepalive: { enabled: boolean; interval: number }
  video: StatusData['video']
  hasFrame: boolean
  lastContent: LastContent | null
  frameTs: number
  presets: Preset[]
  fonts: string[]
  error: string | null
  sseUp: boolean
}

const state = reactive<StoreState>({
  connected: false,
  device: null,
  keepalive: { enabled: false, interval: 1.5 },
  video: { playing: false, file: null, loop: false, fps: 0, frames_sent: 0 },
  hasFrame: false,
  lastContent: null,
  frameTs: Date.now(),
  presets: [],
  fonts: [],
  error: null,
  sseUp: false,
})

function applyStatus(status: StatusData): void {
  state.connected = status.connected
  state.device = status.device
  state.keepalive = status.keepalive
  state.video = status.video
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
    return
  }
  if (event.type === 'video' || event.type === 'keepalive') {
    void refreshStatus()
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
    'keepalive',
    'video',
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
    await Promise.all([actions.loadPresets(), actions.loadFonts()])
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

  async toggleKeepalive(enabled: boolean): Promise<boolean> {
    return wrap(async () => {
      state.keepalive = await API.setKeepalive(enabled, state.keepalive.interval)
    })
  },

  async sendColor(color: string, brightness: number): Promise<boolean> {
    return wrap(async () => {
      await API.sendColor(color, brightness)
    })
  },

  async sendText(req: TextRequest): Promise<boolean> {
    return wrap(async () => {
      await API.sendText(req)
    })
  },

  async uploadImage(file: File, opts: RenderOptions): Promise<boolean> {
    return wrap(async () => {
      await API.uploadImage(file, opts)
    })
  },

  async powerOff(): Promise<boolean> {
    return wrap(() => API.powerOff().then(() => undefined))
  },

  async powerOn(): Promise<boolean> {
    return wrap(() => API.powerOn().then(() => undefined))
  },

  async runTest(delay: number): Promise<boolean> {
    return wrap(() => API.runTest(delay).then(() => undefined))
  },

  async startVideo(
    file: File,
    fps: number,
    loop: boolean,
    opts: RenderOptions,
  ): Promise<boolean> {
    return wrap(async () => {
      state.video = await API.startVideo(file, fps, loop, opts)
    })
  },

  async stopVideo(): Promise<boolean> {
    return wrap(async () => {
      state.video = await API.stopVideo()
    })
  },

  async loadPresets(): Promise<void> {
    try {
      state.presets = (await API.listPresets()).presets
    } catch {
      state.presets = []
    }
  },

  async saveCurrent(name: string): Promise<boolean> {
    return wrap(async () => {
      await API.saveCurrentPreset(name)
      await actions.loadPresets()
    })
  },

  async applyPreset(id: string): Promise<boolean> {
    return wrap(async () => {
      await API.applyPreset(id)
    })
  },

  async deletePreset(id: string): Promise<boolean> {
    return wrap(async () => {
      await API.deletePreset(id)
      await actions.loadPresets()
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
