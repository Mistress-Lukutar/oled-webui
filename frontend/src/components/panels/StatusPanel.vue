<script setup lang="ts">
/**
 * Status panel: compact connection summary for every registered device
 * plus the currently running scene. Replaces the old header status bar.
 */
import { computed, ref } from 'vue'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { useArgbStore } from '../../argb/store'
import { usePanelsStore } from '../../composables/usePanelsStore'

const { state: displayState, actions } = useDisplayStore()
const argb = useArgbStore()
const { state: panelsState } = usePanelsStore()

const busyRow = ref<string | null>(null)

async function toggleRow(row: { id: string; toggle: () => Promise<boolean> }): Promise<void> {
  busyRow.value = row.id
  try {
    await row.toggle()
  } finally {
    busyRow.value = null
  }
}

interface Row {
  id: string
  name: string
  connected: boolean
  detail: string
  connectable: boolean
  toggle: () => Promise<boolean>
  connecting?: boolean
}

const displayRow = computed<Row>(() => ({
  id: 'display:0',
  name: displayState.device
    ? `${displayState.device.vid.toString(16).toUpperCase().padStart(4, '0')}:${displayState.device.pid.toString(16).toUpperCase().padStart(4, '0')} · ${displayState.device.resolution.width}×${displayState.device.resolution.height}`
    : 'OLED display',
  connected: displayState.connected,
  detail: displayState.connected ? 'USB connected' : 'USB not connected',
  connectable: true,
  toggle: () => (displayState.connected ? actions.disconnect() : actions.connect()),
}))

const argbRow = computed<Row>(() => ({
  id: 'argb:openrgb',
  name: 'ARGB · OpenRGB',
  connected: argb.state.status.connected,
  detail: argb.state.status.running
    ? `Running @ ${argb.state.status.fps} fps`
    : argb.state.status.connected
      ? `${argb.state.status.zones.length} zones`
      : 'SDK not connected',
  connectable: true,
  toggle: () =>
    argb.state.status.connected
      ? argb.actions.disconnect()
      : argb.actions.connect(),
}))

const deviceNames = computed(() => {
  const map = new Map<string, string>()
  for (const device of panelsState.devices) map.set(device.id, device.name)
  return map
})

function rowName(row: Row): string {
  return deviceNames.value.get(row.id) ?? row.name
}
</script>

<template>
  <div class="status-grid">
    <div v-for="row in [displayRow, argbRow]" :key="row.id" class="row">
      <span class="dot" :class="{ up: row.connected }" />
      <div class="texts">
        <span class="name">{{ rowName(row) }}</span>
        <span class="detail">{{ row.detail }}</span>
      </div>
      <button
        class="small"
        :disabled="busyRow === row.id"
        @click="toggleRow(row)"
      >
        {{ busyRow === row.id ? '…' : row.connected ? 'Disconnect' : 'Connect' }}
      </button>
    </div>

    <div class="row scene">
      <span class="dot" :class="{ up: displayState.scene.running }" />
      <div class="texts">
        <span class="name">
          {{ displayState.scene.running ? `Scene: ${displayState.scene.name}` : 'Scene idle' }}
        </span>
        <span v-if="displayState.scene.running" class="detail">
          {{ displayState.scene.refresh }} Hz · {{ displayState.scene.max_fps }} fps max ·
          {{ displayState.scene.frames_sent }} frames sent
        </span>
      </div>
      <button v-if="displayState.scene.running" class="small" @click="actions.stopScene()">
        Stop
      </button>
    </div>
  </div>
</template>

<style scoped>
.status-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.row.scene {
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--danger);
  flex: none;
}

.dot.up {
  background: var(--accent);
}

.texts {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail {
  font-size: 12px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

button.small {
  font-size: 12px;
  padding: 3px 10px;
  flex: none;
}
</style>
