<script setup lang="ts">
/**
 * Display quick settings panel: connection, power, test pattern and the
 * global output settings (formerly the display settings modal), applied
 * immediately on change.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useDisplayStore } from '../../composables/useDisplayStore'

const props = defineProps<{ deviceId?: string | null }>()
void props

const { state, actions } = useDisplayStore()
const busy = ref(false)

async function withBusy(action: () => Promise<boolean>): Promise<void> {
  busy.value = true
  await action()
  busy.value = false
}

// Local draft of the persisted settings; every change is applied at once.
const draft = reactive({
  keepalive_enabled: true,
  keepalive_interval: 1.5,
  brightness: 100,
  quality: 95,
  blank_on_display_off: false,
})

watch(
  () => state.settings,
  (settings) => {
    Object.assign(draft, settings)
  },
  { immediate: true, deep: true },
)

// Push the whole draft; the server validates and echoes the saved value.
function applySettings(): void {
  void actions.setDisplaySettings({ ...draft })
}

const sceneRunning = computed(() => state.scene.running)
</script>

<template>
  <div class="settings">
    <div class="power">
      <button :disabled="busy || !state.connected" @click="withBusy(actions.powerOff)">
        Off
      </button>
      <button :disabled="busy || !state.connected" @click="withBusy(actions.powerOn)">
        On
      </button>
      <button
        class="primary"
        :disabled="busy || !state.connected"
        @click="withBusy(() => actions.runTest(1.0))"
      >
        Test pattern
      </button>
    </div>

    <label class="field">
      <span class="label">
        Brightness <b class="mono">{{ draft.brightness }}%</b>
      </span>
      <input
        v-model.number="draft.brightness"
        type="range"
        min="0"
        max="200"
        @change="applySettings"
      />
    </label>

    <label class="field">
      <span class="label">
        JPEG quality <b class="mono">{{ draft.quality }}</b>
      </span>
      <input
        v-model.number="draft.quality"
        type="range"
        min="1"
        max="100"
        @change="applySettings"
      />
    </label>

    <label class="check">
      <input
        v-model="draft.keepalive_enabled"
        type="checkbox"
        @change="applySettings"
      />
      <span>Keepalive</span>
    </label>
    <label v-if="draft.keepalive_enabled" class="field nested">
      <span class="label">
        Interval <b class="mono">{{ draft.keepalive_interval.toFixed(1) }} s</b>
      </span>
      <input
        v-model.number="draft.keepalive_interval"
        type="range"
        min="0.1"
        max="10"
        step="0.1"
        @change="applySettings"
      />
    </label>

    <label class="check">
      <input
        v-model="draft.blank_on_display_off"
        type="checkbox"
        @change="applySettings"
      />
      <span>Blank when the Windows display turns off</span>
    </label>

    <p v-if="sceneRunning" class="hint">
      Brightness and quality apply to the running scene immediately.
    </p>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.power {
  display: flex;
  gap: 8px;
}

.power button {
  flex: 1;
  font-size: 12px;
  padding: 6px 8px;
}

.field span.label,
label span.label {
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

.field.nested {
  margin-left: 23px;
}

.check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
</style>
