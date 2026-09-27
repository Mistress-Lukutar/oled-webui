/**
 * YAML parse/serialize for scene documents plus client-side validation
 * mirroring schema.py. The server stays authoritative on save; these
 * checks give instant feedback while typing.
 */

import { Document, parse, parseDocument, stringify, YAMLMap, YAMLSeq } from 'yaml'
import {
  EASINGS,
  WIDGET_TYPES,
  entryRect,
  isComponentInstance,
  isObject,
  unknownDocKeys,
  unknownStyleKeys,
  unknownWidgetKeys,
  widgetType,
} from './types'
import type { EntryRaw, SceneDocumentRaw, WidgetRaw } from './types'

export interface ParseResult {
  doc: SceneDocumentRaw | null
  errors: string[]
}

function fmt(value: unknown): string {
  return typeof value === 'string' ? `"${value}"` : String(value)
}

/** Exclusive-min range check: min < value <= max (mirrors pydantic gt/le). */
function checkRange(
  errors: string[],
  where: string,
  value: unknown,
  min: number,
  max: number | null,
): void {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  if (value <= min) {
    errors.push(`${where}: must be > ${min}, got ${value}`)
  } else if (max !== null && value > max) {
    errors.push(`${where}: must be <= ${max}, got ${value}`)
  }
}

function checkIntRange(
  errors: string[],
  where: string,
  value: unknown,
  min: number,
  max: number,
): void {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  if (value < min || value > max) {
    errors.push(`${where}: must be ${min}..${max}, got ${value}`)
  }
}

function checkEnum(
  errors: string[],
  where: string,
  value: unknown,
  allowed: readonly string[],
): void {
  if (typeof value === 'string' && !allowed.includes(value)) {
    errors.push(`${where}: unknown value ${fmt(value)} (${allowed.join(', ')})`)
  }
}

function checkColor(errors: string[], where: string, value: unknown): void {
  if (typeof value !== 'string') return
  if (!/^#[0-9a-fA-F]{6}$/.test(value)) {
    errors.push(`${where}: expected #RRGGBB color, got ${fmt(value)}`)
  }
}

function checkStyle(
  errors: string[],
  where: string,
  type: (typeof WIDGET_TYPES)[number],
  style: unknown,
): void {
  if (style === undefined) return
  if (!isObject(style)) {
    errors.push(`${where}.style: must be a mapping`)
    return
  }
  for (const key of unknownStyleKeys(style)) {
    errors.push(`${where}.style: unknown key "${key}"`)
  }
  if (type === 'text') {
    checkIntRange(errors, `${where}.style.size`, style['size'], 4, 200)
    checkColor(errors, `${where}.style.color`, style['color'])
  } else if (type === 'bar') {
    checkIntRange(errors, `${where}.style.border`, style['border'], 0, 16)
    checkEnum(errors, `${where}.style.orientation`, style['orientation'], [
      'horizontal',
      'vertical',
    ])
  } else if (type === 'ring') {
    checkIntRange(errors, `${where}.style.width`, style['width'], 1, 64)
    checkIntRange(errors, `${where}.style.start_angle`, style['start_angle'], -360, 360)
    checkIntRange(errors, `${where}.style.sweep`, style['sweep'], 30, 360)
  } else if (type === 'graph') {
    checkIntRange(errors, `${where}.style.line_width`, style['line_width'], 1, 16)
  }
}

