/**
 * Common-value computation for multi-selection editing. A field is
 * "mixed" when the selected entries hold different values for it;
 * missing keys normalize to the schema default so "all unset" counts
 * as one shared value.
 */

export interface CommonValue {
  /** The shared value, or an arbitrary member's value when mixed. */
  value: unknown
  /** True when the selection holds differing values for the field. */
  mixed: boolean
}

function normalize(value: unknown, def: unknown): unknown {
  return value === undefined || value === null ? def : value
}

/** Common value of a widget-level field across raw entries. */
export function commonFieldValue(
  entries: Array<Record<string, unknown>>,
  key: string,
  def: unknown,
): CommonValue {
  let value: unknown = def
  let mixed = false
  entries.forEach((entry, index) => {
    const current = normalize(entry[key], def)
    if (index === 0) value = current
    else if (current !== value) mixed = true
  })
  return { value, mixed }
}

/** Common value of a style key across style mappings. */
export function commonStyleValue(
  styles: Array<Record<string, unknown>>,
  key: string,
  def: unknown,
): CommonValue {
  let value: unknown = def
  let mixed = false
  styles.forEach((style, index) => {
    const current = normalize(style[key], def)
    if (index === 0) value = current
    else if (current !== value) mixed = true
  })
  return { value, mixed }
}

/** True when every style enables its fill (absent key = enabled). */
export function commonFillOn(styles: Array<Record<string, unknown>>): {
  on: boolean
  mixed: boolean
} {
  let on = true
  let mixed = false
  styles.forEach((style, index) => {
    const current = style['fill'] !== false
    if (index === 0) on = current
    else if (current !== on) mixed = true
  })
  return { on, mixed }
}

/** True when every style draws a stroke of nonzero width. */
export function commonStrokeOn(styles: Array<Record<string, unknown>>): {
  on: boolean
  mixed: boolean
} {
  let on = true
  let mixed = false
  styles.forEach((style, index) => {
    const width = style['stroke_width']
    const current = typeof width === 'number' && Number.isFinite(width) && width > 0
    if (index === 0) on = current
    else if (current !== on) mixed = true
  })
  return { on, mixed }
}

/** True when every style rounds its corners (radius > 0). */
export function commonCornerRounded(styles: Array<Record<string, unknown>>): {
  rounded: boolean
  mixed: boolean
} {
  let rounded = true
  let mixed = false
  styles.forEach((style, index) => {
    const radius = style['radius']
    const current = typeof radius === 'number' && Number.isFinite(radius) && radius > 0
    if (index === 0) rounded = current
    else if (current !== rounded) mixed = true
  })
  return { rounded, mixed }
}
