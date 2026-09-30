/**
 * Per-section UI mapping for the unified scene editor: which canvas,
 * side panels, toolbar extras and statusbar each device section uses.
 * A new device = a new entry here plus its sectionSpecs.ts entry.
 */

import type { Component } from 'vue'
import ArgbCanvas from '../components/argb/ArgbCanvas.vue'
import ArgbInspector from '../components/argb/ArgbInspector.vue'
import ArgbSidePanels from '../components/argb/ArgbSidePanels.vue'
import ArgbStatusbar from '../components/argb/ArgbStatusbar.vue'
import ArgbToolbar from '../components/argb/ArgbToolbar.vue'
import EditorCanvas from '../components/scene-editor/EditorCanvas.vue'
import InspectorPanel from '../components/scene-editor/InspectorPanel.vue'
import SceneLayersPanel from '../components/scene-editor/SceneLayersPanel.vue'

export interface SectionView {
  /** Center design canvas component. */
  canvas: Component
  /** Components stacked in the left aside. */
  left: Component[]
  /** Components stacked in the right aside. */
  right: Component[]
  /** Extra toolbar controls rendered when the section is active. */
  toolbar: Component | null
  /** Statusbar content; null keeps the shared screen statusbar. */
  status: Component | null
  leftWidth: string
  rightWidth: string
}

export const SECTION_VIEWS: Record<string, SectionView> = {
  screen: {
    canvas: EditorCanvas,
    left: [SceneLayersPanel],
    right: [InspectorPanel],
    toolbar: null,
    status: null,
    leftWidth: '210px',
    rightWidth: '250px',
  },
  argb: {
    canvas: ArgbCanvas,
    left: [ArgbSidePanels],
    right: [ArgbInspector],
    toolbar: ArgbToolbar,
    status: ArgbStatusbar,
    leftWidth: '292px',
    rightWidth: '280px',
  },
}
