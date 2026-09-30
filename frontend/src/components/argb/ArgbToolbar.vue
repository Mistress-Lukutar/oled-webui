<script setup lang="ts">
/**
 * ARGB section toolbar: add-device dropdown over the definition library
 * plus library management. Lives in the unified scene editor toolbar
 * while the ARGB section tab is active.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import DeviceLibraryModal from './DeviceLibraryModal.vue'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const addMenuOpen = ref(false)
const libraryOpen = ref(false)
const addWrapEl = ref<HTMLElement | null>(null)

function addFromLibrary(definitionId: string): void {
  addMenuOpen.value = false
  store.actions.addDevice(definitionId)
}

function onGlobalClick(event: MouseEvent): void {
  if (!addMenuOpen.value) return
  const wrapEl = addWrapEl.value
  if (wrapEl !== null && event.target instanceof Node && wrapEl.contains(event.target)) return
  addMenuOpen.value = false
}

onMounted(() => window.addEventListener('click', onGlobalClick))
onBeforeUnmount(() => window.removeEventListener('click', onGlobalClick))
</script>

<template>
  <div ref="addWrapEl" class="add-wrap">
    <button class="seg-btn add-device" @click="addMenuOpen = !addMenuOpen">+ Device ▾</button>
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
      <div v-if="state.library.length === 0" class="add-empty">Library is empty</div>
      <button class="add-manage" @click="addMenuOpen = false; libraryOpen = true">
        Manage library…
      </button>
    </div>
    <DeviceLibraryModal v-if="libraryOpen" @close="libraryOpen = false" />
  </div>
</template>

<style scoped>
.add-wrap {
  position: relative;
  flex: none;
}

.add-device {
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
</style>
