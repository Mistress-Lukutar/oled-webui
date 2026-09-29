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
  /** Width/height estimate used by the masonry layout until the panel's
   * real rendered height is measured. */
  defaultAspect: number
  /** Device registry kind the panel attaches to, or null for singletons. */
  deviceKind: 'display' | 'argb' | null
}

export const PANEL_DEFS: Record<PanelType, PanelDef> = {
  status: { title: 'Status', defaultAspect: 2.4, deviceKind: null },
  'display-preview': { title: 'Display preview', defaultAspect: 1.6, deviceKind: 'display' },
  'display-settings': { title: 'Display settings', defaultAspect: 0.75, deviceKind: 'display' },
  scenes: { title: 'Scenes', defaultAspect: 0.85, deviceKind: 'display' },
  'argb-preview': { title: 'ARGB preview', defaultAspect: 1.0, deviceKind: 'argb' },
  'argb-settings': { title: 'ARGB settings', defaultAspect: 0.7, deviceKind: 'argb' },
}

export function isPanelType(value: string): value is PanelType {
  return Object.prototype.hasOwnProperty.call(PANEL_DEFS, value)
}
