<script setup lang="ts">
/**
 * Scene tab: library of stored YAML scenes. Editing happens in the
 * full-screen scene editor modal (scene-editor/SceneEditorModal.vue).
 */
import { ref } from 'vue'
import { API } from '../api'
import { useDisplayStore } from '../composables/useDisplayStore'
import FileDropZone from './FileDropZone.vue'
import SceneEditorModal from './scene-editor/SceneEditorModal.vue'

const { state, actions, showError } = useDisplayStore()

const editingId = ref<string | null>(null)

const newName = ref('')
const creating = ref(false)
const uploading = ref(false)

const applyingId = ref<string | null>(null)

const uploadFile = ref<File | null>(null)

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

function onSaved(): void {
  void actions.loadScenes()
}

async function createScene(): Promise<void> {
  const name = newName.value.trim()
  if (name === '') return
  creating.value = true
  try {
    const detail = await API.createScene(name)
    await actions.loadScenes()
    newName.value = ''
    editingId.value = detail.scene.id
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  creating.value = false
}

async function addExample(): Promise<void> {
  creating.value = true
  try {
    const detail = await API.seedExampleScene()
    await actions.loadScenes()
    editingId.value = detail.scene.id
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  creating.value = false
}

async function uploadSceneFile(): Promise<void> {
  const file = uploadFile.value
  if (file === null) return
  const name = file.name.replace(/\.(yaml|yml)$/i, '') || 'Uploaded scene'
  uploading.value = true
  try {
    const detail = await API.createScene(name, file)
    await actions.loadScenes()
    uploadFile.value = null
    editingId.value = detail.scene.id
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  uploading.value = false
}

async function apply(id: string): Promise<void> {
  applyingId.value = id
  await actions.applyScene(id)
  applyingId.value = null
}
</script>

<template>
  <div>
    <div v-if="state.scene.running" class="running card">
      <div class="row">
        <span class="badge active">Running</span>
        <span class="file">{{ state.scene.name }}</span>
      </div>
      <div class="meta">
        {{ state.scene.refresh }} Hz · {{ state.scene.max_fps }} fps max ·
        {{ state.scene.frames_sent }} frames sent
      </div>
      <button class="danger" @click="actions.stopScene()">Stop scene</button>
    </div>

    <div class="create-row">
      <input
        v-model="newName"
        type="text"
        placeholder="New scene name…"
        maxlength="100"
        @keyup.enter="createScene"
      />
      <button
        class="primary"
        :disabled="newName.trim() === '' || creating"
        @click="createScene"
      >
        New
      </button>
      <button :disabled="creating" @click="addExample">Add example</button>
    </div>

    <FileDropZone
      v-model="uploadFile"
      accept=".yaml,.yml,text/yaml,application/yaml"
      :mime-types="['text/yaml', 'application/yaml']"
      :extensions="['.yaml', '.yml']"
      title="Drop a scene .yaml here"
      hint="or click to browse · creates a new scene from the file"
      formats="YAML"
      @update:model-value="uploadSceneFile"
    />

    <div v-if="state.scenes.length === 0" class="empty">
      No scenes yet. Create one, upload a .yaml file or add the bundled example.
    </div>

    <ul v-else class="list">
      <li v-for="scene in state.scenes" :key="scene.id" class="item">
        <div class="info">
          <span class="name">{{ scene.name }}</span>
          <span class="badge" :class="{ active: state.scene.running && state.scene.scene_id === scene.id }">
            {{ scene.widget_count }} widgets
          </span>
          <span class="time">{{ formatTime(scene.updated_at) }}</span>
        </div>
        <div class="actions">
          <button
            class="primary"
            :disabled="!state.connected || applyingId === scene.id"
            @click="apply(scene.id)"
          >
            {{ applyingId === scene.id ? '…' : 'Apply' }}
          </button>
          <button @click="editingId = scene.id">Edit</button>
          <button class="danger" @click="actions.deleteScene(scene.id)">
            Delete
          </button>
        </div>
      </li>
    </ul>

    <SceneEditorModal
      v-if="editingId !== null"
      :scene-id="editingId"
      @close="editingId = null"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.running {
  background: var(--bg-input);
  margin-bottom: 12px;
}

.running .file {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  color: var(--text-dim);
  font-size: 12px;
  margin: 10px 0;
}

.create-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.create-row input {
  flex: 1;
}

.empty {
  color: var(--text-dim);
  font-size: 13px;
  padding: 8px 0;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  font-size: 11px;
  color: var(--text-dim);
}

.actions {
  display: flex;
  gap: 6px;
  flex: none;
}
</style>
