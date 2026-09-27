<script setup lang="ts">
/**
 * Near-fullscreen scene editor modal: toolbar, layers, viewport/YAML
 * center area and the inspector. Opens instead of the old inline editor.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { API } from '../../api'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import EditorCanvas from './EditorCanvas.vue'
import InspectorPanel from './InspectorPanel.vue'
import LayersPanel from './LayersPanel.vue'
import YamlPanel from './YamlPanel.vue'

const props = defineProps<{ sceneId: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const { state: appState, actions, showError } = useDisplayStore()
const { state } = editor

const loading = ref(true)
const saving = ref(false)
const checking = ref(false)
const previewUrl = ref<string | null>(null)

const VIEW_MODES = [
  { id: 'design', title: 'Canvas only' },
  { id: 'split', title: 'Canvas + YAML' },
  { id: 'yaml', title: 'YAML only' },
] as const

const widgetCount = (): number => state.doc?.widgets?.length ?? 0

const RESOLUTIONS: Record<string, { width: number; height: number }> = {
  '480x480': { width: 480, height: 480 },
  '1600x720': { width: 1600, height: 720 },
  '1920x462': { width: 1920, height: 462 },
}

const resolutionKey = computed((): string => {
  const override = state.resolutionOverride
  if (override === null) return 'auto'
  for (const [key, res] of Object.entries(RESOLUTIONS)) {
    if (res.width === override.width && res.height === override.height) return key
  }
  return 'auto'
})

function onResolutionChange(event: Event): void {
  const key = (event.target as HTMLSelectElement).value
  editor.setResolutionOverride(RESOLUTIONS[key] ?? null)
}

onMounted(async () => {
  try {
    await editor.load(props.sceneId)
    loading.value = false
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
    emit('close')
  }
})

onUnmounted(revokePreview)

function revokePreview(): void {
  if (previewUrl.value !== null) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = null
}

function requestClose(): void {
  if (
    state.dirty &&
    !window.confirm('Discard unsaved changes and close the editor?')
  ) {
    return
  }
  emit('close')
}

async function save(): Promise<void> {
  saving.value = true
  try {
    await editor.save()
    emit('saved')
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  saving.value = false
}

async function checkFrame(): Promise<void> {
  checking.value = true
  try {
    const yamlFile = new File([state.yamlText], 'scene.yaml', {
      type: 'application/yaml',
    })
    const blob = await API.previewSceneYaml(yamlFile, props.sceneId)
    revokePreview()
    previewUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
  checking.value = false
}

async function apply(): Promise<void> {
  try {
    if (state.dirty) await editor.save()
    await actions.applyScene(props.sceneId)
    emit('saved')
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
}

function onKeydown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (!saving.value && state.syntaxError === null) void save()
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    if (event.shiftKey) editor.redo()
    else editor.undo()
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    editor.redo()
    return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') {
    if (isTypingTarget(event.target) || state.selection.length === 0) return
    event.preventDefault()
    editor.duplicateEntries([...state.selection])
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (isTypingTarget(event.target) || state.selection.length === 0) return
    event.preventDefault()
    editor.deleteEntries([...state.selection])
    return
  }
  if (event.key.startsWith('Arrow') && state.selection.length > 0) {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    const step = event.shiftKey ? 10 : 1
    const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0
    const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0
    editor.mutate((doc) => {
      for (const index of state.selection) {
        const entry = doc.widgets?.[index] as Record<string, unknown> | undefined
        if (entry === undefined) continue
        if (typeof entry['use'] === 'string') {
          const at = entry['at']
          const base = Array.isArray(at) && at.length === 2 ? at : [0, 0]
          entry['at'] = [Number(base[0]) + dx, Number(base[1]) + dy]
        } else {
          const rect = entry['rect']
          if (Array.isArray(rect) && rect.length === 4) {
            entry['rect'] = [Number(rect[0]) + dx, Number(rect[1]) + dy, rect[2], rect[3]]
          }
        }
      }
    })
    return
  }
  if (event.key === 'Escape') {
    if (state.selection.length > 0 && !isTypingTarget(event.target)) {
      editor.setSelection([])
      return
    }
    requestClose()
  }
}

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  )
}

window.addEventListener('keydown', onKeydown)
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="editor-overlay">
    <div class="editor-modal">
      <div class="toolbar">
        <span class="dirty-dot" :class="{ on: state.dirty }" title="Unsaved changes""></span>
        <input
          class="scene-name"
          type="text"
          maxlength="100"
          placeholder="Scene name"
          :value="state.name"
          @input="editor.setName(($event.target as HTMLInputElement).value)"
        />
        <div class="seg">
          <button
            v-for="mode in VIEW_MODES"
            :key="mode.id"
            class="seg-btn"
            :class="{ on: state.viewMode === mode.id }"
            :title="mode.title"
            @click="editor.setViewMode(mode.id)"
          >
            {{ mode.id === 'design' ? 'Design' : mode.id === 'split' ? 'Split' : 'YAML' }}
          </button>
        </div>
        <span class="spacer"></span>
        <button
          :disabled="!editor.canUndo()"
          class="icon-btn"
          title="Undo (Ctrl+Z)"
          @click="editor.undo()"
        >
          ⟲
        </button>
        <button
          :disabled="!editor.canRedo()"
          class="icon-btn"
          title="Redo (Ctrl+Shift+Z)"
          @click="editor.redo()"
        >
          ⟳
        </button>
        <button :disabled="checking || loading" @click="checkFrame">
          {{ checking ? 'Rendering…' : 'Check frame' }}
        </button>
        <button
          class="primary"
          :disabled="saving || loading || state.syntaxError !== null"
          @click="save"
        >
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
        <button
          class="primary"
          :disabled="!appState.connected || loading"
          title="Save if needed, then start this scene on the display"
          @click="apply"
        >
          Apply
        </button>
        <button class="danger" @click="requestClose">Close</button>
      </div>

      <div v-if="loading" class="loading">Loading scene…</div>

      <div v-else class="body">
        <aside class="left">
          <LayersPanel />
        </aside>

        <div class="center">
          <div class="center-area" :class="{ split: state.viewMode === 'split' }">
            <div
              v-if="state.viewMode === 'design' || state.viewMode === 'split'"
              class="viewport-wrap"
            >
              <EditorCanvas />
              <div
                v-if="previewUrl !== null"
                class="frame-preview"
                title="Server-rendered frame (exact Pillow render)"
              >
                <div class="preview-head">
                  <span>Server frame</span>
                  <button class="preview-close" @click="revokePreview">×</button>
                </div>
                <img :src="previewUrl" alt="Rendered scene frame" />
              </div>
            </div>
            <div
              v-if="state.viewMode === 'yaml' || state.viewMode === 'split'"
              class="yaml-wrap"
            >
              <YamlPanel />
            </div>
          </div>
          <div class="statusbar">
            <select
              class="res-select"
              :value="resolutionKey"
              title="Canvas size (panel profile); scenes always render at the connected panel's resolution"
              @change="onResolutionChange"
            >
              <option value="auto">
                Auto ({{ appState.resolution.width }}×{{ appState.resolution.height }})
              </option>
              <option value="480x480">480×480</option>
              <option value="1600x720">1600×720</option>
              <option value="1920x462">1920×462</option>
            </select>
            <span>{{ widgetCount() }} widgets</span>
            <span
              v-if="state.errors.length > 0 || state.syntaxError !== null"
              class="status-errors"
            >
              {{ state.errors.length + (state.syntaxError !== null ? 1 : 0) }} issues
            </span>
            <span v-if="!appState.connected" class="status-dim">device not connected</span>
          </div>
        </div>

        <aside class="right">
          <InspectorPanel />
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-modal {
  position: absolute;
  inset: 2vh 2vw;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex: none;
}

.dirty-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--border);
  flex: none;
}

.dirty-dot.on {
  background: var(--warning);
}

.scene-name {
  width: 220px;
  flex: none;
}

.seg {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  flex: none;
}

.seg-btn {
  border: none;
  border-radius: 0;
  padding: 6px 12px;
  background: transparent;
}

.seg-btn + .seg-btn {
  border-left: 1px solid var(--border);
}

.seg-btn.on {
  background: var(--accent-dim);
  color: #fff;
}

.spacer {
  flex: 1;
}

.loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.left,
.right {
  width: 210px;
  flex: none;
  background: var(--bg-panel);
  min-height: 0;
}

.left {
  border-right: 1px solid var(--border);
}

.right {
  width: 250px;
  border-left: 1px solid var(--border);
}

.center {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.center-area {
  flex: 1;
  display: flex;
  min-height: 0;
}

.center-area.split .viewport-wrap {
  border-right: 1px solid var(--border);
}

.viewport-wrap {
  flex: 1.2;
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.yaml-wrap {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.frame-preview {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 220px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  font-size: 11px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
}

.preview-close {
  background: none;
  border: none;
  padding: 0 4px;
  font-size: 14px;
  color: var(--text-dim);
}

.preview-close:hover {
  color: var(--text);
}

.frame-preview img {
  display: block;
  width: 100%;
  transform: rotate(180deg);
}

.statusbar {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 4px 12px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  font-size: 11px;
  color: var(--text-dim);
  flex: none;
}

.res-select {
  width: auto;
  padding: 2px 6px;
  font-size: 11px;
  border-radius: 6px;
}

.icon-btn {
  padding: 6px 10px;
}

.status-errors {
  color: var(--danger);
}

.status-dim {
  font-style: italic;
}
</style>
