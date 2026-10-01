/**
 * Shared field helpers for the inspector panels: a safe number reader
 * and "write or drop at default" setters used by both the single- and
 * multi-selection inspectors. The setters take the write function as a
 * callback so each panel keeps its own apply semantics (single entry
 * vs. apply-to-all in one undo step).
 */

/** Write callback for a style field; `undefined` drops the key. */
export type StyleSetter = (key: string, value: unknown) => void

/** Read a number, falling back when missing or not finite. */
export function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

/** Write a numeric style field, dropping the key at the schema default. */
export function numOrDrop(
  set: StyleSetter,
  key: string,
  raw: string,
  def: number,
  int = false,
): void {
  const value = Number(raw)
  if (!Number.isFinite(value) || value === def) {
    set(key, undefined)
    return
  }
  set(key, int ? Math.trunc(value) : value)
}

/** Write an enum/text style field, dropping the key at the schema default. */
export function strOrDrop(
  set: StyleSetter,
  key: string,
  value: string,
  def: string,
): void {
  set(key, value === def ? undefined : value)
}
