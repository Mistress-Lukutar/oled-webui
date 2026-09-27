<script setup lang="ts">
/**
 * Layers panel: widget list in z-order (top of list = topmost widget).
 * Reordering and per-layer actions arrive with canvas interactions.
 */
import { computed } from 'vue'
import { editor } from '../../scene-editor/docStore'
import { entryLabel, isComponentInstance, widgetType } from '../../scene-editor/types'
import type { EntryRaw } from '../../scene-editor/types'

const { state } = editor

const widgets = computed(() => editor.getWidgets())

function label(entry: EntryRaw, index: number): string {
  return entryLabel(entry, index)
}

function kindBadge(entry: EntryRaw): string {
  if (isComponentInstance(entry)) return 'use'
  return widgetType(entry) ?? '?'
}

function select(index: number, event: MouseEvent): void {
  const selection = event.shiftKey
    ? [...state.selection, index]
    : [index]
  editor.setSelection([...new Set(selection)].sort((a, b) => a - b))
}
</script>

<template>
  <div class="layers">
    <div class="panel-title">Layers</div>
    <div v-if="widgets.length === 0" class="empty">
      No widgets yet. Add some with the toolbar.
    </div>
    <ul v-else class="list">
      <li
        v-for="(entry, index) in widgets"
        :key="index"
        class="item"
        :class="{ selected: state.selection.includes(index) }"
        @click="select(index, $event)"
      >
        <span class="kind" :data-kind="kindBadge(entry)">{{ kindBadge(entry) }}</span>
        <span class="label">{{ label(entry, index) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.layers {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.panel-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 10px 12px 6px;
  flex: none;
}

.empty {
  color: var(--text-dim);
  font-size: 12px;
  padding: 4px 12px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0 6px 8px;
}

.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
  min-width: 0;
}

.item:hover {
  background: var(--bg-input);
}

.item.selected {
  background: var(--accent-dim);
  color: #fff;
}

.kind {
  flex: none;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  border: 1px solid var(--border);
  color: var(--text-dim);
  text-transform: uppercase;
}

.item.selected .kind {
  border-color: rgba(255, 255, 255, 0.4);
  color: rgba(255, 255, 255, 0.85);
}

.label {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