function checkEntry(errors: string[], index: number, entry: EntryRaw): void {
  const where = `widgets[${index}]`
  if (isComponentInstance(entry)) {
    const at = entry['at']
    if (at !== undefined && (!Array.isArray(at) || at.length !== 2)) {
      errors.push(`${where}: "at" must be [x, y]`)
    }
    return
  }
  const type = widgetType(entry)
  if (type === null) {
    errors.push(
      `${where}: unknown type ${fmt(entry['type'])} (${WIDGET_TYPES.join(', ')})`,
    )
    return
  }
  const rect = entryRect(entry)
  if (rect === null) {
    errors.push(`${where} (${type}): "rect" [x, y, w, h] is required`)
  } else if (rect[2] < 1 || rect[3] < 1) {
    errors.push(`${where} (${type}): rect width/height must be >= 1`)
  }
  for (const key of unknownWidgetKeys(entry)) {
    errors.push(`${where} (${type}): unknown key "${key}"`)
  }
  if (type !== 'text' && type !== 'image' && typeof entry['source'] !== 'string') {
    errors.push(`${where} (${type}): "source" is required`)
  }
  if (type === 'image') {
    const path = entry['path']
    if (typeof path !== 'string' || path.trim() === '') {
      errors.push(`${where} (image): "path" is required`)
    }
    checkEnum(errors, `${where}.fit`, entry['fit'], ['scale', 'contain', 'cover', 'stretch'])
  }
  checkIntRange(errors, `${where}.history`, entry['history'], 2, 3600)
  checkStyle(errors, where, type, entry['style'])
  const animate = entry['animate']
  if (animate !== undefined) {
    if (!isObject(animate)) {
      errors.push(`${where}.animate: must be a mapping`)
    } else {
      for (const [name, spec] of Object.entries(animate)) {
        if (!isObject(spec)) {
          errors.push(`${where}.animate.${name}: must be a mapping`)
          continue
        }
        checkEnum(errors, `${where}.animate.${name}.easing`, spec['easing'], [
          ...EASINGS,
        ])
        checkRange(errors, `${where}.animate.${name}.duration`, spec['duration'], 0, 10000)
      }
    }
  }
}

function checkDocument(errors: string[], doc: SceneDocumentRaw): void {
  for (const key of unknownDocKeys(doc)) {
    errors.push(`Unknown top-level key "${key}"`)
  }
  checkRange(errors, 'refresh', doc['refresh'], 0, 60)
  checkRange(errors, 'max_fps', doc['max_fps'], 0, 60)
  checkRange(errors, 'keepalive_interval', doc['keepalive_interval'], 0, null)
  checkIntRange(errors, 'brightness', doc['brightness'], 0, 200)
  checkIntRange(errors, 'quality', doc['quality'], 1, 100)

  const background = doc['background']
  if (background !== undefined) {
    if (!Array.isArray(background)) {
      errors.push('background: must be a list')
    } else {
      background.forEach((layer, index) => {
        const where = `background[${index}]`
        if (!isObject(layer)) {
          errors.push(`${where}: must be a mapping`)
          return
        }
        if (typeof layer['path'] !== 'string') {
          errors.push(`${where}: "path" is required`)
        }
        checkRange(errors, `${where}.scale`, layer['scale'], 0, null)
        checkIntRange(errors, `${where}.opacity`, layer['opacity'], 0, 1)
      })
    }
  }

  const widgets = doc['widgets']
  if (widgets !== undefined) {
    if (!Array.isArray(widgets)) {
      errors.push('widgets: must be a list')
    } else {
      widgets.forEach((entry, index) => {
        if (!isObject(entry)) {
          errors.push(`widgets[${index}]: must be a mapping`)
          return
        }
        checkEntry(errors, index, entry as EntryRaw)
      })
    }
  }
}

/** Re-validate an already-parsed document (used after mutations). */
export function validateSceneDoc(doc: SceneDocumentRaw): string[] {
  const errors: string[] = []
  checkDocument(errors, doc)
  return errors
}

/** Parse scene YAML text; null doc means a syntax error. */
export function parseSceneYaml(text: string): ParseResult {
  let raw: unknown
  try {
    raw = parse(text)
  } catch (err) {
    const message = err instanceof Error ? err.message.split('\n')[0] : String(err)
    return { doc: null, errors: [`YAML syntax: ${message}`] }
  }
  if (raw === undefined || raw === null) {
    return { doc: { widgets: [] }, errors: [] }
  }
  if (!isObject(raw)) {
    return { doc: null, errors: ['Scene root must be a YAML mapping'] }
  }
  const doc = raw as SceneDocumentRaw
  const errors: string[] = []
  checkDocument(errors, doc)
  return { doc, errors }
}

/**
 * Serialize the document back to YAML text. Short scalar sequences
 * (rect, at, pos...) are emitted inline in flow style to match the
 * hand-written scene conventions. When the previous YAML text is given,
 * comments are grafted from it (matched structurally by key/index), so
 * header, section and trailing comments survive graphical edits.
 */
