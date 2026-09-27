<script setup lang="ts">
/**
 * Display settings modal: keepalive, global brightness, JPEG quality and
 * the "blank panel when Windows display powers off" energy-saving option.
 */
import { reactive, ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const emit = defineEmits<{ close: [] }>()
const { state, actions } = useDisplayStore()

const draft = reactive({ ...state.settings })
const saving = ref(false)

async function apply(): Promise<void> {
  saving.value = true
  const ok = await actions.setDisplaySettings({ ...draft })
  saving.value = false
  if (ok) emit('close')
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal card">
      <div class="head">
        <h2>Display settings</h2>
        <button class="close" title="Close" @click="emit('close')">×</button>
      </div>

      <div class="body">
        <div class="field">
          <label class="check">
            <input v-model="draft.keepalive_enabled" type="checkbox" />
            <span>Keepalive (auto-refresh the last frame)</span>
          </label>
          <p class="hint">
            The panel reverts to its built-in logo after a few seconds
            without frames; keepalive resends the current frame to prevent
            that.
          </p>
        </div>

        <div v-if="draft.keepalive_enabled" class="field">
          <label>Keepalive interval: {{ draft.keepalive_interval.toFixed(1) }} s</label>
          <input
            v-model.number="draft.keepalive_interval"
            type="range"
            min="0.1"
            max="10"
            step="0.1"
          />
        </div>

        <div class="field">
          <label>Brightness: {{ draft.brightness }}%</label>
          <input v-model.number="draft.brightness" type="range" min="0" max="200" />
          <p class="hint">Global output brightness for anything shown on the panel.</p>
        </div>

        <div class="field">
          <label>JPEG quality: {{ draft.quality }}</label>
          <input v-model.number="draft.quality" type="range" min="1" max="100" />
          <p class="hint">
            Encoding quality of frames sent over USB. Lower quality means
            smaller, faster frames.
          </p>
        </div>

        <div class="field">
          <label class="check">
            <input v-model="draft.blank_on_display_off" type="checkbox" />
            <span>Blank panel when the Windows display turns off</span>
          </label>
          <p class="hint">
            Power saving: when Windows switches its display off, a black
            frame is sent to the panel; the content is restored
            automatically when the display turns back on.
          </p>
        </div>
      </div>

      <div class="actions">
        <button class="primary" :disabled="saving" @click="apply">
          {{ saving ? 'Applying…' : 'Apply' }}
        </button>
        <button @click="emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}

.modal {
  width: 440px;
  max-width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 0;
}

.head h2 {
  margin: 0;
}

.close {
  font-size: 16px;
  line-height: 1;
  padding: 4px 10px;
}

.body {
  padding: 12px 16px;
  overflow-y: auto;
}

.field {
  margin-bottom: 14px;
}

.field > label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
}

.check {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.check input {
  width: auto;
}

.hint {
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.45;
  margin: 6px 0 0;
}

.actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 0 16px 16px;
}
</style>
