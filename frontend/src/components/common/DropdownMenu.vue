<script setup lang="ts">
/**
 * Button with an attached dropdown menu: toggles from the trigger slot,
 * closes on any outside click and on any click inside the menu. Menu
 * items and their styling come from the parent through the default
 * slot; the component owns positioning, chrome and the open state.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function toggle(): void {
  open.value = !open.value
}

function onDocumentClick(event: MouseEvent): void {
  if (!open.value) return
  if (root.value !== null && event.target instanceof Node && root.value.contains(event.target)) {
    return
  }
  open.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div ref="root" class="dropdown">
    <slot name="trigger" :toggle="toggle" />
    <div v-if="open" class="menu" @click="open = false">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.dropdown {
  position: relative;
}

.menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 50;
  min-width: 220px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
