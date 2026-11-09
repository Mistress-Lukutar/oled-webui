<script setup lang="ts">
import { computed, onMounted } from 'vue'
import DashboardGrid from './components/panels/DashboardGrid.vue'
import AppIcon from './components/AppIcon.vue'
import DropdownMenu from './components/common/DropdownMenu.vue'
import { useArgbStore } from './argb/store'
import { useDisplayStore } from './composables/useDisplayStore'
import { usePanelsStore } from './composables/usePanelsStore'

const { state } = useDisplayStore()
const argb = useArgbStore()
const panels = usePanelsStore()

const available = computed(() => panels.availablePanels.value)

onMounted(() => {
  void panels.init()
  void useDisplayStore().actions.init()
})

function addPanel(index: number): void {
  const entry = available.value[index]
  if (entry === undefined) return
  panels.addPanel(entry)
}
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <img src="/favicon.svg" alt="" class="logo" />
      <h1>LuminaFlowUI</h1>
    </div>

    <DropdownMenu>
      <template #trigger="{ toggle }">
        <button
          class="primary"
          :disabled="available.length === 0"
          :title="available.length === 0 ? 'All available panels are placed' : 'Add a panel'"
          @click="toggle"
        >
          <AppIcon name="plus" :size="12" />
          Panel
        </button>
      </template>
      <button
        v-for="(entry, index) in available"
        :key="`${entry.type}-${entry.device ?? 'global'}`"
        class="menu-item"
        @click="addPanel(index)"
      >
        {{ entry.title }}
        <span v-if="entry.deviceName" class="device">{{ entry.deviceName }}</span>
      </button>
      <span v-if="available.length === 0" class="menu-empty">
        Every available panel is already placed
      </span>
    </DropdownMenu>

    <button class="reset" title="Restore the default layout" @click="panels.resetLayout()">
      Reset layout
    </button>

    <div v-if="state.error" class="topbar-error" :title="state.error">{{ state.error }}</div>
  </header>

  <DashboardGrid />

  <div v-if="state.error" class="error-toast">{{ state.error }}</div>
  <div v-if="argb.state.error" class="error-toast">{{ argb.state.error }}</div>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 0;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand h1 {
  font-size: 18px;
  margin: 0;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.logo {
  width: 26px;
  height: 26px;
}

.add-wrap {
  position: relative;
}

.dropdown > button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.menu-item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  background: transparent;
  border-color: transparent;
  text-align: left;
}

.menu-item:hover {
  border-color: var(--accent-dim);
}

.menu-item .device {
  font-size: 11px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.menu-empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: 6px;
}

.reset {
  font-size: 12px;
}

.topbar-error {
  flex: 1;
  min-width: 120px;
  font-size: 12px;
  color: var(--danger);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Two stores can report at once; stack their toasts. */
.error-toast + .error-toast {
  bottom: 74px;
}
</style>
