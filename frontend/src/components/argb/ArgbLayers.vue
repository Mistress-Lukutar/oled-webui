<script setup lang="ts">
/**
 * Layer stack panel: ordered top-to-bottom like compositing order.
 */
import { computed } from 'vue'
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

// Render top of the stack first (layers composite bottom-up).
const reversed = computed(() => [...state.layout.layers].reverse())

function onAdd(event: Event): void {
  const select = event.target as HTMLSelectElement
  if (select.value !== '') store.actions.addLayer(select.value as EffectType)
  select.value = ''
}

function onToggle(effect: Event, id: string): void {
  const box = effect.target as HTMLInputElement
  store.actions.updateLayer(id, { enabled: box.checked })
}

function up(id: string): void {
  store.actions.reorderLayer(id, 1)
}

function down(id: string): void {
  store.actions.reorderLayer(id, -1)
}
</script>

<template>
  <div class="layers">
    <div class="head">
      <h3>Layers</h3>
      <select class="add" @change="onAdd">
        <option value="">+ Add effect…</option>
        <option v-for="(label, type) in EFFECT_LABELS" :key="type" :value="type">
          {{ label }}
        </option>
      </select>
    </div>

    <p v-if="state.layout.layers.length === 0" class="empty">
      No layers yet — the chain stays dark. Add a fill or an effect.
    </p>

    <div
      v-for="layer in reversed"
      :key="layer.id"
      class="row"
      :class="{
        selected: state.selection.kind === 'layer' && state.selection.id === layer.id,
        disabled: !layer.enabled,
      }"
      @click="store.actions.select('layer', layer.id)"
    >
      <button
        class="icon"
        :title="layer.enabled ? 'Disable' : 'Enable'"
        @click.stop="onToggle($event, layer.id)"
      >
        {{ layer.enabled ? '◉' : '○' }}
      </button>
      <span class="name" :title="layer.name">{{ layer.name }}</span>
      <span class="chip">{{ EFFECT_LABELS[layer.effect.type] }}</span>
      <span class="spacer" />
      <button class="icon" title="Move up" @click.stop="up(layer.id)">▲</button>
      <button class="icon" title="Move down" @click.stop="down(layer.id)">▼</button>
      <button
        class="icon danger"
        title="Delete layer"
        @click.stop="store.actions.deleteLayer(layer.id)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.layers {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.head h3 {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

.add {
  max-width: 150px;
  font-size: 12px;
}

.empty {
  color: var(--text-dim);
  font-size: 12px;
  margin: 4px 0;
}

.row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 13px;
}

.row.selected {
  border-color: var(--accent-dim);
  background: rgba(53, 201, 142, 0.08);
}

.row.disabled .name {
  opacity: 0.45;
}

.name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip {
  font-size: 9px;
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-dim);
}

.spacer {
  flex: 0;
}

.icon {
  padding: 1px 3px;
  font-size: 11px;
  line-height: 1.2;
  min-width: 18px;
}

.icon.danger {
  color: var(--danger);
}
</style>
