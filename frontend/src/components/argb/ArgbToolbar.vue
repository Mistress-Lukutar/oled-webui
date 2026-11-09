<script setup lang="ts">
/**
 * ARGB section toolbar: add-device dropdown over the definition library
 * plus library management. Lives in the unified scene editor toolbar
 * while the ARGB section tab is active. The library modal sits outside
 * the dropdown so closing the menu cannot unmount it.
 */
import { ref } from 'vue'
import DeviceLibraryModal from './DeviceLibraryModal.vue'
import AppIcon from '../AppIcon.vue'
import DropdownMenu from '../common/DropdownMenu.vue'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const libraryOpen = ref(false)

function addFromLibrary(definitionId: string): void {
  store.actions.addDevice(definitionId)
}
</script>

<template>
  <DropdownMenu class="add-wrap">
    <template #trigger="{ toggle }">
      <button class="seg-btn add-device" @click="toggle">
        <AppIcon name="plus" :size="12" />
        Device
        <AppIcon name="chevron-down" :size="10" />
      </button>
    </template>
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
    <button class="add-manage" @click="libraryOpen = true">
      Manage library…
    </button>
  </DropdownMenu>
  <DeviceLibraryModal v-if="libraryOpen" @close="libraryOpen = false" />
</template>

<style scoped>
.add-wrap {
  flex: none;
}

.add-device {
  padding: 6px 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.add-wrap :deep(.menu) {
  max-height: 320px;
  overflow-y: auto;
}

.add-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
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
  border-radius: 0;
  background: transparent;
  color: var(--accent);
  padding: 7px 10px;
  margin-top: 2px;
}
</style>
