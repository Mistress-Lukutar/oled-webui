<script setup lang="ts">
/**
 * Scene tab: library of stored YAML scenes plus an editor with
 * validation, asset management and hardware-free frame preview.
 */
import { onUnmounted, ref } from 'vue'
import { API } from '../api'
import type { SceneDetail } from '../api'
import { useDisplayStore } from '../composables/useDisplayStore'
import FileDropZone from './FileDropZone.vue'

const { state, actions, showError } = useDisplayStore()

const editingId = ref<string | null>(null)
const editingName = ref('')
const yamlText = ref('')
const assets = ref<string[]>([])
const dirty = ref(false)

const newName = ref('')
const creating = ref(false)
const uploading = ref(false)

const saving = ref(false)
const applyingId = ref<string | null>(null)
const checking = ref(false)
const previewUrl = ref<string | null>(null)
const assetInput = ref<HTMLInputElement | null>(null)

const uploadFile = ref<File | null>(null)

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}

function openEditor(detail: SceneDetail): void {
  editingId.value = detail.scene.id
  editingName.value = detail.scene.name
  yamlText.value = detail.yaml
  assets.value = detail.assets
  dirty.value = false
  clearPreview()
}

function closeEditor(): void {
  editingId.value = null
  clearPreview()
}

function clearPreview(): void {
  if (previewUrl.value !== null) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
}

onUnmounted(clearPreview)

async function createScene(): Promise<void> {
  const name = newName.value.trim()
  if (name === '') return
  creating.value = true
  try {
    const detail = await API.createScene(name)
    await actions.loadScenes()
    newName.value = ''
    openEditor(detail)
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
    openEditor(detail)
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
    openEditor(detail)
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  uploading.value = false
}

async function edit(id: string): Promise<void> {
  try {
    openEditor(await API.getScene(id))
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
}

async function save(): Promise<void> {
  if (editingId.value === null) return
  saving.value = true
  try {
    const saved = await API.saveScene(
      editingId.value,
      yamlText.value,
      editingName.value.trim() || undefined,
    )
    dirty.value = false
    if (editingName.value.trim() === '') {
      editingName.value = saved.scene.name
    }
    await actions.loadScenes()
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  saving.value = false
}

async function checkFrame(): Promise<void> {
  if (editingId.value === null) return
  checking.value = true
  try {
    const yamlFile = new File([yamlText.value], 'scene.yaml', {
      type: 'application/yaml',
    })
    const blob = await API.previewSceneYaml(yamlFile, editingId.value)
    clearPreview()
    previewUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  checking.value = false
}

async function apply(id: string): Promise<void> {
  applyingId.value = id
  await actions.applyScene(id)
  applyingId.value = null
}

async function addAssets(files: FileList | null): Promise<void> {
  if (editingId.value === null || files === null || files.length === 0) return
  try {
    const stored = await API.uploadSceneAssets(editingId.value, [...files])
    assets.value = stored.assets
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  if (assetInput.value !== null) assetInput.value.value = ''
}

async function removeAsset(name: string): Promise<void> {
  if (editingId.value === null) return
  try {
    const result = await API.deleteSceneAsset(editingId.value, name)
    assets.value = result.assets
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
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

    <template v-if="editingId !== null">
      <div class="editor-head">
        <input
          v-model="editingName"
          class="scene-name"
          type="text"
          maxlength="100"
          placeholder="Scene name"
        />
        <div class="editor-actions">
          <button
            class="primary"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
          <button :disabled="checking" @click="checkFrame">
            {{ checking ? 'Rendering…' : 'Check frame' }}
          </button>
          <button
            class="primary"
            :disabled="!state.connected || applyingId === editingId"
            @click="apply(editingId)"
          >
            {{ applyingId === editingId ? '…' : 'Apply' }}
          </button>
          <button class="danger" @click="closeEditor">Close</button>
        </div>
      </div>

      <textarea
        v-model="yamlText"
        class="yaml-editor"
        spellcheck="false"
        @input="dirty = true"
      ></textarea>

      <div v-if="previewUrl !== null" class="frame-preview">
        <img :src="previewUrl" alt="Rendered scene frame" />
      </div>

      <div class="assets">
        <h3>Assets</h3>
        <div class="asset-list">
          <span v-for="asset in assets" :key="asset" class="badge asset">
            {{ asset }}
            <button class="asset-remove" @click="removeAsset(asset)">×</button>
          </span>
          <span v-if="assets.length === 0" class="none">No assets uploaded</span>
        </div>
        <input
          ref="assetInput"
          type="file"
          multiple
          accept="image/*,.ttf,.otf,.woff,.woff2"
          class="visually-hidden"
          @change="addAssets(($event.target as HTMLInputElement).files)"
        />
        <button :disabled="uploading" @click="assetInput?.click()">
          {{ uploading ? 'Uploading…' : 'Upload images / fonts' }}
        </button>
      </div>
    </template>

    <template v-else>
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
            <button @click="edit(scene.id)">Edit</button>
            <button class="danger" @click="actions.deleteScene(scene.id)">
              Delete
            </button>
          </div>
        </li>
      </ul>
    </template>
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

.editor-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
}

.scene-name {
  width: 100%;
}

.editor-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.yaml-editor {
  width: 100%;
  min-height: 320px;
  resize: vertical;
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.45;
  white-space: pre;
  tab-size: 2;
}

.frame-preview {
  margin-top: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.frame-preview img {
  display: block;
  width: 100%;
  transform: rotate(180deg);
}

.assets {
  margin-top: 12px;
}

.assets h3 {
  font-size: 13px;
  margin: 0 0 6px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.asset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.asset {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.asset-remove {
  background: none;
  border: none;
  color: var(--text-dim);
  padding: 0 2px;
  font-size: 14px;
  line-height: 1;
}

.asset-remove:hover {
  color: var(--danger);
}

.none {
  color: var(--text-dim);
  font-size: 12px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
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
