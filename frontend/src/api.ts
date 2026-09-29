/**
 * Typed fetch wrapper and API endpoint functions.
 */

import type { ArgbLayout, ArgbStatus, DeviceDefinition, DeviceSummary } from './argb/types'

export interface Resolution {
  width: number
  height: number
}

export interface DeviceInfo {
  vid: number
  pid: number
  pm: number
  sub: number
  resolution: Resolution
}

export interface DisplaySettings {
  keepalive_enabled: boolean
  keepalive_interval: number
  brightness: number
  quality: number
  blank_on_display_off: boolean
}

export interface SceneState {
  running: boolean
  scene_id: string | null
  name: string | null
  refresh: number
  max_fps: number
  frames_sent: number
}

export interface SceneInfo {
  id: string
  name: string
  created_at: number
  updated_at: number
  widget_count: number
}

export interface SceneDetail {
  scene: SceneInfo
  yaml: string
  assets: string[]
  /** Component YAML sources keyed by component name (for `use:` entries). */
  components?: Record<string, string>
}

export interface LastContent {
  type: 'image' | 'color' | 'text' | 'scene'
  params: Record<string, unknown>
  payload: Record<string, unknown>
}

export interface SystemDevice {
  id: string
  kind: 'display' | 'argb'
  name: string
  connected: boolean
}

export interface PanelConfig {
  id: string
  type: string
  device: string | null
  aspect: number
}

export interface PanelLayout {
  version: number
  panels: PanelConfig[]
}

export interface StatusData {
  connected: boolean
  device: DeviceInfo | null
  resolution: Resolution
  settings: DisplaySettings
  scene: SceneState
  has_frame: boolean
  last_content: LastContent | null
}

interface Envelope<T> {
  success: boolean
  error: string | null
  data: T
}

// Raw JPEG responses (scene preview) bypass the JSON envelope.
async function apiBlob(path: string, init?: RequestInit): Promise<Blob> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = `HTTP ${response.status}`
    try {
      const body = (await response.json()) as Envelope<unknown>
      if (body.error !== null) message = body.error
    } catch {
      // Not a JSON error body; keep the HTTP status message.
    }
    throw new Error(message)
  }
  return response.blob()
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  let body: Envelope<T>
  try {
    body = (await response.json()) as Envelope<T>
  } catch {
    throw new Error(`HTTP ${response.status}`)
  }
  if (!response.ok || !body.success) {
    throw new Error(body.error ?? `HTTP ${response.status}`)
  }
  return body.data
}

function form(
  fields: Record<string, string | number | boolean | File>,
): FormData {
  const data = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    data.append(key, value instanceof File ? value : String(value))
  }
  return data
}

/** URL of a stored scene asset (image/font), for canvas rendering. */
function sceneAssetUrl(sceneId: string, name: string): string {
  return `/api/scenes/${sceneId}/assets/${encodeURIComponent(name)}`
}

/** URL of a shared library font file, for canvas rendering. */
function libraryFontUrl(name: string): string {
  return `/api/frame/fonts/${encodeURIComponent(name)}`
}

