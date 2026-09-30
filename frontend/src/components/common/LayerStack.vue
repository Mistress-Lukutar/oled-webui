<script setup lang="ts">
/**
 * Shared layer-stack panel for the scene and ARGB editors.
 * Store-agnostic: parents map their state to `LayerRow` rows and handle
 * the emitted actions. Rows are displayed top-to-bottom in z-order
 * (whatever the parent passes first is the topmost layer).
 *
 * Reorder is pointer-drag on the grip handle; the row is moved as a
 * single item and the parent receives `move(id, delta)` where delta is
 * the signed shift in displayed positions (negative = up).
 */
import { ref } from 'vue'

export interface LayerRow {
  id: string
  label: string
  /** Type badge text ('text', 'Fill', 'use'…); omit for no badge. */
  chip?: string
  /** data-kind attribute for badge coloring; defaults to the chip text. */
  chipKind?: string
  enabled: boolean
  /** Eye button disabled (visibility driven by an expression). */
  toggleDisabled?: boolean
  /** Rows without a visibility concept (e.g. hardware channels) hide the eye. */
  toggleable?: boolean
  /** Delete disabled while locked; lock button shown via `lockable`. */
  locked?: boolean
  /** Disable delete independent of `locked` (e.g. channel still has devices). */
  deleteDisabled?: boolean
  /** Delete button tooltip; defaults to 'Delete'. */
  deleteTitle?: string
}

export interface LayerStackAddOption {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    rows: LayerRow[]
    selectedIds: string[]
    title?: string
    emptyText: string
    addOptions?: LayerStackAddOption[]
    addPlaceholder?: string
    lockable?: boolean
  }>(),
  { title: 'Layers', addPlaceholder: '+ Add…', lockable: false },
)

const emit = defineEmits<{
  /** ids in clicked order; shift-click unions with the current selection. */
  select: [ids: string[]]
  toggle: [id: string]
  toggleLock: [id: string]
  delete: [id: string]
  move: [id: string, delta: number]
  add: [value: string]
}>()

const listEl = ref<HTMLElement | null>(null)

function onSelect(row: LayerRow, event: MouseEvent): void {
  const ids = event.shiftKey
    ? [...new Set([...props.selectedIds, row.id])]
    : [row.id]
  emit('select', ids)
}

function onAdd(event: Event): void {
  const select = event.target as HTMLSelectElement
  if (select.value !== '') emit('add', select.value)
  select.value = ''
}

// --- drag reorder -----------------------------------------------------------

interface DragState {
  id: string
  index: number
  startY: number
  moved: boolean
}

const drag = ref<DragState | null>(null)
/** Insertion gap index in the displayed list (0..rows.length), null when not dragging. */
const dropIndex = ref<number | null>(null)

function onGripDown(event: PointerEvent, row: LayerRow, index: number): void {
  event.preventDefault()
  const grip = event.currentTarget as HTMLElement
  grip.setPointerCapture(event.pointerId)
  drag.value = { id: row.id, index, startY: event.clientY, moved: false }
}

function onGripMove(event: PointerEvent): void {
  const state = drag.value
  if (state === null) return
  if (!state.moved && Math.abs(event.clientY - state.startY) < 4) return
  state.moved = true
  const list = listEl.value
  if (list === null) return
  const rows = list.querySelectorAll<HTMLElement>('.row')
  let index = rows.length
  for (let i = 0; i < rows.length; i += 1) {
    const rect = rows[i]!.getBoundingClientRect()
    if (event.clientY < rect.top + rect.height / 2) {
      index = i
      break
    }
  }
  dropIndex.value = index
}

function onGripUp(): void {
  const state = drag.value
  drag.value = null
  const target = dropIndex.value
  dropIndex.value = null
  if (state === null || !state.moved || target === null) return
  // Inserting below the start position shifts the final index up by one.
  const final = target > state.index ? target - 1 : target
  const delta = final - state.index
  if (delta !== 0) emit('move', state.id, delta)
}
</script>

