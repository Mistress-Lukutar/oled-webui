/**
 * Shared keyboard plumbing for canvas editors: typing-target guards and
 * a window keydown helper. Shortcuts match by physical key (event.code)
 * so they work on any keyboard layout.
 */

export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  )
}

export function isFormTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

export interface ShortcutSpec {
  /** Physical key (event.code), e.g. 'KeyC' — layout independent. */
  code?: string
  /** Logical key (event.key), e.g. 'ArrowLeft' — for layouts where it matters. */
  key?: string
  ctrl?: boolean
  shift?: boolean
  /** Match with or without shift for logical-key shortcuts (default: exact). */
  ignoreShift?: boolean
  /** Invoke even while the focus is in a form field (default: never). */
  allowTypingTarget?: boolean
  handler: (event: KeyboardEvent) => void
}

/**
 * Register window-level keydown bindings; returns a detach function.
 * First matching binding wins; matched events are preventDefault-ed.
 */
export function useKeydown(specs: ShortcutSpec[]): () => void {
  const onKeydown = (event: KeyboardEvent): void => {
    for (const spec of specs) {
      if (spec.code !== undefined && event.code !== spec.code) continue
      if (spec.key !== undefined && event.key !== spec.key) continue
      if (spec.ignoreShift !== true && spec.shift === true !== event.shiftKey) continue
      const mod = event.ctrlKey || event.metaKey
      if ((spec.ctrl === true) !== mod) continue
      if (!spec.allowTypingTarget && isTypingTarget(event.target)) return
      event.preventDefault()
      spec.handler(event)
      return
    }
  }
  window.addEventListener('keydown', onKeydown)
  return () => window.removeEventListener('keydown', onKeydown)
}
