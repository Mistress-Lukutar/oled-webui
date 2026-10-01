<script setup lang="ts">
/**
 * Display quick settings panel: the Designer shortcut and the global
 * output settings (formerly the display settings modal), applied
 * immediately on change. Manual power on/off is gone — blanking follows
 * the Windows display power when the setting below is enabled.
 */
import { computed, reactive, ref, watch } from 'vue'
import SceneEditorModal from '../scene-editor/SceneEditorModal.vue'
import { useDisplayStore } from '../../composables/useDisplayStore'

const props = defineProps<{ deviceId?: string | null }>()
void props

const { state, actions, showError } = useDisplayStore()

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

const editorOpen = ref(false)
const editSceneId = ref<string | null>(null)

function openDesigner(): void {
  const sceneId = state.scene.scene_id
  if (sceneId === null) {
    showError(
      'No active scene — apply or create one in the Scenes panel first; the screen layout lives in a scene file',
    )
    return
  }
  editSceneId.value = sceneId
  editorOpen.value = true
}
</script>

<template>
  <div class="settings">
    <label class="check">
      <input
        v-model="draft.blank_on_display_off"
        type="checkbox"
        @change="applySettings"
      />
      <span>Blank when the Windows display turns off</span>
    </label>

    <div class="actions">
      <button class="designer" @click="openDesigner">✏ Designer</button>
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

    <p v-if="sceneRunning" class="hint">
      Brightness and quality apply to the running scene immediately.
    </p>

    <SceneEditorModal
      v-if="editorOpen && editSceneId !== null"
      :scene-id="editSceneId"
      initial-section="screen"
      @close="editorOpen = false"
    />
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.actions {
  display: flex;
  gap: 8px;
}

.actions button {
  flex: 1;
  font-size: 12px;
  padding: 6px 8px;
}

.designer {
  border-color: var(--accent-dim);
  color: var(--accent);
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
