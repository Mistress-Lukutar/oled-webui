<script setup lang="ts">
/**
 * Near-fullscreen unified scene editor modal: one scene file describes
 * every device, one tab per section (registry-driven), plus the shared
 * YAML view. The toolbar carries per-section tools, shared undo and the
 * scene-level save/apply actions.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { API } from '../../api'
import { isTypingTarget } from '../../canvas/shortcuts'
import { useArgbStore } from '../../argb/store'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { SECTION_SPECS, sectionSpec } from '../../scene-editor/sectionSpecs'
import { SECTION_VIEWS } from '../../scene-editor/sectionViews'
import { viewCenter } from '../../scene-editor/viewState'
import EditorCanvas from './EditorCanvas.vue'
import TimelinePanel from './TimelinePanel.vue'
import YamlPanel from './YamlPanel.vue'

const props = defineProps<{ sceneId: string; initialSection?: string }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const { state: appState, actions, showError } = useDisplayStore()
const argbStore = useArgbStore()
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

const activeSpec = computed(() => sectionSpec(state.activeSection))
const activeView = computed(
  () => SECTION_VIEWS[state.activeSection] ?? SECTION_VIEWS['screen']!,
)
const sectionPresent = computed(
  () => state.file !== null && state.file[state.activeSection] !== undefined,
)
const isScreenActive = computed(() => state.activeSection === 'screen')

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
  ['T / B / R / G / I / S / V', 'Screen: add text / bar / ring / graph / image / shape / video widget'],
  ['▭ ◯ ╱ tool + drag', 'Screen: draw a shape on the canvas (Shift = square, Esc = off)'],
  ['Ctrl+C / X / V / D', 'Screen: widgets · ARGB: devices'],
  ['Arrows', 'Nudge selection 1 px (Shift = 10 px)'],
  ['Del', 'Delete selection'],
  ['Click / Shift+click', 'Select / extend selection'],
  ['Drag on empty canvas', 'Marquee selection (screen) · pan (ARGB)'],
  ['Handles', 'Resize · drag just outside a corner to rotate (Shift = 15°)'],
  ['Ctrl+Z / Ctrl+Shift+Z', 'Undo / redo (all sections)'],
  ['Space + drag / middle drag', 'Pan the viewport'],
  ['Mouse wheel', 'Zoom'],
  ['Ctrl+S', 'Save'],
  ['Esc', 'Exit tool / deselect / close editor'],
  ['?', 'This help'],
]

function addWidget(type: string): void {
  const override = state.resolutionOverride
  const panel = override ?? {
    width: appState.resolution.width,
    height: appState.resolution.height,
  }
  editor.addWidget(type, viewCenter(panel.width, panel.height))
}

function selectSection(key: string): void {
  editor.setActiveSection(key)
  if (state.viewMode === 'design' || state.viewMode === 'split') {
    // Keep the mode; the canvas swaps to the section's own view.
  }
}

/** Create a missing device section, then bind the ARGB store to it. */
function addSection(key: string): void {
  editor.ensureSection(key)
  if (key === 'argb') argbStore.actions.bindSceneSection()
}

// Keep the ARGB store's working layout aliased to the file's argb
// section: rebind on load, YAML edits, undo/redo and "+ Add section".
watch(
  () => {
    const file = editor.getRawFile()
    return [file, file?.argb]
  },
  () => argbStore.actions.bindSceneSection(),
)

onMounted(async () => {
  if (props.initialSection !== undefined) {
    editor.setActiveSection(props.initialSection)
  }
  try {
    await editor.load(props.sceneId)
    argbStore.actions.bindSceneSection()
    loading.value = false
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
    emit('close')
  }
})

onUnmounted(() => {
  revokePreview()
  // Release the section alias: the store goes back to mirroring the
  // active engine layout for the dashboard previews.
  void argbStore.actions.refreshActiveLayout()
})

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
  if (isTypingTarget(event.target)) return

  const clipboardShortcut =
    (mod && event.code === 'KeyC') ||
    (mod && event.code === 'KeyX') ||
    (mod && event.code === 'KeyV') ||
    (mod && event.code === 'KeyD')

  if (isScreenActive.value) {
    onScreenKeydown(event, mod)
  } else {
    onArgbKeydown(event, mod)
  }
  if (clipboardShortcut) event.preventDefault()
}

