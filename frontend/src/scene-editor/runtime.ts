/**
 * Scene runtime evaluation for the editor canvas: evaluates expressions
 * per widget at a given scene time against a data-source provider
 * (placeholder values while editing). Mirrors runner.py's _evaluate.
 */

import { Expression } from './exprEval'
import type { ExpandedEntry } from './expand'
import type { EntryRaw, WidgetRaw } from './types'
import { isComponentInstance, widgetType } from './types'

export type ValueProvider = (source: string) => number | string | null

export interface EvalEntry {
  expanded: ExpandedEntry
  visible: boolean
  offsetX: number
  offsetY: number
  opacity: number
  rotation: number
  /** Raw source value (number, string or null when unavailable). */
  raw: number | string | null
  /** Bar/ring fill in [0, 1]. */
  value01: number
  /** Rendered text for text widgets. */
  text: string
  /** Graph sample series, oldest first. */
  history: number[]
  /** First evaluation problem for this widget, if any. */
  error: string | null
}

// Deterministic sample values so edited widgets show plausible content.
// time.* uses the real clock.
function sampleValue(source: string): number | string | null {
  const now = new Date()
  const pad = (n: number): string => String(n).padStart(2, '0')
  const samples: Record<string, number | string> = {
    'cpu.percent': 37,
    'cpu.cores': 8,
    'cpu.freq_ghz': 3.6,
    'ram.percent': 62,
    'ram.used_gb': 9.8,
    'ram.free_gb': 6.2,
    'ram.total_gb': 16,
    'disk.percent': 45,
    'disk.used_gb': 214,
    'disk.free_gb': 261,
    'net.kbps': 320,
    'temp.cpu': 52,
    'gpu.percent': 28,
    'gpu.temp': 61,
    'time.h': now.getHours(),
    'time.m': now.getMinutes(),
    'time.s': now.getSeconds(),
    'time.hms': `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
    'time.hhmm': `${pad(now.getHours())}:${pad(now.getMinutes())}`,
    'time.date': `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
  }
  const aliases: Record<string, string> = {
    cpu: 'cpu.percent',
    ram: 'ram.percent',
    disk: 'disk.percent',
    net: 'net.kbps',
    gpu: 'gpu.percent',
  }
  const resolved = aliases[source] ?? source
  const value = samples[resolved]
  return value === undefined ? null : value
}

/** Provider with deterministic sample data for the editor. */
export function makePlaceholderProvider(): ValueProvider {
  return (source) => sampleValue(source)
}

// Expression compilation cache shared across frames.
const exprCache = new Map<string, Expression>()

function compile(source: string): Expression {
  let expr = exprCache.get(source)
  if (expr === undefined) {
    expr = new Expression(source)
    exprCache.set(source, expr)
  }
  return expr
}

/** Evaluate a number-or-expression field; returns null when invalid. */
export function evalNumber(
  spec: number | string | undefined,
  vars: Record<string, number>,
  defaultValue = 0,
): number | null {
  if (spec === undefined) return defaultValue
  if (typeof spec === 'number') return spec
  try {
    return compile(spec).evaluate(vars)
  } catch {
    return null
  }
}

/** Evaluate a visibility flag (bool or expression); null when invalid. */
export function evalVisible(
  spec: boolean | string | undefined,
  vars: Record<string, number>,
): boolean | null {
  if (spec === undefined) return true
  if (typeof spec === 'boolean') return spec
  try {
    return compile(spec).evaluate(vars) !== 0
  } catch {
    return null
  }
}

/** Python str.format-style {value} and {value:.Nf} template support. */
export function formatTemplate(
  template: string | number | null | undefined,
  raw: number | string | null,
): { text: string; error: string | null } {
  if (template === null || template === undefined) {
    return { text: raw === null ? '' : String(raw), error: null }
  }
  const base = String(template)
  if (!base.includes('{')) return { text: base, error: null }
  let error: string | null = null
  const text = base.replace(/\{([^{}]*)\}/g, (match, rawSpec: string) => {
    const spec = rawSpec.trim()
    const colon = spec.indexOf(':')
    const field = colon === -1 ? spec : spec.slice(0, colon).trim()
    const format = colon === -1 ? '' : spec.slice(colon + 1).trim()
    if (field !== 'value') {
      error = `unknown template field {${field}}`
      return match
    }
    const fixed = format.match(/^\.(\d+)f$/)
    if (format !== '' && fixed === null) {
      error = `unsupported format spec "{${spec}}"`
      return match
    }
    if (typeof raw === 'number' && fixed !== null) {
      return raw.toFixed(Number(fixed[1]))
    }
    return raw === null ? '' : String(raw)
  })
  return { text, error }
}

