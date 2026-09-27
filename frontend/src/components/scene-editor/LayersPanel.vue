<script setup lang="ts">
/**
 * Layers panel: widget list in z-order (top of list = topmost widget)
 * with visibility toggles, reorder and delete. Component instances are
 * shown as locked groups.
 */
import { computed } from 'vue'
import { editor } from '../../scene-editor/docStore'
import { entryLabel, isComponentInstance, widgetType } from '../../scene-editor/types'
import type { EntryRaw } from '../../scene-editor/types'

const { state } = editor

interface Row {
  index: number
  entry: EntryRaw
  isInstance: boolean
  label: string
  kind: string
  hidden: boolean
  expressionVisible: boolean
}

const rows = computed<Row[]>(() => {
  const widgets = editor.getWidgets()
  const list: Row[] = widgets.map((entry, index) => {
    const visible = entry['visible']
    return {
      index,
      entry,
      isInstance: isComponentInstance(entry),
      label: entryLabel(entry, index),
      kind: isComponentInstance(entry) ? 'use' : (widgetType(entry) ?? '?'),
      hidden: visible === false,
      expressionVisible: typeof visible === 'string',
    }
  })
  // Topmost first (widgets composite in array order, last on top).
  return list.reverse()
})

function select(index: number, event: MouseEvent): void {
  const selection = event.shiftKey ? [...state.selection, index] : [index]
  editor.setSelection([...new Set(selection)].sort((a, b) => a - b))
}

function toggleVisible(row: Row): void {
  editor.setEntryField(row.index, 'visible', row.hidden ? undefined : false)
}

function move(row: Row, direction: -1 | 1): void {
  // Display order is reversed: "up" in the list = +1 in the array.
  editor.moveEntry(row.index, row.index + direction)
}

function remove(row: Row): void {
  editor.deleteEntries([row.index])
}
</script>

<template>
  <div class="layers">
    <div class="panel-title">Layers</div>
    <div v-if="rows.length === 0" class="empty">
      No widgets yet. Add some with the toolbar.
    </div>
    <ul v-else class="list">
      <li
        v-for="row in rows"
        :key="row.index"
        class="item"
        :class="{ selected: state.selection.includes(row.index) }"
        @click="select(row.index, $event)"
      >
        <span class="kind" :data-kind="row.kind">{{ row.kind }}</span>
        <span class="label">{{ row.label }}</span>
        <span class="actions" @click.stop>
          <button
            class="mini"
            :class="{ dim: row.hidden }"
            :title="row.expressionVisible ? 'Visibility driven by an expression' : row.hidden ? 'Show' : 'Hide'"
            :disabled="row.expressionVisible"
            @click="toggleVisible(row)"
          >
            {{ row.hidden ? '◌' : '◉' }}
          </button>
          <button class="mini" title="Move up" @click="move(row, 1)">▲</button>
          <button class="mini" title="Move down" @click="move(row, -1)">▼</button>
          <button class="mini danger-mini" title="Delete" @click="remove(row)">×</button>
        </span>
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
  gap: 6px;
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
  flex: 1;
  min-width: 0;
}

.actions {
  display: none;
  gap: 2px;
  flex: none;
}

.item:hover .actions,
.item.selected .actions {
  display: inline-flex;
}

.mini {
  background: none;
  border: none;
  padding: 0 3px;
  font-size: 11px;
  color: var(--text-dim);
  cursor: pointer;
}

.mini:hover:not(:disabled) {
  color: var(--text);
}

.mini:disabled {
  opacity: 0.4;
  cursor: default;
}

.mini.dim {
  color: var(--text-dim);
}

.danger-mini:hover:not(:disabled) {
  color: var(--danger);
}
</style>
