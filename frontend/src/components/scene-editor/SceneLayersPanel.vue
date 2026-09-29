<script setup lang="ts">
/**
 * Scene-editor adapter for the shared LayerStack: maps the widget list
 * (array order = bottom-up) to display rows, topmost first. Row ids are
 * widget array indices as strings.
 */
import { computed } from 'vue'
import LayerStack from '../common/LayerStack.vue'
import type { LayerRow } from '../common/LayerStack.vue'
import { editor } from '../../scene-editor/docStore'
import { entryLabel, isComponentInstance, widgetType } from '../../scene-editor/types'

const { state } = editor

const rows = computed<LayerRow[]>(() => {
  const widgets = editor.getWidgets()
  const list: LayerRow[] = widgets.map((entry, index) => {
    const visible = entry['visible']
    const kind = isComponentInstance(entry) ? 'use' : (widgetType(entry) ?? '?')
    return {
      id: String(index),
      label: entryLabel(entry, index),
      chip: kind,
      chipKind: kind,
      enabled: visible !== false,
      toggleDisabled: typeof visible === 'string',
      locked: entry['locked'] === true,
    }
  })
  // Topmost first (widgets composite in array order, last on top).
  return list.reverse()
})

const selectedIds = computed(() => state.selection.map(String))

function onSelect(ids: string[]): void {
  editor.setSelection(ids.map(Number).sort((a, b) => a - b))
}

function onToggle(id: string): void {
  const index = Number(id)
  const hidden = editor.getWidgets()[index]?.['visible'] === false
  editor.setEntryField(index, 'visible', hidden ? undefined : false)
}

function onToggleLock(id: string): void {
  editor.toggleLock(Number(id))
}

function onDelete(id: string): void {
  editor.deleteEntries([Number(id)])
}

function onMove(id: string, delta: number): void {
  // Display order is reversed: a shift of `delta` display rows is
  // `-delta` positions in the widget array.
  const from = Number(id)
  const count = editor.getWidgets().length
  const to = Math.max(0, Math.min(count - 1, from - delta))
  if (to !== from) editor.moveEntry(from, to)
}
</script>

<template>
  <LayerStack
    :rows="rows"
    :selected-ids="selectedIds"
    empty-text="No widgets yet. Add some with the toolbar."
    lockable
    @select="onSelect"
    @toggle="onToggle"
    @toggle-lock="onToggleLock"
    @delete="onDelete"
    @move="onMove"
  />
</template>