export const API = {
  getStatus: () => api<StatusData>('/api/device/status'),
  connect: () =>
    api<DeviceInfo>('/api/device/connect', { method: 'POST' }),
  disconnect: () => api<StatusData>('/api/device/disconnect', { method: 'POST' }),
  getDisplaySettings: () => api<DisplaySettings>('/api/device/settings'),
  setDisplaySettings: (patch: Partial<DisplaySettings>) =>
    api<DisplaySettings>('/api/device/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }),

  powerOff: () => api<null>('/api/frame/off', { method: 'POST' }),
  powerOn: () => api<null>('/api/frame/on', { method: 'POST' }),
  runTest: (delay: number) =>
    api<null>('/api/frame/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delay }),
    }),
  listFonts: () => api<{ fonts: string[] }>('/api/frame/fonts'),
  uploadFonts: (files: File[]) => {
    const data = new FormData()
    for (const file of files) data.append('files', file)
    return api<{ fonts: string[] }>('/api/frame/fonts', {
      method: 'POST',
      body: data,
    })
  },
  deleteFont: (name: string) =>
    api<{ fonts: string[] }>(`/api/frame/fonts/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  listScenes: () => api<{ scenes: SceneInfo[] }>('/api/scenes'),
  getScene: (id: string) => api<SceneDetail>(`/api/scenes/${id}`),
  createScene: (name: string, file?: File) =>
    api<SceneDetail>('/api/scenes', {
      method: 'POST',
      body: form(file ? { name, file } : { name }),
    }),
  saveScene: (id: string, yaml: string, name?: string) =>
    api<{ scene: SceneInfo }>(`/api/scenes/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml, name }),
    }),
  deleteScene: (id: string) =>
    api<null>(`/api/scenes/${id}`, { method: 'DELETE' }),
  uploadSceneAssets: (id: string, files: File[]) => {
    const data = new FormData()
    for (const file of files) data.append('files', file)
    return api<{ assets: string[] }>(`/api/scenes/${id}/assets`, {
      method: 'POST',
      body: data,
    })
  },
  deleteSceneAsset: (id: string, name: string) =>
    api<{ assets: string[] }>(`/api/scenes/${id}/assets/${name}`, {
      method: 'DELETE',
    }),
  applyScene: (id: string) =>
    api<SceneState>(`/api/scenes/${id}/apply`, { method: 'POST' }),
  sceneAssetUrl,
  libraryFontUrl,
  stopScene: () => api<SceneState>('/api/scenes/stop', { method: 'POST' }),
  seedExampleScene: () =>
    api<SceneDetail>('/api/scenes/seed-example', { method: 'POST' }),
  previewScene: (id: string) =>
    apiBlob(`/api/scenes/${id}/preview`, { method: 'POST' }),
  previewSceneYaml: (yaml: File, sceneId: string | null) => {
    const data = new FormData()
    data.append('file', yaml)
    if (sceneId !== null) data.append('scene_id', sceneId)
    return apiBlob('/api/scenes/preview', { method: 'POST', body: data })
  },

  getArgbStatus: () => api<ArgbStatus>('/api/argb/status'),

  getSystemDevices: () =>
    api<{ devices: SystemDevice[] }>('/api/system/devices'),
  getPanelLayout: () => api<PanelLayout>('/api/ui/panels'),
  savePanelLayout: (layout: PanelLayout) =>
    api<PanelLayout>('/api/ui/panels', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layout),
    }),
  resetPanelLayout: () =>
    api<PanelLayout>('/api/ui/panels', { method: 'DELETE' }),

  connectArgb: () => api<ArgbStatus>('/api/argb/connect', { method: 'POST' }),
  disconnectArgb: () => api<ArgbStatus>('/api/argb/disconnect', { method: 'POST' }),
  getArgbLayout: () => api<{ layout: ArgbLayout }>('/api/argb/layout'),
  saveArgbLayout: (layout: ArgbLayout, apply = false) =>
    api<{ layout?: ArgbLayout }>(`/api/argb/layout?apply=${apply}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layout),
    }),
  applyArgb: (layout: ArgbLayout) =>
    api<ArgbStatus>('/api/argb/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layout),
    }),
  stopArgb: () => api<ArgbStatus>('/api/argb/stop', { method: 'POST' }),
  listArgbDevices: () => api<{ devices: DeviceSummary[] }>('/api/argb/devices'),
  getArgbDevice: (id: string) =>
    api<{ yaml: string; definition: DeviceDefinition }>(`/api/argb/devices/${id}`),
  createArgbDevice: (yaml: string) =>
    api<{ definition: DeviceDefinition }>('/api/argb/devices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml }),
    }),
  updateArgbDevice: (id: string, yaml: string) =>
    api<{ definition: DeviceDefinition }>(`/api/argb/devices/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ yaml }),
    }),
  deleteArgbDevice: (id: string) =>
    api<{ deleted: string }>(`/api/argb/devices/${id}`, { method: 'DELETE' }),
  renderArgbPreview: (layout: ArgbLayout, t?: number) =>
    api<{ buffers: Record<string, string> }>(
      t === undefined ? '/api/argb/render_preview' : `/api/argb/render_preview?t=${t}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(layout),
      },
    ),
}
