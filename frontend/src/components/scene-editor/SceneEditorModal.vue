<script setup lang="ts">
/**
 * Near-fullscreen scene editor modal: toolbar, layers, viewport/YAML
 * center area and the inspector. Opens instead of the old inline editor.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { API } from '../../api'
import { isTypingTarget } from '../../canvas/shortcuts'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { viewCenter } from '../../scene-editor/viewState'
import EditorCanvas from './EditorCanvas.vue'
import InspectorPanel from './InspectorPanel.vue'
import SceneLayersPanel from './SceneLayersPanel.vue'
import TimelinePanel from './TimelinePanel.vue'
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

const ADD_BUTTONS = [
  { type: 'text', label: 'T', title: 'Add text widget (T)' },
  { type: 'bar', label: '▮', title: 'Add bar widget (B)' },
  { type: 'ring', label: '◯', title: 'Add ring widget (R)' },
  { type: 'graph', label: '∿', title: 'Add graph widget (G)' },
  { type: 'image', label: '▣', title: 'Add image widget (I)' },
  { type: 'shape', label: '▭', title: 'Add shape widget (S)' },
  { type: 'video', label: '▶', title: 'Add video widget (V)' },
] as const

const DRAW_TOOLS = [
  { kind: 'rect', label: '▭', title: 'Draw rectangle (drag on canvas)' },
  { kind: 'ellipse', label: '◯', title: 'Draw ellipse (drag on canvas)' },
  { kind: 'line', label: '╱', title: 'Draw diagonal line (drag on canvas)' },
] as const

// Armed shape-drawing tool; Esc or a second click disarms it.
const drawTool = ref<'rect' | 'ellipse' | 'line' | null>(null)

function toggleDrawTool(kind: 'rect' | 'ellipse' | 'line'): void {
  drawTool.value = drawTool.value === kind ? null : kind
}

const helpVisible = ref(false)

const SHORTCUTS: Array<[string, string]> = [
  ['T / B / R / G / I / S / V', 'Add text / bar / ring / graph / image / shape / video widget'],
  ['▭ ◯ ╱ tool + drag', 'Draw a shape on the canvas (Shift = square, Esc = off)'],
  ['Click / Shift+click', 'Select / extend selection'],
  ['Drag on empty canvas', 'Marquee selection'],
  ['Drag selection', 'Move (Shift = 45° axes, Alt disables snapping)'],
  ['Handles', 'Resize · drag just outside a corner to rotate (Shift = 15°)'],
  ['Ctrl+C / X / V', 'Copy / cut / paste widgets'],
  ['Arrows', 'Nudge 1 px (Shift = 10 px)'],
  ['Del', 'Delete selection'],
  ['Ctrl+D', 'Duplicate selection'],
  ['Ctrl+Z / Ctrl+Shift+Z', 'Undo / redo'],
  ['Space + drag / middle drag', 'Pan the viewport'],
  ['Mouse wheel', 'Zoom'],
  ['Ctrl+S', 'Save'],
  ['Esc', 'Exit draw tool / deselect / close editor'],
]

function addWidget(type: string): void {
  const override = state.resolutionOverride
  const panel = override ?? {
    width: appState.resolution.width,
    height: appState.resolution.height,
  }
  editor.addWidget(type, viewCenter(panel.width, panel.height))
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
  const mod = event.ctrlKey || event.metaKey
  // Modifier shortcuts match by physical key (event.code) so they work
  // on any keyboard layout; typing targets keep native behavior.
  if (mod && event.code === 'KeyS') {
    event.preventDefault()
    if (!saving.value && state.syntaxError === null) void save()
    return
  }
  if (mod && event.code === 'KeyZ') {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    if (event.shiftKey) editor.redo()
    else editor.undo()
    return
  }
  if (mod && event.code === 'KeyY') {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    editor.redo()
    return
  }
  if (mod && event.code === 'KeyC') {
    if (isTypingTarget(event.target) || state.selection.length === 0) return
    event.preventDefault()
    editor.copyEntries([...state.selection])
    return
  }
  if (mod && event.code === 'KeyX') {
    if (isTypingTarget(event.target) || state.selection.length === 0) return
    event.preventDefault()
    editor.cutEntries([...state.selection])
    return
  }
  if (mod && event.code === 'KeyV') {
    if (isTypingTarget(event.target)) return
    event.preventDefault()
    editor.pasteEntries()
    return
  }
  if (mod && event.code === 'KeyD') {
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
    const movable = [...state.selection].filter((index) => !editor.isLockedIndex(index))
    if (movable.length === 0) return
    editor.mutate((doc) => {
      for (const index of movable) {
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
    if (drawTool.value !== null) {
      drawTool.value = null
      return
    }
    if (state.selection.length > 0 && !isTypingTarget(event.target)) {
      editor.setSelection([])
      return
    }
    requestClose()
  }
  if (
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey &&
    !isTypingTarget(event.target)
  ) {
    if (event.key === '?') {
      helpVisible.value = !helpVisible.value
      return
    }
    const addKeys: Record<string, string> = {
      t: 'text',
      b: 'bar',
      r: 'ring',
      g: 'graph',
      i: 'image',
      s: 'shape',
      v: 'video',
    }
    const type = addKeys[event.key.toLowerCase()]
    if (type !== undefined) {
      addWidget(type)
    }
  }
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
        <div class="seg add-seg">
          <button
            v-for="btn in ADD_BUTTONS"
            :key="btn.type"
            class="seg-btn add-btn"
            :title="btn.title"
            @click="addWidget(btn.type)"
          >
            {{ btn.label }}
          </button>
          <span class="seg-divider"></span>
          <button
            v-for="tool in DRAW_TOOLS"
            :key="tool.kind"
            class="seg-btn add-btn"
            :class="{ on: drawTool === tool.kind }"
            :title="tool.title"
            @click="toggleDrawTool(tool.kind)"
          >
            {{ tool.label }}
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
        <button class="icon-btn" title="Keyboard shortcuts (?)" @click="helpVisible = !helpVisible">
          ?
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
          <SceneLayersPanel />
        </aside>

        <div class="center">
          <div class="center-area" :class="{ split: state.viewMode === 'split' }">
            <div
              v-if="state.viewMode === 'design' || state.viewMode === 'split'"
              class="viewport-wrap"
            >
            <EditorCanvas :draw-shape="drawTool" />
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

      <TimelinePanel />
    </div>

    <div v-if="helpVisible" class="help-overlay" @click.self="helpVisible = false">
      <div class="help-card">
        <div class="help-head">
          <span>Keyboard &amp; mouse</span>
          <button class="preview-close" @click="helpVisible = false">×</button>
        </div>
        <table class="help-table">
          <tbody>
            <tr v-for="[keys, action] in SHORTCUTS" :key="keys">
              <td class="keys">{{ keys }}</td>
              <td>{{ action }}</td>
            </tr>
          </tbody>
        </table>
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

.add-seg .add-btn {
  width: 34px;
  padding: 6px 0;
  font-size: 13px;
}

.add-seg .add-btn:hover {
  color: var(--accent);
}

.seg-divider {
  width: 1px;
  align-self: stretch;
  margin: 4px 3px;
  background: var(--border);
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

.help-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
}

.help-card {
  width: 420px;
  max-height: 80%;
  overflow-y: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}

.help-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
}

.help-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.help-table td {
  padding: 5px 12px;
  border-bottom: 1px solid rgba(51, 51, 51, 0.5);
}

.help-table .keys {
  font-family: ui-monospace, Consolas, monospace;
  color: var(--accent);
  white-space: nowrap;
  width: 40%;
}

.status-errors {
  color: var(--danger);
}

.status-dim {
  font-style: italic;
}
</style>
