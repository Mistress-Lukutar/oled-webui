<script setup lang="ts">
/**
 * ARGB panel: connection/engine status, the active scene's effect list
 * and the Designer button. The lighting state lives in the active
 * scene's ``argb`` section; editing happens in the unified scene editor
 * opened on the ARGB tab.
 */
import { computed, ref } from 'vue'
import SceneEditorModal from '../scene-editor/SceneEditorModal.vue'
import { useArgbStore } from '../../argb/store'
import type { EffectType } from '../../argb/types'
import { useDisplayStore } from '../../composables/useDisplayStore'

const props = defineProps<{ deviceId?: string | null }>()
void props

const store = useArgbStore()
const { state } = store
const display = useDisplayStore()

const editorOpen = ref(false)
const editSceneId = ref<string | null>(null)

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

const activeScene = computed(() => display.state.scene)

function openDesigner(): void {
  const sceneId = activeScene.value.scene_id
  if (sceneId === null) {
    store.showError(
      'No active scene — apply or create one in the Scenes panel first; the lighting state lives in a scene file',
    )
    return
  }
  editSceneId.value = sceneId
  editorOpen.value = true
}
</script>

<template>
  <div class="quick">
    <div class="status">
      <span
        class="dot"
        :class="{ on: state.status.connected, run: state.status.running }"
        :title="state.status.connected ? 'OpenRGB connected' : 'OpenRGB not connected'"
      />
      <span class="status-text">
        <template v-if="state.status.running">
          Engine running @ {{ state.status.fps }} fps · {{ state.status.frames_sent }} frames
        </template>
        <template v-else-if="state.status.connected">
          OpenRGB connected · {{ state.status.zones.length }} zones · engine stopped
        </template>
        <template v-else>OpenRGB not connected</template>
      </span>
      <button
        v-if="state.status.connected"
        class="small"
        @click="store.actions.disconnect()"
      >
        Disconnect
      </button>
      <button v-else class="small" @click="store.actions.connect()">Connect</button>
    </div>

    <p v-if="activeScene.running" class="hint">
      Active scene: <b>{{ activeScene.name }}</b> — its <code>argb:</code> section
      drives the lighting.
    </p>
    <p v-else class="hint">
      No active scene. Apply a scene with an <code>argb:</code> section to start
      the lighting engine.
    </p>

    <button class="designer" @click="openDesigner">✏ Designer</button>

    <h4>Effects (active layout)</h4>
    <div
      v-for="layer in layersTopFirst"
      :key="layer.id"
      class="fx-row"
      :class="{ disabled: !layer.enabled }"
    >
      <span class="icon">{{ layer.enabled ? '◉' : '○' }}</span>
      <span class="name">{{ layer.name }}</span>
      <span class="chip">{{ EFFECT_LABELS[layer.effect.type] }}</span>
    </div>
    <p v-if="state.layout.layers.length === 0" class="hint">
      No effects in the active layout — open the designer to add some.
    </p>

    <SceneEditorModal
      v-if="editorOpen && editSceneId !== null"
      :scene-id="editSceneId"
      initial-section="argb"
      @close="editorOpen = false"
      @saved="store.actions.refreshStatus()"
    />
    <div v-if="state.error !== null" class="error-toast">{{ state.error }}</div>
  </div>
</template>

<style scoped>
.quick {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.status-text {
  flex: 1;
  color: var(--text-dim);
}

.status .small {
  font-size: 11px;
  padding: 2px 8px;
}

.dot {
  width: 9px;
  height: 9px;
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

.designer {
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
  font-size: 11px;
  color: var(--text-dim);
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}

code {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
}

.error-toast {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 60;
  background: var(--bg-panel);
  border: 1px solid var(--danger);
  border-radius: var(--radius);
  color: var(--danger);
  padding: 10px 14px;
  font-size: 12px;
  max-width: 380px;
}
</style>