function onScreenKeydown(event: KeyboardEvent, mod: boolean): void {
  if (mod && event.code === 'KeyC') {
    if (state.selection.length === 0) return
    editor.copyEntries([...state.selection])
    return
  }
  if (mod && event.code === 'KeyX') {
    if (state.selection.length === 0) return
    editor.cutEntries([...state.selection])
    return
  }
  if (mod && event.code === 'KeyV') {
    editor.pasteEntries()
    return
  }
  if (mod && event.code === 'KeyD') {
    if (state.selection.length === 0) return
    editor.duplicateEntries([...state.selection])
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (state.selection.length === 0) return
    event.preventDefault()
    editor.deleteEntries([...state.selection])
    return
  }
  if (event.key.startsWith('Arrow') && state.selection.length > 0) {
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
    if (state.selection.length > 0) {
      editor.setSelection([])
      return
    }
    requestClose()
    return
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey) {
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

function onArgbKeydown(event: KeyboardEvent, mod: boolean): void {
  const argb = argbStore
  if (mod && event.code === 'KeyC') {
    if (argb.state.deviceSelection.length === 0) return
    argb.actions.copyDevices([...argb.state.deviceSelection])
    return
  }
  if (mod && event.code === 'KeyX') {
    if (argb.state.deviceSelection.length === 0) return
    argb.actions.cutDevices([...argb.state.deviceSelection])
    return
  }
  if (mod && event.code === 'KeyV') {
    argb.actions.pasteDevices()
    return
  }
  if (mod && event.code === 'KeyD') {
    if (argb.state.deviceSelection.length === 0) return
    argb.actions.duplicateDevices([...argb.state.deviceSelection])
    return
  }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    if (argb.state.deviceSelection.length > 0) {
      event.preventDefault()
      argb.actions.deleteDevices([...argb.state.deviceSelection])
    } else if (
      argb.state.selection.kind !== null &&
      argb.state.selection.kind !== 'device' &&
      argb.state.selection.id !== null
    ) {
      event.preventDefault()
      if (argb.state.selection.kind === 'layer') {
        argb.actions.deleteLayer(argb.state.selection.id)
      } else if (argb.state.selection.kind === 'header') {
        argb.actions.deleteHeader(argb.state.selection.id)
      }
    }
    return
  }
  if (event.key.startsWith('Arrow') && argb.state.deviceSelection.length > 0) {
    event.preventDefault()
    const step = event.shiftKey ? 10 : 1
    const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0
    const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0
    argbStore.actions.moveDevicesBy([...argbStore.state.deviceSelection], dx, dy)
    return
  }
  if (event.key === 'Escape') {
    if (argb.state.maskLayerId !== null) {
      argb.actions.stopMaskPaint()
      return
    }
    if (argb.state.deviceSelection.length > 0) {
      argb.actions.setDeviceSelection([])
      return
    }
    if (argb.state.selection.kind !== null) {
      argb.actions.select(null, null)
      return
    }
    requestClose()
    return
  }
  if (!mod && event.key === '?') {
    helpVisible.value = !helpVisible.value
  }
}

window.addEventListener('keydown', onKeydown)
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div class="editor-overlay">
      <div class="editor-modal">
        <div class="toolbar">
          <span class="dirty-dot" :class="{ on: state.dirty }" title="Unsaved changes"></span>
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
              v-for="spec in SECTION_SPECS"
              :key="spec.key"
              class="seg-btn section-btn"
              :class="{ on: state.activeSection === spec.key }"
              :title="`${spec.label} section`"
              @click="selectSection(spec.key)"
            >
              {{ spec.label }}
              <span v-if="state.file?.[spec.key] === undefined" class="absent" title="Section not in this scene">·</span>
            </button>
          </div>

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

          <template v-if="isScreenActive && sectionPresent">
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
          </template>
          <component
            :is="activeView.toolbar"
            v-else-if="activeView.toolbar !== null && sectionPresent"
          />

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
          <button
            v-if="isScreenActive"
            :disabled="checking || loading"
            title="Render the screen section as JPEG (Pillow)"
            @click="checkFrame"
          >
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
            :disabled="loading"
            title="Save if needed, then start this scene on every device it describes"
            @click="apply"
          >
            Apply
          </button>
          <button class="danger" @click="requestClose">Close</button>
        </div>

        <div v-if="loading" class="loading">Loading scene…</div>

        <div v-else class="body">
          <aside class="left" :style="{ width: activeView.leftWidth }">
            <template v-if="sectionPresent">
              <component :is="component" v-for="component in activeView.left" :key="state.activeSection" />
            </template>
          </aside>

          <div class="center">
            <div class="center-area" :class="{ split: state.viewMode === 'split' }">
              <div
                v-if="state.viewMode === 'design' || state.viewMode === 'split'"
                class="viewport-wrap"
              >
                <div v-if="!sectionPresent" class="empty-section">
                  <p>
                    This scene has no
                    <b>{{ activeSpec?.label ?? state.activeSection }}</b> section —
                    applying it stops that device.
                  </p>
                  <button class="primary" @click="addSection(state.activeSection)">
                    + Add {{ activeSpec?.label ?? state.activeSection }} section
                  </button>
                </div>
                <template v-else>
                  <EditorCanvas v-if="isScreenActive" :draw-shape="drawTool" />
                  <component :is="activeView.canvas" v-else />
                </template>
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
              <template v-if="activeView.status !== null">
                <component :is="activeView.status" />
              </template>
              <template v-else>
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
              </template>
              <span
                v-if="state.errors.length > 0 || state.syntaxError !== null"
                class="status-errors"
              >
                {{ state.errors.length + (state.syntaxError !== null ? 1 : 0) }} issues
              </span>
              <span v-if="!appState.connected && isScreenActive" class="status-dim">
                panel not connected
              </span>
            </div>
          </div>

          <aside class="right" :style="{ width: activeView.rightWidth }">
            <template v-if="sectionPresent">
              <component :is="component" v-for="component in activeView.right" :key="state.activeSection" />
            </template>
          </aside>
        </div>

        <TimelinePanel v-if="isScreenActive && sectionPresent" />
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
  </Teleport>
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
  flex-wrap: wrap;
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
  width: 200px;
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

.section-btn .absent {
  color: var(--text-dim);
  font-weight: 700;
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
  flex: none;
  background: var(--bg-panel);
  min-height: 0;
}

.left {
  border-right: 1px solid var(--border);
}

.right {
  border-left: 1px solid var(--border);
  padding: 10px;
  overflow-y: auto;
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

.empty-section {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--text-dim);
  text-align: center;
  padding: 20px;
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
  flex-wrap: wrap;
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
  width: 460px;
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