/** Deterministic synthetic history for graph widgets in the editor. */
function syntheticHistory(source: string, count: number): number[] {
  const base = typeof sampleValue(source) === 'number' ? Number(sampleValue(source)) : 50
  const points: number[] = []
  for (let i = 0; i < count; i += 1) {
    const wave = Math.sin(i * 0.35) * base * 0.18 + Math.sin(i * 0.11 + 1.3) * base * 0.1
    points.push(Math.max(0, base + wave))
  }
  return points
}

export interface EvaluateOptions {
  time: number
  maxFps: number
  provider: ValueProvider
}

/**
 * Evaluate expanded entries at a scene time. Component instances in the
 * raw list must already be expanded (pass expandDocument().entries).
 */
export function evaluateEntries(
  entries: readonly ExpandedEntry[],
  opts: EvaluateOptions,
): EvalEntry[] {
  const varsBase = { t: opts.time, dt: opts.maxFps > 0 ? 1 / opts.maxFps : 0.05 }
  const results: EvalEntry[] = []
  for (const expanded of entries) {
    const widget = expanded.widget
    const type = widgetType(widget)
    const context = `widgets[${expanded.sourceIndex}] (${type ?? 'unknown'})`

    const sourceValue = widget['source']
    const source = typeof sourceValue === 'string' ? sourceValue : null
    const raw = source === null ? null : opts.provider(source)

    const vars: Record<string, number> = {
      ...varsBase,
      v: typeof raw === 'number' ? raw : 0,
    }

    let value01 = 0
    let text = ''
    let history: number[] = []
    let error: string | null = null

    if (raw === null && source !== null) {
      // Unknown data source: the server hides the widget.
      results.push({
        expanded,
        visible: false,
        offsetX: 0,
        offsetY: 0,
        opacity: 1,
        rotation: 0,
        raw: null,
        value01: 0,
        text: '',
        history: [],
        error: `${context}: source "${source}" is unavailable`,
      })
      continue
    }

    if (type === 'text') {
      const formatted = formatTemplate(widget['value'] as string | null, raw)
      text = formatted.text
      error = formatted.error
    } else if (type === 'bar' || type === 'ring') {
      const numeric = typeof raw === 'number' ? raw : Number(raw)
      value01 = Math.max(0, Math.min(1, (Number.isFinite(numeric) ? numeric : 0) / 100))
    } else if (type === 'graph') {
      const declared = widget['history']
      const count =
        typeof declared === 'number' && declared >= 2 ? Math.trunc(declared) : 60
      history = syntheticHistory(source ?? '', Math.min(count, 3600))
    }

    const visible = evalVisible(widget['visible'] as boolean | string | undefined, vars)
    const offsetX = evalNumber(widget['offset_x'] as number | string | undefined, vars)
    const offsetY = evalNumber(widget['offset_y'] as number | string | undefined, vars)
    const opacity = evalNumber(
      widget['opacity'] as number | string | undefined,
      vars,
      1,
    )
    const rotation = evalNumber(widget['rotation'] as number | string | undefined, vars)

    results.push({
      expanded,
      visible: visible ?? true,
      offsetX: offsetX === null ? 0 : Math.round(offsetX),
      offsetY: offsetY === null ? 0 : Math.round(offsetY),
      opacity: opacity === null ? 1 : opacity,
      rotation: rotation === null ? 0 : rotation,
      raw,
      value01,
      text,
      history,
      error,
    })
  }
  return results
}

/** Source paths referenced by an entry (for data-source pickers). */
export function entrySource(entry: EntryRaw): string | null {
  if (isComponentInstance(entry)) return null
  const source = (entry as WidgetRaw)['source']
  return typeof source === 'string' ? source : null
}
