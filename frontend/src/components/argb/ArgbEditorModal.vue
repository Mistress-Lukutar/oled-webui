<script setup lang="ts">
/**
 * Fullscreen ARGB designer modal (scene-editor conventions): toolbar,
 * Effects/Hardware side tabs, canvas or YAML source view, inspector and
 * a statusbar with the OpenRGB connection controls. All state lives in
 * the argb store singleton, so opening/closing loses nothing.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ArgbCanvas from './ArgbCanvas.vue'
import ArgbHeaders from './ArgbHeaders.vue'
import ArgbInspector from './ArgbInspector.vue'
import ArgbYaml from './ArgbYaml.vue'
import ArgbLayers from './ArgbLayers.vue'
import DeviceLibraryModal from './DeviceLibraryModal.vue'
import { useArgbStore } from '../../argb/store'
import { isTypingTarget } from '../../canvas/shortcuts'

const emit = defineEmits<{ close: [] }>()

const store = useArgbStore()
const { state } = store

type ViewMode = 'design' | 'yaml'
const viewMode = ref<ViewMode>('design')
const sideTab = ref<'effects' | 'hardware'>('effects')
const helpVisible = ref(false)
const addMenuOpen = ref(false)
const libraryOpen = ref(false)

function requestClose(): void {
  if (state.dirty && !window.confirm('Discard unsaved changes?')) return
  emit('close')
}

async function save(): Promise<void> {
  await store.actions.save()
}

function addFromLibrary(definitionId: string): void {
  addMenuOpen.value = false
  store.actions.addDevice(definitionId)
}

const statusText = computed(() =>
  state.status.connected
    ? `${state.status.controller ?? 'OpenRGB'} · ${state.status.zones.length} zones`
    : 'OpenRGB not connected',
)

const chainInfo = computed(() => {
  const { kind, id } = state.selection
  let header = null
  if (kind === 'device' && id !== null) {
    const device = state.layout.devices.find((item) => item.id === id)
    header =
      device !== undefined
        ? (state.layout.headers.find((item) => item.id === device.header_id) ?? null)
        : null
  } else if (kind === 'header' && id !== null) {
    header = state.layout.headers.find((item) => item.id === id) ?? null
  }
  return header !== null ? store.headerUsage(header) : null
})

function onKeydown(event: KeyboardEvent): void {
  const mod = event.ctrlKey || event.metaKey
  if (mod && event.code === 'KeyS') {
    // Works while typing in the JSON view too.
    event.preventDefault()
    void save()
    return
  }
  if (event.key === 'Escape' && !isTypingTarget(event.target)) {
    if (helpVisible.value) {
      helpVisible.value = false
      return
    }
    // The canvas has no Escape handler of its own: this chain peels one
    // thing off per press and only closes when nothing is selected.
    if (state.maskLayerId !== null) {
      store.actions.stopMaskPaint()
      return
    }
    if (state.deviceSelection.length > 0) {
      store.actions.setDeviceSelection([])
      return
    }
    if (state.selection.kind !== null) {
      store.actions.select(null, null)
      return
    }
    requestClose()
    return
  }
  if (event.key === '?' && !isTypingTarget(event.target)) {
    helpVisible.value = !helpVisible.value
  }
}

function onGlobalClick(event: MouseEvent): void {
  if (!addMenuOpen.value) return
  const wrapEl = addWrapEl.value
  if (wrapEl !== null && event.target instanceof Node && wrapEl.contains(event.target)) return
  addMenuOpen.value = false
}

const addWrapEl = ref<HTMLElement | null>(null)

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('click', onGlobalClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('click', onGlobalClick)
})
</script>

<template>
  <div class="editor-overlay">
    <div class="editor-modal">
      <div class="toolbar">
        <span
          class="dirty-dot"
          :class="{ on: state.dirty }"
          :title="state.dirty ? 'Unsaved changes' : 'All changes saved'"
        />
        <div ref="addWrapEl" class="add-wrap">
          <button class="add-btn" @click="addMenuOpen = !addMenuOpen">+ Device ▾</button>
          <div v-if="addMenuOpen" class="add-menu" @click.stop>
            <button
              v-for="item in state.library"
              :key="item.id"
              class="add-item"
              :title="`${item.name} — ${item.leds} LEDs (${item.id}.yaml)`"
              @click="addFromLibrary(item.id)"
            >
              <span class="add-name">{{ item.name }}</span>
              <span class="add-leds">{{ item.leds }} LED</span>
            </button>
            <div v-if="state.library.length === 0" class="add-empty">
              Library is empty
            </div>
            <button class="add-manage" @click="addMenuOpen = false; libraryOpen = true">
              Manage library…
            </button>
          </div>
        </div>

        <span class="spacer" />

        <div class="seg">
          <button class="seg-btn" :class="{ on: viewMode === 'design' }" @click="viewMode = 'design'">
            Design
          </button>
          <button class="seg-btn" :class="{ on: viewMode === 'yaml' }" @click="viewMode = 'yaml'">
            YAML
          </button>
        </div>
        <button class="icon-btn" :disabled="!store.canUndo()" title="Undo (Ctrl+Z)" @click="store.undo()">⟲</button>
        <button class="icon-btn" :disabled="!store.canRedo()" title="Redo (Ctrl+Shift+Z)" @click="store.redo()">⟳</button>
        <button title="Save layout (Ctrl+S)" @click="save()">Save</button>
        <button class="primary" title="Save and run the engine" @click="store.actions.apply()">▶ Apply</button>
        <button :disabled="!state.status.running" @click="store.actions.stop()">Stop</button>
        <button class="danger" @click="requestClose()">Close</button>
        <button class="icon-btn" title="Keyboard shortcuts (?)" @click="helpVisible = !helpVisible">?</button>
      </div>

      <div class="body">
        <aside class="left">
          <div class="side-tabs">
            <button :class="{ on: sideTab === 'effects' }" @click="sideTab = 'effects'">Effects</button>
            <button :class="{ on: sideTab === 'hardware' }" @click="sideTab = 'hardware'">Hardware</button>
          </div>
          <div class="side-content">
            <ArgbLayers v-show="sideTab === 'effects'" />
            <ArgbHeaders v-show="sideTab === 'hardware'" />
          </div>
        </aside>

        <div class="center">
          <div class="center-area">
            <ArgbCanvas v-if="viewMode === 'design'" />
            <ArgbYaml v-else />
          </div>
          <div class="statusbar">
            <span
              class="dot"
              :class="{ on: state.status.connected, run: state.status.running }"
              :title="state.status.connected ? 'OpenRGB connected' : 'OpenRGB not connected'"
            />
            <span>{{ statusText }}</span>
            <span v-if="state.status.running">
              running @ {{ state.status.fps }} fps · {{ state.status.frames_sent }} frames sent
            </span>
            <button
              v-if="!state.status.connected"
              class="small"
              @click="store.actions.connect()"
            >
              Connect
            </button>
            <button v-else class="small" @click="store.actions.disconnect()">Disconnect</button>
            <span class="grow" />
            <span v-if="chainInfo !== null" class="mono">
              Chain {{ chainInfo.used }}<template v-if="chainInfo.capacity !== null">/{{ chainInfo.capacity }}</template> LEDs
            </span>
            <span class="dim">Drag to move · Wheel to zoom · Del to delete</span>
          </div>
        </div>

        <aside class="right">
          <ArgbInspector />
        </aside>
      </div>

      <div v-if="helpVisible" class="help-overlay" @click.self="helpVisible = false">
        <div class="help-card">
          <div class="help-head">
            <span>Keyboard shortcuts</span>
            <button class="icon-btn" @click="helpVisible = false">×</button>
          </div>
          <table class="help-table">
            <tbody>
              <tr><td class="keys">Del / Backspace</td><td>Delete selection</td></tr>
              <tr><td class="keys">Ctrl+C / X / V / D</td><td>Copy / cut / paste / duplicate devices</td></tr>
              <tr><td class="keys">Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y</td><td>Undo / redo</td></tr>
              <tr><td class="keys">Ctrl+S</td><td>Save layout</td></tr>
              <tr><td class="keys">Arrow keys</td><td>Nudge selection 1 px (Shift = 10 px)</td></tr>
              <tr><td class="keys">Wheel</td><td>Zoom canvas</td></tr>
              <tr><td class="keys">Space + drag</td><td>Pan canvas</td></tr>
              <tr><td class="keys">Escape</td><td>Deselect; again — close the designer</td></tr>
              <tr><td class="keys">?</td><td>This help</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <DeviceLibraryModal v-if="libraryOpen" @close="libraryOpen = false" />
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

.add-wrap {
  position: relative;
  flex: none;
}

.add-btn {
  padding: 6px 12px;
}

.add-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 10;
  min-width: 220px;
  max-height: 320px;
  overflow-y: auto;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.add-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 6px 10px;
  text-align: left;
}

.add-item:hover {
  background: var(--accent-dim);
}

.add-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-leds {
  color: var(--text-dim);
  font-size: 11px;
  flex: none;
}

.add-empty {
  padding: 10px;
  color: var(--text-dim);
  font-size: 12px;
  text-align: center;
}

.add-manage {
  border-top: 1px solid var(--border);
  border-radius: 0;
  background: transparent;
  color: var(--accent);
  padding: 7px 10px;
  margin-top: 2px;
}

.spacer,
.grow {
  flex: 1;
}

.icon-btn {
  padding: 6px 10px;
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.left {
  width: 292px;
  flex: none;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.right {
  width: 280px;
  flex: none;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  padding: 10px;
  min-height: 0;
  overflow-y: auto;
}

.side-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex: none;
}

.side-tabs button {
  flex: 1;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-dim);
}

.side-tabs button.on {
  color: var(--accent);
  background: var(--accent-dim);
}

.side-content {
  flex: 1;
  min-height: 0;
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

.center-area > :deep(*) {
  flex: 1;
  min-width: 0;
}

.statusbar {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 12px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  font-size: 11px;
  color: var(--text-dim);
  flex: none;
  flex-wrap: wrap;
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

.statusbar .small {
  font-size: 11px;
  padding: 2px 8px;
}

.mono {
  font-variant-numeric: tabular-nums;
}

.dim {
  opacity: 0.75;
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
  width: 440px;
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
  border-top: 1px solid var(--border);
}

.help-table .keys {
  white-space: nowrap;
  color: var(--accent);
  font-family: ui-monospace, Menlo, Consolas, monospace;
  width: 1%;
}
</style>
