/**
 * Panel type registry: metadata per dashboard panel type. Pure data —
 * component wiring lives in DashboardGrid, store logic in usePanelsStore.
 */

export type PanelType =
  | 'status'
  | 'display-preview'
  | 'display-settings'
  | 'scenes'
  | 'argb-preview'
  | 'argb-settings'

export interface PanelDef {
  /** Panel title shown in the shell header. */
  title: string
  /** Grid columns the panel occupies when first placed (1..3). */
  defaultSpan: number
  /** Device registry kind the panel attaches to, or null for singletons. */
  deviceKind: 'display' | 'argb' | null
}

export const PANEL_DEFS: Record<PanelType, PanelDef> = {
  status: { title: 'Status', defaultSpan: 3, deviceKind: null },
  'display-preview': { title: 'Display preview', defaultSpan: 2, deviceKind: 'display' },
  'display-settings': { title: 'Display settings', defaultSpan: 1, deviceKind: 'display' },
  scenes: { title: 'Scenes', defaultSpan: 2, deviceKind: 'display' },
  'argb-preview': { title: 'ARGB preview', defaultSpan: 2, deviceKind: 'argb' },
  'argb-settings': { title: 'ARGB settings', defaultSpan: 1, deviceKind: 'argb' },
}

export function isPanelType(value: string): value is PanelType {
  return Object.prototype.hasOwnProperty.call(PANEL_DEFS, value)
}
