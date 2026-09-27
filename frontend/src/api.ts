/**
 * Typed fetch wrapper and API endpoint functions.
 */

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

export interface KeepaliveState {
  enabled: boolean
  interval: number
}

export interface VideoState {
  playing: boolean
  file: string | null
  loop: boolean
  fps: number
  frames_sent: number
}

export interface LastContent {
  type: 'image' | 'color' | 'text'
  params: Record<string, unknown>
  payload: Record<string, unknown>
}

export interface StatusData {
  connected: boolean
  device: DeviceInfo | null
  keepalive: KeepaliveState
  video: VideoState
  has_frame: boolean
  last_content: LastContent | null
}

export interface Preset {
  id: string
  name: string
  type: 'image' | 'color' | 'text'
  params: Record<string, number | string>
  payload: Record<string, unknown>
  created_at: number
  has_asset: boolean
}

export interface TextRequest {
  text: string
  font_size: number
  color: string
  background: string
  align: 'left' | 'center' | 'right'
  valign: 'top' | 'middle' | 'bottom'
  padding: number
  rotation: number
  brightness: number
  quality: number
  font_name: string | null
}

export interface RenderOptions {
  rotation: number
  brightness: number
  fit: 'contain' | 'stretch' | 'width' | 'height'
  quality: number
}

interface Envelope<T> {
  success: boolean
  error: string | null
  data: T
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

export const API = {
  getStatus: () => api<StatusData>('/api/device/status'),
  connect: () =>
    api<DeviceInfo>('/api/device/connect', { method: 'POST' }),
  disconnect: () => api<StatusData>('/api/device/disconnect', { method: 'POST' }),
  setKeepalive: (enabled: boolean, interval?: number) =>
    api<KeepaliveState>('/api/device/keepalive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, interval }),
    }),

  sendColor: (color: string, brightness: number) =>
    api<Record<string, number>>('/api/frame/color', {
      method: 'POST',
      body: form({ color, brightness }),
    }),
  sendText: (req: TextRequest) =>
    api<Record<string, number>>('/api/frame/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
  uploadImage: (file: File, opts: RenderOptions) =>
    api<Record<string, number>>('/api/frame/image', {
      method: 'POST',
      body: form({ ...opts, file }),
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

  startVideo: (
    file: File,
    fps: number,
    loop: boolean,
    opts: RenderOptions,
  ) =>
    api<VideoState>('/api/video', {
      method: 'POST',
      body: form({ ...opts, fps, loop, file }),
    }),
  stopVideo: () => api<VideoState>('/api/video/stop', { method: 'POST' }),

  listPresets: () => api<{ presets: Preset[] }>('/api/presets'),
  saveCurrentPreset: (name: string) =>
    api<Preset>('/api/presets/save-current', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
  applyPreset: (id: string) =>
    api<Record<string, number>>(`/api/presets/${id}/apply`, { method: 'POST' }),
  deletePreset: (id: string) =>
    api<null>(`/api/presets/${id}`, { method: 'DELETE' }),
}
