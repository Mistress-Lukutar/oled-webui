<script setup lang="ts">
/**
 * Dashboard grid: renders the persisted panel layout, wires each panel
 * to its component and implements drag-and-drop reordering.
 */
import { ref } from 'vue'
import PanelShell from './PanelShell.vue'
import StatusPanel from './StatusPanel.vue'
import DisplayPreviewPanel from './DisplayPreviewPanel.vue'
import DisplaySettingsPanel from './DisplaySettingsPanel.vue'
import ScenesPanel from './ScenesPanel.vue'
import ArgbPreviewPanel from './ArgbPreviewPanel.vue'
import ArgbSettingsPanel from './ArgbSettingsPanel.vue'
import { usePanelsStore } from '../../composables/usePanelsStore'
import { PANEL_DEFS, isPanelType } from '../../panels/registry'

const { state, deviceById, removePanel, reorderPanel, cycleSpan } = usePanelsStore()

const COMPONENTS = {
  status: StatusPanel,
  'display-preview': DisplayPreviewPanel,
  'display-settings': DisplaySettingsPanel,
  scenes: ScenesPanel,
  'argb-preview': ArgbPreviewPanel,
  'argb-settings': ArgbSettingsPanel,
} as const

const dragId = ref<string | null>(null)
const overId = ref<string | null>(null)

function onDragStart(id: string): void {
  dragId.value = id
}

function onDragEnter(id: string): void {
  overId.value = id
}

function onDrop(id: string): void {
  const targetIndex = state.panels.findIndex((panel) => panel.id === id)
  if (dragId.value !== null && targetIndex >= 0) {
    reorderPanel(dragId.value, targetIndex)
  }
  dragId.value = null
  overId.value = null
}

function onDragEnd(): void {
  dragId.value = null
  overId.value = null
}
</script>

<template>
  <main class="dashboard">
    <template v-for="panel in state.panels" :key="panel.id">
      <PanelShell
        v-if="isPanelType(panel.type)"
        :title="PANEL_DEFS[panel.type].title"
        :subtitle="deviceById(panel.device)?.name ?? null"
        :span="panel.span"
        draggable
        :class="{ 'drop-target': overId === panel.id && dragId !== panel.id }"
        @remove="removePanel(panel.id)"
        @cycle-span="cycleSpan(panel.id)"
        @drag-start="onDragStart(panel.id)"
        @drag-enter="onDragEnter(panel.id)"
        @drop-on="onDrop(panel.id)"
        @drag-end="onDragEnd"
      >
        <div v-if="panel.device !== null && deviceById(panel.device) === null" class="missing">
          Device is not available
        </div>
        <component v-else :is="COMPONENTS[panel.type]" :device-id="panel.device" />
      </PanelShell>
    </template>
  </main>
</template>

<style scoped>
.dashboard {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

@media (max-width: 1100px) {
  .dashboard {
    grid-template-columns: minmax(0, 1fr);
  }
}

.drop-target {
  outline: 2px dashed var(--accent-dim);
  outline-offset: 2px;
}

.missing {
  color: var(--text-dim);
  font-size: 13px;
  padding: 12px 0;
}
</style>
