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
import AppIcon from '../AppIcon.vue'
import AppModal from '../common/AppModal.vue'
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
  <AppModal width="min(640px, 90vw)" :z-index="55" @close="emit('close')">
    <template #header>
      <div class="app-modal-head head">
        <h3>Device library</h3>
        <span class="count">{{ state.library.length }} devices</span>
        <span class="grow" />
        <button @click="fileInput?.click()">Import .yaml…</button>
        <button class="primary" @click="openDesigner(null)">
          <AppIcon name="plus" :size="12" />
          New device
        </button>
        <button class="icon-btn" title="Close" @click="emit('close')">
          <AppIcon name="close" :size="13" />
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".yaml,.yml,text/yaml"
          class="hidden-input"
          @change="onImportFile"
        />
      </div>
    </template>

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
          <button class="small" @click="duplicate(item.id)">Duplicate</button>
          <button
            class="small danger"
            :disabled="item.used_by.length > 0"
            :title="item.used_by.length > 0 ? 'Remove it from the layout first' : 'Delete definition'"
            @click="remove(item.id)"
          >
            Delete
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

    <DeviceDesignerModal v-if="designerOpen" :id="designerId" @close="onDesignerClosed" />
  </AppModal>
</template>

<style scoped>
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

.icon-btn {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
}

.primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
  font-size: 11px;
  color: var(--text-dim);
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
</style>
