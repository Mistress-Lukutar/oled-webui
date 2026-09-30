<script setup lang="ts">
/**
 * Device library manager: installed YAML device definitions with static
 * thumbnails. Add to canvas, edit in the designer, duplicate, import a
 * .yaml file or create a new device. Deletion is blocked while layout
 * instances reference the definition.
 */
import { ref } from 'vue'
import DeviceThumb from './DeviceThumb.vue'
import DeviceDesignerModal from './DeviceDesignerModal.vue'
import { useArgbStore } from '../../argb/store'

const emit = defineEmits<{ close: [] }>()

const store = useArgbStore()
const { state } = store

const designerId = ref<string | null>(null)
const designerOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function openDesigner(id: string | null): void {
  designerId.value = id
  designerOpen.value = true
}

async function onDesignerClosed(): Promise<void> {
  designerOpen.value = false
  await store.actions.loadLibrary()
}

function addToCanvas(id: string): void {
  store.actions.addDevice(id)
  emit('close')
}

async function duplicate(id: string): Promise<void> {
  await store.actions.duplicateDeviceDefinition(id)
}

async function remove(id: string): Promise<void> {
  const summary = state.library.find((item) => item.id === id)
  if (summary === undefined) return
  if (!window.confirm(`Delete device definition "${summary.name}" (${id})?`)) return
  await store.actions.deleteDeviceDefinition(id)
}

async function onImportFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file === undefined) return
  const text = await file.text()
  await store.actions.createDeviceDefinition(text)
}
</script>

<template>
  <Teleport to="body">
    <div class="library-overlay" @click.self="emit('close')">
      <div class="library-modal">
        <div class="head">
          <h3>Device library</h3>
          <span class="count">{{ state.library.length }} devices</span>
          <span class="grow" />
          <button @click="fileInput?.click()">Import .yaml…</button>
          <button class="primary" @click="openDesigner(null)">+ New device</button>
          <button class="icon-btn" title="Close" @click="emit('close')">×</button>
          <input
            ref="fileInput"
            type="file"
            accept=".yaml,.yml,text/yaml"
            class="hidden-input"
            @change="onImportFile"
          />
        </div>

        <div class="list">
          <div v-for="item in state.library" :key="item.id" class="row">
            <DeviceThumb :definition="item.definition" />
            <div class="info">
              <div class="name">{{ item.name }}</div>
              <div class="meta mono">{{ item.id }}.yaml · {{ item.leds }} LEDs</div>
              <div v-if="item.used_by.length > 0" class="meta dim">
                used by {{ item.used_by.length }} layout device{{ item.used_by.length > 1 ? 's' : '' }}
              </div>
            </div>
            <div class="actions">
              <button class="small" @click="addToCanvas(item.id)">Add</button>
              <button class="small" @click="openDesigner(item.id)">Edit</button>
              <button class="small" @click="duplicate(item.id)">Copy</button>
              <button
                class="small danger"
                :disabled="item.used_by.length > 0"
                :title="item.used_by.length > 0 ? 'Remove it from the layout first' : 'Delete definition'"
                @click="remove(item.id)"
              >
                Del
              </button>
            </div>
          </div>
          <div v-if="state.library.length === 0" class="empty">
            No devices installed. Import a .yaml definition or create a new one.
          </div>
        </div>

        <div class="foot dim">
          Definitions live in <span class="mono">data/argb/devices/&lt;id&gt;.yaml</span> — one shape
          per LED (list order = chain index); decor draws beneath the LEDs.
        </div>
      </div>

      <DeviceDesignerModal v-if="designerOpen" @close="onDesignerClosed" />
    </div>
  </Teleport>
</template>

<style scoped>
.library-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 55;
  display: flex;
  align-items: center;
  justify-content: center;
}

.library-modal {
  width: min(640px, 90vw);
  max-height: 82vh;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}

.head h3 {
  margin: 0;
  font-size: 14px;
}

.count {
  font-size: 12px;
  color: var(--text-dim);
}

.grow {
  flex: 1;
}

.hidden-input {
  display: none;
}

.list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-panel);
}

.info {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  font-size: 11px;
  color: var(--text-dim);
}

.dim {
  opacity: 0.75;
}

.actions {
  display: flex;
  gap: 4px;
  flex: none;
}

.empty {
  padding: 24px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
}

.foot {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-dim);
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
</style>
