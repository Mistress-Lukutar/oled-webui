<script setup lang="ts">
/**
 * ARGB device tab: toolbar, workspace canvas, layers and inspector.
 */
import { onMounted } from 'vue'
import ArgbCanvas from './ArgbCanvas.vue'
import ArgbInspector from './ArgbInspector.vue'
import ArgbLayers from './ArgbLayers.vue'
import { useArgbStore } from '../../argb/store'
import type { DeviceType } from '../../argb/types'

const store = useArgbStore()
const { state } = store

onMounted(() => {
  void store.actions.init()
})

function num(event: Event): number {
  return Number((event.target as HTMLInputElement).value) || 0
}

function setBrightness(event: Event): void {
  store.mutate((layout) => {
    layout.brightness = Math.min(200, Math.max(0, Math.round(num(event))))
  })
}
</script>

<template>
  <section class="argb">
    <div class="toolbar">
      <span class="label">Add:</span>
      <button @click="store.actions.addDevice('strip' as DeviceType)">+ Strip</button>
      <button @click="store.actions.addDevice('ring' as DeviceType)">+ Ring fan</button>
      <button @click="store.actions.addDevice('ring_stripes' as DeviceType)">+ Dual-ring fan</button>

      <span class="sep" />
      <label class="slider">
        <span class="label">Brightness</span>
        <input
          type="range"
          min="0"
          max="200"
          :value="state.layout.brightness"
          @input="setBrightness"
        />
        <span class="mono">{{ state.layout.brightness }}%</span>
      </label>

      <span class="sep" />
      <span
        class="dot"
        :class="{ on: state.status.connected, run: state.status.running }"
        :title="state.status.connected ? 'OpenRGB connected' : 'OpenRGB not connected'"
      />
      <span class="status-text">
        {{
          state.status.connected
            ? `${state.status.controller ?? 'OpenRGB'} · ${state.status.zones.length} zones`
            : 'OpenRGB not connected'
        }}
        <template v-if="state.status.running"> · running @ {{ state.status.fps }} fps</template>
      </span>
      <button @click="store.actions.connect()" :disabled="state.status.connected">
        Connect
      </button>
      <button @click="store.actions.disconnect()" :disabled="!state.status.connected">
        Disconnect
      </button>

      <span class="grow" />
      <span v-if="state.dirty" class="dirty" title="Unsaved changes">● unsaved</span>
      <button :disabled="!store.canUndo()" title="Undo (Ctrl+Z)" @click="store.undo()">⟲</button>
      <button :disabled="!store.canRedo()" title="Redo (Ctrl+Shift+Z)" @click="store.redo()">⟳</button>
      <button @click="store.actions.save()">Save</button>
      <button class="primary" @click="store.actions.apply()">▶ Apply</button>
      <button @click="store.actions.stop()" :disabled="!state.status.running">Stop</button>
    </div>

    <div class="workarea">
      <div class="canvas-holder">
        <ArgbCanvas />
      </div>
      <aside class="side">
        <div class="card">
          <ArgbLayers />
        </div>
        <div class="card grow">
          <ArgbInspector />
        </div>
      </aside>
    </div>

    <div v-if="state.error !== null" class="error-toast">{{ state.error }}</div>
  </section>
</template>

<style scoped>
.argb {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-panel);
}

.label {
  font-size: 12px;
  color: var(--text-dim);
}

.sep {
  width: 1px;
  height: 22px;
  background: var(--border);
}

.grow {
  flex: 1;
}

.slider {
  display: flex;
  align-items: center;
  gap: 6px;
}

.slider input {
  width: 110px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--danger);
  flex: none;
}

.dot.on {
  background: var(--accent);
}

.dot.run {
  box-shadow: 0 0 6px var(--accent);
}

.status-text {
  font-size: 12px;
  color: var(--text-dim);
}

.dirty {
  color: var(--warning);
  font-size: 12px;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.workarea {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 12px;
  min-height: 480px;
}

@media (max-width: 900px) {
  .workarea {
    grid-template-columns: 1fr;
  }
}

.canvas-holder {
  min-height: 480px;
  border-radius: var(--radius);
}

.side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.side .card {
  padding: 10px;
}

.side .card.grow {
  flex: 1;
  min-height: 0;
}
</style>