<template>
  <div class="layer-stack">
    <div class="head">
      <span class="title">{{ title }}</span>
      <select v-if="addOptions" class="add" @change="onAdd">
        <option value="">{{ addPlaceholder }}</option>
        <option v-for="option in addOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    </div>

    <div v-if="rows.length === 0" class="empty">{{ emptyText }}</div>

    <ul v-else ref="listEl" class="list">
      <li
        v-for="(row, index) in rows"
        :key="row.id"
        class="row"
        :class="{
          selected: selectedIds.includes(row.id),
          off: !row.enabled,
          'drop-above': dropIndex === index,
          'drop-below': dropIndex === rows.length && index === rows.length - 1,
        }"
        @click="onSelect(row, $event)"
      >
        <span
          class="grip"
          title="Drag to reorder"
          @pointerdown="onGripDown($event, row, index)"
          @pointermove="onGripMove"
          @pointerup="onGripUp"
          @pointercancel="onGripUp"
        >
          <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
            <circle cx="9" cy="6" r="1.7" fill="currentColor" />
            <circle cx="15" cy="6" r="1.7" fill="currentColor" />
            <circle cx="9" cy="12" r="1.7" fill="currentColor" />
            <circle cx="15" cy="12" r="1.7" fill="currentColor" />
            <circle cx="9" cy="18" r="1.7" fill="currentColor" />
            <circle cx="15" cy="18" r="1.7" fill="currentColor" />
          </svg>
        </span>
        <button
          v-if="row.toggleable !== false"
          class="icon"
          :class="{ dim: !row.enabled }"
          :title="row.toggleDisabled
            ? 'Visibility driven by an expression'
            : row.enabled ? 'Hide' : 'Show'"
          :disabled="row.toggleDisabled"
          @click.stop="emit('toggle', row.id)"
        >
          <svg v-if="row.enabled" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path
              d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"
              fill="none" stroke="currentColor" stroke-width="1.8"
            />
            <circle cx="12" cy="12" r="2.8" fill="none" stroke="currentColor" stroke-width="1.8" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path
              d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"
              fill="none" stroke="currentColor" stroke-width="1.8"
            />
            <line x1="4" y1="3" x2="20" y2="21" stroke="currentColor" stroke-width="1.8" />
          </svg>
        </button>
        <span v-if="row.chip" class="chip" :data-kind="row.chipKind ?? row.chip">{{ row.chip }}</span>
        <span class="label" :title="row.label">{{ row.label }}</span>
        <button
          v-if="lockable"
          class="icon"
          :class="{ on: row.locked }"
          :title="row.locked ? 'Unlock (canvas interaction blocked)' : 'Lock: visible but mouse-transparent and protected'"
          @click.stop="emit('toggleLock', row.id)"
        >
          <svg v-if="row.locked" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="1.8" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="1.8" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="1.8" />
            <path d="M8 11V8a4 4 0 0 1 7.5-2" fill="none" stroke="currentColor" stroke-width="1.8" />
          </svg>
        </button>
        <button
          class="icon danger"
          :title="row.locked ? 'Locked — unlock first' : (row.deleteTitle ?? 'Delete')"
          :disabled="row.locked || row.deleteDisabled === true"
          @click.stop="emit('delete', row.id)"
        >
          <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
            <path
              d="M4 7h16M10 11v6M14 11v6M6.5 7l1 13h9l1-13M9.5 7V4h5v3"
              fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
            />
          </svg>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.layer-stack {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 6px;
  flex: none;
}

.title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.add {
  max-width: 150px;
  font-size: 12px;
}

.empty {
  color: var(--text-dim);
  font-size: 12px;
  padding: 4px 12px 8px;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0 6px 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 4px;
  border-radius: 6px;
  cursor: pointer;
  min-width: 0;
}

.row:hover {
  background: var(--bg-input);
}

.row.selected {
  background: var(--accent-dim);
  color: #fff;
}

.row.drop-above {
  box-shadow: inset 0 2px 0 var(--accent);
}

.row.drop-below {
  box-shadow: inset 0 -2px 0 var(--accent);
}

.grip {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 22px;
  color: var(--text-dim);
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.grip:active {
  cursor: grabbing;
}

.row:hover .grip,
.row.selected .grip {
  color: var(--text);
}

.icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
}

.icon:hover:not(:disabled) {
  color: var(--text);
}

.icon:disabled {
  opacity: 0.35;
  cursor: default;
}

.icon.dim {
  color: var(--text-dim);
}

.icon.on {
  color: var(--warning);
}

.icon.danger:hover:not(:disabled) {
  color: var(--danger);
}

.chip {
  flex: none;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  border: 1px solid var(--border);
  color: var(--text-dim);
  text-transform: uppercase;
}

.row.selected .chip {
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

.row.off .label {
  opacity: 0.45;
}
</style>
