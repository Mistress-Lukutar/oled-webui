<script setup lang="ts">
/**
 * ARGB adapter for the shared LayerStack: maps the effect layers
 * (array order = composite bottom-up) to display rows, top of stack
 * first. Row ids are stable layer ids.
 */
import { computed } from 'vue'
import LayerStack from '../common/LayerStack.vue'
import type { LayerRow } from '../common/LayerStack.vue'
import { useArgbStore } from '../../argb/store'
import type { EffectType } from '../../argb/types'

const store = useArgbStore()
const { state } = store

const EFFECT_LABELS: Record<EffectType, string> = {
  fill: 'Fill',
  gradient: 'Gradient',
  rainbow: 'Rainbow',
  breathing: 'Breathing',
  comet: 'Comet',
  scanner: 'Scanner',
  meter: 'Meter',
}

const addOptions = Object.entries(EFFECT_LABELS).map(([value, label]) => ({ value, label }))

const rows = computed<LayerRow[]>(() =>
  // Render top of the stack first (layers composite bottom-up).
  [...state.layout.layers].reverse().map((layer) => ({
    id: layer.id,
    label: layer.name,
    chip: EFFECT_LABELS[layer.effect.type],
    enabled: layer.enabled,
  })),
)

const selectedIds = computed(() => {
  const { kind, id } = state.selection
  return kind === 'layer' && id !== null ? [id] : []
})

function onSelect(ids: string[]): void {
  const id = ids[ids.length - 1]
  if (id !== undefined) store.actions.select('layer', id)
}

function onToggle(id: string): void {
  const layer = state.layout.layers.find((item) => item.id === id)
  if (layer !== undefined) store.actions.updateLayer(id, { enabled: !layer.enabled })
}

function onDelete(id: string): void {
  store.actions.deleteLayer(id)
}

function onMove(id: string, delta: number): void {
  // reorderLayer's direction is +1 toward the top of the stack,
  // which is one row up in the displayed (reversed) list.
  store.actions.reorderLayer(id, -delta)
}

function onAdd(value: string): void {
  store.actions.addLayer(value as EffectType)
}
</script>

<template>
  <LayerStack
    :rows="rows"
    :selected-ids="selectedIds"
    :add-options="addOptions"
    add-placeholder="+ Add effect…"
    empty-text="No layers yet — the chain stays dark. Add a fill or an effect."
    @select="onSelect"
    @toggle="onToggle"
    @delete="onDelete"
    @move="onMove"
    @add="onAdd"
  />
</template>
