/**
 * Client-side component expansion, a port of the relevant parts of
 * src/oled_webui/scene/loader.py. Turns `use:` instances into concrete
 * widget mappings for canvas rendering and tracks which raw document
 * entry each expanded widget came from (needed to map selections back).
 */

import { parse } from 'yaml'
import { isObject } from './types'
import type { SceneDocumentRaw, WidgetRaw } from './types'

// Instance-level keys consumed by the loader itself; everything else in a
// `use:` block is treated as a component parameter.
const RESERVED_KEYS = new Set([
  'use',
  'at',
  'animate',
  'visible',
  'offset_x',
  'offset_y',
  'opacity',
  'rotation',
])

// Keys copied from the instance block into every rendered child that does
// not define the key itself.
const OVERRIDE_KEYS = [
  'animate',
  'visible',
  'offset_x',
  'offset_y',
  'opacity',
  'rotation',
] as const

const PLACEHOLDER = /\{\{\s*([A-Za-z_]\w*(?:\.\w+)*)\s*\}\}/g
const MAX_COMPONENT_DEPTH = 8

export interface ExpandedEntry {
  widget: WidgetRaw
  /** Index of the raw doc.widgets entry this widget came from. */
  sourceIndex: number
}

export interface ExpansionResult {
  entries: ExpandedEntry[]
  /** Per-instance problems (missing component, bad params). */
  errors: string[]
}

/** Parsed component definitions keyed by component name. */
export type ComponentMap = Record<string, string>

interface ParsedComponent {
  params: Record<string, unknown>
  render: unknown[]
}

function parseComponent(name: string, text: string): ParsedComponent {
  const raw = parse(text) as unknown
  if (!isObject(raw)) throw new Error(`component "${name}": root must be a mapping`)
  const params = (raw['params'] ?? {}) as unknown
  const render = raw['render']
  if (!isObject(params)) throw new Error(`component "${name}": 'params' must be a mapping`)
  if (!Array.isArray(render) || render.length === 0) {
    throw new Error(`component "${name}": 'render' must be a non-empty list`)
  }
  return { params: params as Record<string, unknown>, render }
}

function lookup(params: Record<string, unknown>, path: string): unknown {
  let value: unknown = params
  for (const part of path.split('.')) {
    if (isObject(value) && part in value) {
      value = value[part]
    } else {
      throw new Error(`Undefined component parameter "${path}"`)
    }
  }
  return value
}

function substitute(node: unknown, params: Record<string, unknown>): unknown {
  if (typeof node === 'string') {
    const trimmed = node.trim()
    const single = trimmed.match(/^\{\{\s*([A-Za-z_]\w*(?:\.\w+)*)\s*\}\}$/)
    if (single) return lookup(params, single[1]!)
    return node.replace(PLACEHOLDER, (_match, path: string) =>
      String(lookup(params, path)),
    )
  }
  if (Array.isArray(node)) return node.map((item) => substitute(item, params))
  if (isObject(node)) {
    const out: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(node)) {
      out[key] = substitute(value, params)
    }
    return out
  }
  return node
}

function shiftRect(rect: unknown, dx: number, dy: number): unknown {
  if (!Array.isArray(rect) || rect.length !== 4) return rect
  const [x, y, w, h] = rect.map((v) => Math.trunc(Number(v)))
  return [x + dx, y + dy, w, h]
}

/**
 * Expand the document's widget list into concrete widgets.
 *
 * Errors are collected per entry (and the entry skipped) so a broken
 * component does not blind the whole editor; the YAML view still shows
 * the raw source for fixing.
 */
export function expandDocument(
  doc: SceneDocumentRaw,
  components: ComponentMap,
): ExpansionResult {
  const entries: ExpandedEntry[] = []
  const errors: string[] = []
  const widgets = doc.widgets ?? []

  const expandList = (list: unknown[], depth: number, sourceIndex: number): void => {
    if (depth > MAX_COMPONENT_DEPTH) {
      errors.push(`widgets[${sourceIndex}]: component nesting too deep`)
      return
    }
    for (const item of list) {
      if (!isObject(item)) {
        errors.push(`widgets[${sourceIndex}]: entry must be a mapping`)
        continue
      }
      const use = item['use']
      if (typeof use !== 'string') {
        entries.push({ widget: item as WidgetRaw, sourceIndex })
        continue
      }
      const source = components[use]
      if (source === undefined) {
        errors.push(`widgets[${sourceIndex}]: component "${use}" not found`)
        continue
      }
      let component: ParsedComponent
      try {
        component = parseComponent(use, source)
      } catch (err) {
        errors.push(`widgets[${sourceIndex}]: ${(err as Error).message}`)
        continue
      }

      const overrides: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(item)) {
        if (!RESERVED_KEYS.has(key)) overrides[key] = value
      }
      const merged: Record<string, unknown> = { ...component.params }
      let badParam = false
      for (const [key, value] of Object.entries(overrides)) {
        if (!(key in merged)) {
          errors.push(
            `widgets[${sourceIndex}]: component "${use}" got unknown parameter "${key}"`,
          )
          badParam = true
          break
        }
        merged[key] = value
      }
      if (badParam) continue

      const at = item['at']
      const dx = Array.isArray(at) && at.length === 2 ? Math.trunc(Number(at[0]) || 0) : 0
      const dy = Array.isArray(at) && at.length === 2 ? Math.trunc(Number(at[1]) || 0) : 0

      try {
        const children = substitute(component.render, merged) as unknown[]
        children.forEach((rawChild, childIndex) => {
          if (!isObject(rawChild)) {
            errors.push(
              `widgets[${sourceIndex}]: component "${use}" render[${childIndex}] must be a mapping`,
            )
            return
          }
          const child: Record<string, unknown> = { ...rawChild }
          child['rect'] = shiftRect(child['rect'], dx, dy)
          for (const key of OVERRIDE_KEYS) {
            if (key in item && !(key in child)) child[key] = item[key]
          }
          // Components may nest further `use:` references.
          if ('use' in child) {
            expandList([child], depth + 1, sourceIndex)
          } else {
            entries.push({ widget: child as WidgetRaw, sourceIndex })
          }
        })
      } catch (err) {
        errors.push(`widgets[${sourceIndex}]: ${(err as Error).message}`)
      }
    }
  }

  widgets.forEach((entry, index) => expandList([entry as unknown], 0, index))
  return { entries, errors }
}