export function stringifySceneYaml(doc: SceneDocumentRaw, previousText?: string): string {
  const yamlDoc = new Document(doc as Record<string, unknown>)
  markShortSeqsFlow(yamlDoc.contents as YAMLMap | YAMLSeq | null)
  const regenerated = stringify(yamlDoc, { lineWidth: 120 })
  if (previousText === undefined || previousText.trim() === '') {
    return regenerated
  }
  try {
    const prev = parseDocument(previousText)
    const next = parseDocument(regenerated)
    graftComments(prev.contents as YAMLMap | YAMLSeq | null, next.contents as YAMLMap | YAMLSeq | null)
    if (next.commentBefore === undefined || next.commentBefore === null) {
      next.commentBefore = prev.commentBefore
    }
    return String(next)
  } catch {
    return regenerated
  }
}

function isCollection(node: unknown): node is YAMLMap | YAMLSeq {
  return node instanceof YAMLMap || node instanceof YAMLSeq
}

function markShortSeqsFlow(node: YAMLMap | YAMLSeq | null): void {
  if (node === null) return
  if (node instanceof YAMLSeq) {
    const items = node.items
    if (
      items.length > 0 &&
      items.length <= 8 &&
      items.every((item) => !(item instanceof YAMLMap) && !(item instanceof YAMLSeq))
    ) {
      node.flow = true
    }
    for (const item of items) {
      if (isCollection(item)) markShortSeqsFlow(item)
    }
    return
  }
  if (node instanceof YAMLMap) {
    for (const pair of node.items) {
      if (isCollection(pair.value)) markShortSeqsFlow(pair.value)
    }
  }
}

function keyOf(pair: { key: unknown }): string {
  const key = (pair as { key: { value?: unknown; source?: unknown } }).key
  return String(key?.value ?? key?.source ?? '')
}

type CommentedNode = YAMLMap | YAMLSeq | { commentBefore?: string; comment?: string }

function commented(node: unknown): CommentedNode | undefined {
  return node === undefined || node === null ? undefined : (node as CommentedNode)
}

/** Copy comments from the old CST onto the regenerated CST, best effort. */
function graftComments(
  prev: YAMLMap | YAMLSeq | null,
  next: YAMLMap | YAMLSeq | null,
): void {
  if (prev === null || next === null) return
  if (prev instanceof YAMLMap && next instanceof YAMLMap) {
    const nextByKey = new Map(next.items.map((pair) => [keyOf(pair), pair]))
    for (const prevPair of prev.items) {
      const nextPair = nextByKey.get(keyOf(prevPair))
      if (nextPair === undefined) continue
      const prevKey = commented(prevPair.key)
      const nextKey = commented(nextPair.key)
      const prevValue = commented(prevPair.value)
      const nextValue = commented(nextPair.value)
      if (
        prevKey?.commentBefore !== undefined &&
        nextKey !== undefined &&
        !nextKey.commentBefore
      ) {
        nextKey.commentBefore = prevKey.commentBefore
      }
      if (prevValue?.comment !== undefined && nextValue !== undefined && !nextValue.comment) {
        nextValue.comment = prevValue.comment
      }
      if (isCollection(prevValue) && isCollection(nextValue)) {
        if (prevValue.commentBefore && !nextValue.commentBefore) {
          nextValue.commentBefore = prevValue.commentBefore
        }
        graftComments(prevValue, nextValue)
      }
    }
    return
  }
  if (prev instanceof YAMLSeq && next instanceof YAMLSeq) {
    const count = Math.min(prev.items.length, next.items.length)
    for (let i = 0; i < count; i += 1) {
      const prevItem = commented(prev.items[i])
      const nextItem = commented(next.items[i])
      if (prevItem === undefined || nextItem === undefined) continue
      if (
        prevItem.commentBefore !== undefined &&
        !nextItem.commentBefore
      ) {
        nextItem.commentBefore = prevItem.commentBefore
      }
      if (prevItem.comment !== undefined && !nextItem.comment) {
        nextItem.comment = prevItem.comment
      }
      if (isCollection(prevItem) && isCollection(nextItem)) {
        graftComments(prevItem, nextItem)
      }
    }
  }
}

/** First widget referenced by a value template placeholder, if any. */
export function isWidgetEntry(entry: unknown): entry is WidgetRaw {
  return isObject(entry) && widgetType(entry as EntryRaw) !== null
}
