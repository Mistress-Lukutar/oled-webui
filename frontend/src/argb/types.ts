/**
 * TypeScript mirror of the backend ARGB schema (argb/schema.py,
 * argb/devices.py) plus factory templates for editor objects.
 */

export type EffectType =
  | 'fill'
  | 'gradient'
  | 'rainbow'
  | 'breathing'
  | 'comet'
  | 'scanner'
  | 'meter'

export interface StopSpec {
  pos: number
  color: string
}

export interface MaskSpec {
  all: boolean
  runs: Record<string, [number, number][]>
}

export interface FillEffect {
  type: 'fill'
  color: string
}

export interface GradientEffect {
  type: 'gradient'
  stops: StopSpec[]
  scale: number
  mode: 'static' | 'scroll' | 'pingpong'
  speed: number
}

export interface RainbowEffect {
  type: 'rainbow'
  speed: number
  scale: number
  direction: 1 | -1
  saturation: number
  value: number
}

export interface BreathingEffect {
  type: 'breathing'
  colors: string[]
  period: number
  min_level: number
}

export interface CometEffect {
  type: 'comet'
  color: string
  tail: number
  speed: number
  direction: 1 | -1
  mode: 'loop' | 'bounce'
  fade: boolean
}

export interface ScannerEffect {
  type: 'scanner'
  color: string
  width: number
  period: number
}

export interface MeterEffect {
  type: 'meter'
  source: string
  color_low: string
  color_high: string
  max_value: number
  mode: 'fill' | 'bar'
}

export type ArgbEffect =
  | FillEffect
  | GradientEffect
  | RainbowEffect
  | BreathingEffect
  | CometEffect
  | ScannerEffect
  | MeterEffect

// ---------------------------------------------------------------------------
// Device definitions (argb/devices.py): one LED shape per LED, list order is
// the LED index; decor is non-LED artwork drawn underneath the LEDs.
// ---------------------------------------------------------------------------

export interface LedRectShape {
  type: 'rect'
  rect: [number, number, number, number]
  radius?: number
  stroke_color?: string | null
  stroke_width?: number
}

export interface LedCircleShape {
  type: 'circle'
  center: [number, number]
  radius: number
  stroke_color?: string | null
  stroke_width?: number
}

export interface LedPolygonShape {
  type: 'polygon'
  points: [number, number][]
  stroke_color?: string | null
  stroke_width?: number
}

export type LedShape = LedRectShape | LedCircleShape | LedPolygonShape

export interface DecorPaint {
  fill: boolean
  fill_color: string
  stroke_color: string
  stroke_width: number
  stroke_align: 'center' | 'inside' | 'outside'
  opacity: number
}

export interface DecorRectShape extends DecorPaint {
  type: 'rect'
  rect: [number, number, number, number]
  radius?: number
}

export interface DecorCircleShape extends DecorPaint {
  type: 'circle'
  center: [number, number]
  radius: number
}

export interface DecorPolygonShape extends DecorPaint {
  type: 'polygon'
  points: [number, number][]
}

export interface DecorPolylineShape {
  type: 'polyline'
  points: [number, number][]
  stroke_color: string
  stroke_width: number
  opacity: number
}

export type DecorShape =
  | DecorRectShape
  | DecorCircleShape
  | DecorPolygonShape
  | DecorPolylineShape

export interface DeviceDefinition {
  id: string
  name: string
  size: [number, number] | null
  leds: LedShape[]
  decor: DecorShape[]
}

/** Library listing entry: summary plus the full parsed definition. */
export interface DeviceSummary {
  id: string
  name: string
  leds: number
  used_by: string[]
  definition: DeviceDefinition
}

export interface ArgbDevice {
  id: string
  name: string
  /** Device definition id from the library. */
  device: string
  header_id: string
  x: number
  y: number
  rotation: number
  scale: number
}

export interface ArgbHeader {
  id: string
  name: string
  zone_index: number
  size: number | null
  devices: string[]
}

export interface ArgbLayer {
  id: string
  name: string
  enabled: boolean
  opacity: number
  mask: MaskSpec
  effect: ArgbEffect
}

export interface ArgbLayout {
  version: number
  fps: number
  brightness: number
  autostart: boolean
  headers: ArgbHeader[]
  devices: ArgbDevice[]
  layers: ArgbLayer[]
}

export interface ZoneInfo {
  index: number
  name: string
  leds: number
}

export interface ArgbStatus {
  connected: boolean
  controller: string | null
  zones: ZoneInfo[]
  running: boolean
  fps: number
  brightness: number
  autostart: boolean
  frames_sent: number
}

/** Logical workspace size the editor arranges devices on. */
export const WORKSPACE_WIDTH = 800
export const WORKSPACE_HEIGHT = 500

function uid(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().slice(0, 8)}`
}

/** Create a new device instance from a library definition. */
export function makeDevice(
  definition: DeviceDefinition,
  headerId: string,
  x: number,
  y: number,
  ordinal: number,
): ArgbDevice {
  const base = definition.name || definition.id
  return {
    id: uid('d'),
    name: `${base} ${ordinal}`,
    device: definition.id,
    header_id: headerId,
    x,
    y,
    rotation: 0,
    scale: 1,
  }
}

const DEFAULT_STOPS: StopSpec[] = [
  { pos: 0, color: '#FF0044' },
  { pos: 0.5, color: '#FFCC00' },
  { pos: 1, color: '#4400FF' },
]

/** Create a new layer wrapping a fresh effect of the given type. */
export function makeLayer(type: EffectType, ordinal: number): ArgbLayer {
  let effect: ArgbEffect
  switch (type) {
    case 'gradient':
      effect = {
        type: 'gradient',
        stops: DEFAULT_STOPS.map((stop) => ({ ...stop })),
        scale: 30,
        mode: 'scroll',
        speed: 0.3,
      }
      break
    case 'rainbow':
      effect = {
        type: 'rainbow',
        speed: 0.5,
        scale: 32,
        direction: 1,
        saturation: 1,
        value: 1,
      }
      break
    case 'breathing':
      effect = { type: 'breathing', colors: ['#FF0044'], period: 2, min_level: 0.1 }
      break
    case 'comet':
      effect = {
        type: 'comet',
        color: '#FF2222',
        tail: 8,
        speed: 12,
        direction: 1,
        mode: 'loop',
        fade: true,
      }
      break
    case 'scanner':
      effect = { type: 'scanner', color: '#33FF66', width: 3, period: 2 }
      break
    case 'meter':
      effect = {
        type: 'meter',
        source: 'cpu.percent',
        color_low: '#00FF88',
        color_high: '#FF2222',
        max_value: 100,
        mode: 'bar',
      }
      break
    default:
      effect = { type: 'fill', color: '#2244CC' }
  }
  const label = type.charAt(0).toUpperCase() + type.slice(1)
  return {
    id: uid('l'),
    name: `${label} ${ordinal}`,
    enabled: true,
    opacity: 1,
    mask: { all: true, runs: {} },
    effect,
  }
}

/** Deep-copy a layout (drafts must never alias the stored document). */
export function cloneLayout(layout: ArgbLayout): ArgbLayout {
  return JSON.parse(JSON.stringify(layout)) as ArgbLayout
}

/** Build a minimal starter layout (used when the server has none). */
export function defaultLayout(): ArgbLayout {
  return {
    version: 1,
    fps: 30,
    brightness: 100,
    autostart: false,
    headers: [
      { id: 'h1', name: 'ARGB 1', zone_index: 0, size: null, devices: [] },
    ],
    devices: [],
    layers: [],
  }
}
