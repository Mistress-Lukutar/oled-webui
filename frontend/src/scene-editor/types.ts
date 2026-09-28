/**
 * TS mirror of the scene schema (src/oled_webui/scene/schema.py) plus
 * safe accessors over the raw parsed YAML object. The raw object stays
 * the source of truth so unknown keys and component params survive
 * round-trips; these views only read/write the fields the schema defines.
 */

export type Align = 'left' | 'center' | 'right'
export type Orientation = 'horizontal' | 'vertical'
/** Writing direction: rtl mirrors ltr, btt mirrors ttb (stacked). */
export type TextDirection = 'ltr' | 'rtl' | 'ttb' | 'btt'

export const TEXT_DIRECTIONS: Array<{ value: TextDirection; label: string }> = [
  { value: 'ltr', label: 'Left → right' },
  { value: 'rtl', label: 'Right ← left (mirror)' },
  { value: 'ttb', label: 'Top ↓ bottom (stacked)' },
  { value: 'btt', label: 'Bottom ↑ top (mirror)' },
]

/** Plain number or an expression string evaluated per frame. */
export type ExprValue = number | string

export interface TextStyle {
  family?: string | null
  size?: number
  color?: string
  /** Line spacing as a multiplier of font size (schema default 1.2). */
  leading?: number
  /** Letter spacing in pixels. */
  tracking?: number
  direction?: TextDirection
  stroke_width?: number
  stroke_color?: string
}

export interface BarStyle {
  fg?: string
  bg?: string
  border?: number
  border_color?: string
  border_align?: 'center' | 'inside' | 'outside'
  radius?: number
  orientation?: Orientation
}

export interface RingStyle {
  fg?: string
  bg?: string
  width?: number
  start_angle?: number
  sweep?: number
}

export interface GraphStyle {
  fg?: string
  bg?: string | null
  fill?: boolean
  line_width?: number
  scale_max?: number | null
}

export interface AnimateSpec {
  easing?: string
  duration?: number
}

export interface BaseFields {
  rect?: [number, number, number, number]
  visible?: boolean | string
  offset_x?: ExprValue
  offset_y?: ExprValue
  opacity?: ExprValue
  rotation?: ExprValue
  animate?: Record<string, AnimateSpec>
  /** Editor hint: locked elements render but are mouse-transparent. */
  locked?: boolean
  [key: string]: unknown
}

export interface TextWidgetRaw extends BaseFields {
  type: 'text'
  source?: string | null
  value?: string | number | null
  align?: Align
  style?: TextStyle
}

export interface BarWidgetRaw extends BaseFields {
  type: 'bar'
  source: string
  style?: BarStyle
}

export interface RingWidgetRaw extends BaseFields {
  type: 'ring'
  source: string
  style?: RingStyle
}

export interface GraphWidgetRaw extends BaseFields {
  type: 'graph'
  source: string
  history?: number
  style?: GraphStyle
}

export type ImageFit = 'scale' | 'contain' | 'cover' | 'stretch'

export interface ImageWidgetRaw extends BaseFields {
  type: 'image'
  path: string
  fit?: ImageFit
  scale?: number
}

export type WidgetRaw =
  | TextWidgetRaw
  | BarWidgetRaw
  | RingWidgetRaw
  | GraphWidgetRaw
  | ImageWidgetRaw

/** A `use:` entry referencing a reusable component. */
export interface ComponentInstanceRaw extends BaseFields {
  use: string
  at?: [number, number]
  [param: string]: unknown
}

export type EntryRaw = WidgetRaw | ComponentInstanceRaw

export interface ImageLayerRaw {
  path: string
  pos?: [number, number] | null
  scale?: number
  opacity?: number
  [key: string]: unknown
}

export interface SceneDocumentRaw {
  background?: ImageLayerRaw[]
  widgets?: EntryRaw[]
  refresh?: number
  max_fps?: number
  keepalive_interval?: number
  [key: string]: unknown
}

export const WIDGET_TYPES = ['text', 'bar', 'ring', 'graph', 'image'] as const
export type WidgetType = (typeof WIDGET_TYPES)[number]

