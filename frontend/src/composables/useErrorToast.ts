/**
 * Shared error-toast plumbing: one implementation of the self-clearing
 * error message and the `wrap` helper around async actions, used by
 * both singleton stores. The messages render as the global
 * `.error-toast` (App.vue); `errMsg` normalizes thrown values.
 */

/** Human-readable message from a thrown value. */
export function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export interface ErrorChannel {
  showError: (message: string) => void
  /** Run an async action; on failure show the error and return false. */
  wrap: (action: () => Promise<void>) => Promise<boolean>
}

/**
 * Create an error channel that reports into the given sink (usually
 * `state.error = message` on a store's reactive state).
 */
export function createErrorChannel(
  setError: (message: string | null) => void,
  clearAfterMs = 5000,
): ErrorChannel {
  // Track the latest message so an older timeout never clears a newer error.
  let current: string | null = null

  function showError(message: string): void {
    current = message
    setError(message)
    window.setTimeout(() => {
      if (current === message) {
        current = null
        setError(null)
      }
    }, clearAfterMs)
  }

  async function wrap(action: () => Promise<void>): Promise<boolean> {
    try {
      await action()
      return true
    } catch (err) {
      showError(errMsg(err))
      return false
    }
  }

  return { showError, wrap }
}
