/**
 * Shared viewport view state (zoom/pan) so other panels (e.g. widget
 * insertion) can compute what the user is currently looking at.
 */

import { reactive } from 'vue'

export const viewState = reactive({
  zoom: 1,
  panX: 0,
  panY: 0,
})

/** Center of the visible canvas area in scene coordinates. */
export function viewCenter(panelWidth: number, panelHeight: number): {
  x: number
  y: number
} {
  return {
    x: panelWidth / 2 - viewState.panX / viewState.zoom,
    y: panelHeight / 2 - viewState.panY / viewState.zoom,
  }
}