export const EASINGS = [
  'linear',
  'ease-in-quad',
  'ease-out-quad',
  'ease-in-out-quad',
  'ease-in-cubic',
  'ease-out-cubic',
  'ease-in-out-cubic',
  'ease-out-back',
  'ease-out-elastic',
  'ease-out-bounce',
] as const

export const DATA_SOURCES = [
  'cpu.percent',
  'cpu.cores',
  'cpu.freq_ghz',
  'ram.percent',
  'ram.used_gb',
  'ram.free_gb',
  'ram.total_gb',
  'disk.percent',
  'disk.used_gb',
  'disk.free_gb',
  'net.kbps',
  'temp.cpu',
  'gpu.percent',
  'gpu.temp',
  'time.h',
  'time.m',
  'time.s',
  'time.hms',
  'time.hhmm',
  'time.date',
] as const

const DOC_KEYS = new Set([
  'background',
  'widgets',
  'refresh',
  'max_fps',
  'keepalive_interval',
])

const BASE_WIDGET_KEYS = new Set([
  'type',
  'use',
  'at',
  'rect',
  'visible',
  'offset_x',
  'offset_y',
  'opacity',
  'rotation',
  'animate',
  'locked',
])

const WIDGET_KEYS: Record<WidgetType, Set<string>> = {
  text: new Set(['source', 'value', 'align', 'style']),
  bar: new Set(['source', 'style']),
  ring: new Set(['source', 'style']),
  graph: new Set(['source', 'history', 'style']),
  image: new Set(['path', 'fit', 'scale']),
}

const STYLE_KEYS = new Set([
  'family',
  'size',
  'color',
  'leading',
  'tracking',
  'direction',
  'stroke_width',
  'stroke_color',
  'fg',
  'bg',
  'border',
  'border_color',
  'border_align',
  'radius',
  'orientation',
  'width',
  'start_angle',
  'sweep',
  'fill',
  'line_width',
  'scale_max',
])

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isComponentInstance(entry: unknown): entry is ComponentInstanceRaw {
  return isObject(entry) && typeof entry['use'] === 'string'
}

export function widgetType(entry: EntryRaw): WidgetType | null {
  if (!isObject(entry)) return null
  const type = entry['type']
  return WIDGET_TYPES.includes(type as WidgetType) ? (type as WidgetType) : null
}

/** Widget box as [x, y, w, h]; component instances have no own rect. */
export function entryRect(entry: EntryRaw): [number, number, number, number] | null {
  const rect = entry['rect']
  if (
    Array.isArray(rect) &&
    rect.length === 4 &&
    rect.every((n) => typeof n === 'number' && Number.isFinite(n))
  ) {
    return rect as [number, number, number, number]
  }
  return null
}

export function entryLabel(entry: EntryRaw, index: number): string {
  if (isComponentInstance(entry)) return `use: ${entry['use']}`
  const type = widgetType(entry)
  if (type === null) return `#${index + 1}`
  const text = entry['value']
  if (type === 'text' && typeof text === 'string' && text.trim() !== '') {
    return `text · ${text.trim().slice(0, 24)}`
  }
  if (type !== 'text' && typeof entry['source'] === 'string') {
    return `${type} · ${entry['source']}`
  }
  if (type === 'image' && typeof entry['path'] === 'string') {
    return `image · ${String(entry['path']).slice(0, 24)}`
  }
  return type
}

/** Unknown top-level keys (the server rejects those with extra="forbid"). */
export function unknownDocKeys(doc: SceneDocumentRaw): string[] {
  return Object.keys(doc).filter((key) => !DOC_KEYS.has(key))
}

/** Unknown per-widget keys for the given entry, if it is a known widget. */
export function unknownWidgetKeys(entry: EntryRaw): string[] {
  if (isComponentInstance(entry)) return []
  const type = widgetType(entry)
  if (type === null) return []
  return Object.keys(entry).filter(
    (key) => !BASE_WIDGET_KEYS.has(key) && !WIDGET_KEYS[type].has(key),
  )
}

/** Unknown style keys for a style mapping (shared key set across types). */
export function unknownStyleKeys(style: unknown): string[] {
  if (!isObject(style)) return []
  return Object.keys(style).filter((key) => !STYLE_KEYS.has(key))
}
