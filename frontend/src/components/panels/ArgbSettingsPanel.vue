<script setup lang="ts">
/**
 * ARGB quick settings panel: engine start/stop, brightness/fps/autostart
 * and the effect list. Editing lives in the designer modal opened from
 * here; quick settings push to hardware with a debounce while the engine
 * is running. OpenRGB connection lives in the status panel.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import ArgbEditorModal from '../argb/ArgbEditorModal.vue'
import { useArgbStore } from '../../argb/store'
import type { ArgbLayer, EffectType } from '../../argb/types'

const props = defineProps<{ deviceId?: string | null }>()
void props

const store = useArgbStore()
const { state } = store

const editorOpen = ref(false)

const EFFECT_LABELS: Record<EffectType, string> = {
  fill: 'Fill',
  gradient: 'Gradient',
  rainbow: 'Rainbow',
  breathing: 'Breathing',
  comet: 'Comet',
  scanner: 'Scanner',
  meter: 'Meter',
}

// Layers composite bottom-up; show the stack top-first like the editor.
const layersTopFirst = computed(() => [...state.layout.layers].reverse())

// ---------------------------------------------------------------------
// Quick settings: edits go into the draft; while the engine runs they
// are pushed to hardware soon after the last change. Slider drags are
// one undo entry (batch) and one hardware push (debounce).
// ---------------------------------------------------------------------

const LIVE_APPLY_DELAY = 400
let liveApplyTimer = 0
let sliding = false

function scheduleLiveApply(): void {
  if (!state.status.running) return
  window.clearTimeout(liveApplyTimer)
  liveApplyTimer = window.setTimeout(() => {
    if (state.status.running) void store.actions.apply()
  }, LIVE_APPLY_DELAY)
}

function beginSlide(): void {
  if (sliding) return
  store.beginBatch()
  sliding = true
}

function endSlide(): void {
  if (!sliding) return
  store.endBatch()
  sliding = false
  scheduleLiveApply()
}

function setBrightness(event: Event): void {
  const value = Math.round(Number((event.target as HTMLInputElement).value) || 0)
  store.mutate((layout) => {
    layout.brightness = Math.min(200, Math.max(0, value))
  })
}

function setFps(event: Event): void {
  const value = Math.round(Number((event.target as HTMLInputElement).value) || 30)
  store.mutate((layout) => {
    layout.fps = Math.min(60, Math.max(1, value))
  })
}

function toggleLayer(layer: ArgbLayer): void {
  store.actions.updateLayer(layer.id, { enabled: !layer.enabled })
  scheduleLiveApply()
}

onBeforeUnmount(() => {
  window.clearTimeout(liveApplyTimer)
})
</script>

<template>
  <div class="quick">
    <div class="engine">
      <button
        class="primary"
        :disabled="state.status.running"
        title="Save the layout and run the engine"
        @click="store.actions.apply()"
      >
        ▶ Start
      </button>
      <button :disabled="!state.status.running" @click="store.actions.stop()">
        Stop
      </button>
      <button class="designer" @click="editorOpen = true">✏ Designer</button>
    </div>

    <label class="field">
      <span class="label">
        Brightness <b class="mono">{{ state.layout.brightness }}%</b>
      </span>
      <input
        type="range"
        min="0"
        max="200"
        :value="state.layout.brightness"
        @input="beginSlide(); setBrightness($event)"
        @change="endSlide"
        @pointerup="endSlide"
        @blur="endSlide"
      />
    </label>

    <label class="field">
      <span class="label">
        Frame rate <b class="mono">{{ state.layout.fps }} fps</b>
      </span>
      <input
        type="range"
        min="1"
        max="60"
        :value="state.layout.fps"
        @input="beginSlide(); setFps($event)"
        @change="endSlide"
        @pointerup="endSlide"
        @blur="endSlide"
      />
    </label>

    <label class="check">
      <input
        type="checkbox"
        :checked="state.layout.autostart"
        @change="store.actions.setAutostart(($event.target as HTMLInputElement).checked)"
      />
      <span>Run automatically on server start</span>
    </label>

    <h4>Effects</h4>
    <div
      v-for="layer in layersTopFirst"
      :key="layer.id"
      class="fx-row"
      :class="{ disabled: !layer.enabled }"
    >
      <button
        class="icon"
        :title="layer.enabled ? 'Disable' : 'Enable'"
        @click="toggleLayer(layer)"
      >
        {{ layer.enabled ? '◉' : '○' }}
      </button>
      <span class="name">{{ layer.name }}</span>
      <span class="chip">{{ EFFECT_LABELS[layer.effect.type] }}</span>
    </div>
    <p v-if="state.layout.layers.length === 0" class="hint">
      No effects yet — open the designer to add some.
    </p>

    <p class="hint live-hint">
      While the engine is running, these settings reach the hardware
      immediately after you release the control.
    </p>

    <div class="actions">
      <span class="grow" />
      <button :disabled="!state.dirty" @click="store.actions.save()">Save</button>
    </div>

    <ArgbEditorModal v-if="editorOpen" @close="editorOpen = false" />
    <div v-if="state.error !== null" class="error-toast">{{ state.error }}</div>
  </div>
</template>

<style scoped>
.quick {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.engine {
  display: flex;
  gap: 8px;
}

.engine button {
  flex: 1;
  font-size: 12px;
  padding: 6px 8px;
}

.engine .designer {
  border-color: var(--accent-dim);
  color: var(--accent);
}

h4 {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.field span.label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-weight: 400;
  color: var(--text-dim);
}

.check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.fx-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 13px;
}

.fx-row.disabled .name {
  opacity: 0.45;
}

.fx-row .name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fx-row .chip {
  font-size: 10px;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-dim);
}

.fx-row .icon {
  padding: 1px 5px;
  font-size: 11px;
  line-height: 1.2;
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}

.live-hint {
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.grow {
  flex: 1;
}
</style>
