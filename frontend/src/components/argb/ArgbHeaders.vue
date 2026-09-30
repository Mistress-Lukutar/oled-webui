<script setup lang="ts">
/**
 * Hardware panel (right column, under the inspector): OpenRGB channels
 * as a shared LayerStack. Rows are compact — picking one focuses it in
 * the inspector above, where zone, capacity and chain are edited.
 * Adding a channel adopts the zone's reported LED capacity.
 */
import { computed } from 'vue'
import LayerStack from '../common/LayerStack.vue'
import type { LayerRow, LayerStackAddOption } from '../common/LayerStack.vue'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const rows = computed<LayerRow[]>(() =>
  state.layout.headers.map((header) => {
    const zone = state.status.zones.find((item) => item.index === header.zone_index)
    return {
      id: header.id,
      label: header.name,
      chip: zone !== undefined ? zone.name : `zone ${header.zone_index}`,
      chipKind: zone?.device_type || undefined,
      enabled: true,
      toggleable: false,
      deleteDisabled: header.devices.length > 0,
      deleteTitle:
        header.devices.length > 0 ? 'Remove its devices first' : 'Delete channel',
    }
  }),
)

const selectedIds = computed(() => {
  const { kind, id } = state.selection
  return kind === 'header' && id !== null ? [id] : []
})

/** Zones of every connected OpenRGB device; 'new' = bare header while offline. */
const addOptions = computed<LayerStackAddOption[]>(() => {
  if (state.status.zones.length === 0) {
    return [{ value: 'new', label: 'New channel' }]
  }
  return state.status.zones.map((zone) => ({
    value: String(zone.index),
    label: `${zone.device_name ? `${zone.device_name} · ` : ''}${zone.name} (${zone.leds})`,
  }))
})

function onSelect(ids: string[]): void {
  const id = ids[ids.length - 1]
  if (id !== undefined) store.actions.select('header', id)
}

function onAdd(value: string): void {
  store.actions.addHeader(value === 'new' ? undefined : Number(value))
}

function onDelete(id: string): void {
  store.actions.deleteHeader(id)
}

function onMove(id: string, delta: number): void {
  store.actions.reorderHeader(id, delta)
}
</script>

<template>
  <LayerStack
    title="Channels"
    :rows="rows"
    :selected-ids="selectedIds"
    :add-options="addOptions"
    add-placeholder="+ Add channel…"
    empty-text="No channels yet — add an OpenRGB zone to light anything up."
    @select="onSelect"
    @delete="onDelete"
    @move="onMove"
    @add="onAdd"
  />
</template>
