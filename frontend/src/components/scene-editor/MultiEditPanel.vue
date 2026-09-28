<script setup lang="ts">
/**
 * Multi-selection inspector: edits apply to every selected widget in one
 * undo step. Only properties shared by all selected types are shown (the
 * paint block, transform fields, and type-specific style keys when every
 * selection member has the same type). A field whose values differ across
 * the selection renders in the "mixed" state — dashed amber border,
 * "mixed" placeholder, indeterminate toggle or a "— mixed —" select
 * option — and any edit replaces the value on all members.
 */
import { computed, ref } from 'vue'
import { API } from '../../api'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import {
  PAINT_SLOTS,
  TEXT_DIRECTIONS,
  isComponentInstance,
  intersectPaintConfigs,
} from '../../scene-editor/types'
import type { EntryRaw, PaintSlotConfig } from '../../scene-editor/types'
import {
  commonFieldValue,
  commonStyleValue,
} from '../../scene-editor/mixed'
import ExprField from './ExprField.vue'
import PaintStyleSection from './PaintStyleSection.vue'

const { state: appState, actions: appActions, showError } = useDisplayStore()
const { state } = editor

// ---------------------------------------------------------------------
// Selection views
// ---------------------------------------------------------------------

const entries = computed<Array<Record<string, unknown>>>(() =>
  state.selection
    .map((index) => editor.getWidgets()[index])
    .filter((entry) => entry !== undefined)
    .map((entry) => entry as unknown as Record<string, unknown>),
)

const hasInstance = computed(() =>
  entries.value.some((entry) => isComponentInstance(entry as EntryRaw)),
)

const widgetTypes = computed(() => [
  ...new Set(
    entries.value
      .filter((entry) => !isComponentInstance(entry as EntryRaw))
      .map((entry) => entry['type'] as string),
  ),
])

const sameType = computed(() => widgetTypes.value.length === 1)

function styleOf(entry: Record<string, unknown>): Record<string, unknown> {
  const raw = entry['style']
  return raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
}

const styles = computed(() => entries.value.map(styleOf))

/** Paint slots surviving the type intersection, or null (no style UI). */
const paintConfig = computed<PaintSlotConfig | null>(() => {
  if (hasInstance.value || widgetTypes.value.length === 0) return null
  const configs = widgetTypes.value
    .map((type) => PAINT_SLOTS[type])
    .filter((config) => config !== undefined)
  if (configs.length !== widgetTypes.value.length) return null
  return intersectPaintConfigs(configs)
})

// ---------------------------------------------------------------------
// Mutators: one mutate() call per edit = one undo step for the group
// ---------------------------------------------------------------------

function applyToAll(update: (entry: Record<string, unknown>) => void): void {
  const indices = [...state.selection]
  editor.mutate((doc) => {
    const widgets = doc.widgets ?? []
    for (const index of indices) {
      const entry = widgets[index]
      if (entry !== undefined && typeof entry === 'object' && entry !== null) {
        update(entry as Record<string, unknown>)
      }
    }
  })
}

function applyField(key: string, value: unknown): void {
  applyToAll((entry) => {
    if (value === undefined) delete entry[key]
    else entry[key] = value
  })
}

function applyStyleToAll(key: string, value: unknown): void {
  applyToAll((entry) => {
    const next = { ...styleOf(entry) }
    if (value === undefined) delete next[key]
    else next[key] = value
    if (Object.keys(next).length === 0) delete entry['style']
    else entry['style'] = next
  })
}

/** Write a numeric style field on every entry, dropping it at the default. */
function numOrDropAll(key: string, raw: string, def: number, int = false): void {
  const value = Number(raw)
  if (!Number.isFinite(value) || value === def) {
    applyStyleToAll(key, undefined)
    return
  }
  applyStyleToAll(key, int ? Math.trunc(value) : value)
}

/** Write a string style field on every entry, dropping it at the default. */
function strOrDropAll(key: string, value: string, def: string): void {
  applyStyleToAll(key, value === def ? undefined : value)
}

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

// ---------------------------------------------------------------------
// Common field states
// ---------------------------------------------------------------------

const visibleState = computed(() => commonFieldValue(entries.value, 'visible', true))
const offsetX = computed(() => commonFieldValue(entries.value, 'offset_x', 0))
const offsetY = computed(() => commonFieldValue(entries.value, 'offset_y', 0))
const opacity = computed(() => commonFieldValue(entries.value, 'opacity', 1))
const rotation = computed(() => commonFieldValue(entries.value, 'rotation', 0))

/** Visible checkbox: checked / unchecked / indeterminate (mixed). */
const visibleChecked = computed(() => visibleState.value.value === true)

// ---------------------------------------------------------------------
// Text typography (multi-edit only when every member is a text widget)
// ---------------------------------------------------------------------

const family = computed(() => commonStyleValue(styles.value, 'family', ''))
const size = computed(() => commonStyleValue(styles.value, 'size', 24))
const leading = computed(() => commonStyleValue(styles.value, 'leading', 1.2))
const tracking = computed(() => commonStyleValue(styles.value, 'tracking', 0))
const direction = computed(() => commonStyleValue(styles.value, 'direction', 'ltr'))

const fontAssets = computed(() =>
  state.assets.filter((a) => /\.(ttf|otf|woff2?)$/i.test(a)),
)

const isCustomFamily = computed<boolean>(() => {
  const value = String(family.value.value)
  if (value === '' || family.value.mixed) return false
  return (
    !appState.fonts.some((font) => `fonts/${font}` === value) &&
    !fontAssets.value.some((asset) => `assets/${asset}` === value)
  )
})

// ---------------------------------------------------------------------
// Bar / ring specifics
// ---------------------------------------------------------------------

const progressColor = computed(() => commonStyleValue(styles.value, 'progress_color', '#7CFC00'))
const orientation = computed(() => commonStyleValue(styles.value, 'orientation', 'horizontal'))
const startAngle = computed(() => commonStyleValue(styles.value, 'start_angle', -90))
const sweep = computed(() => commonStyleValue(styles.value, 'sweep', 360))
const scaleMax = computed(() => commonStyleValue(styles.value, 'scale_max', undefined))

const fontInput = ref<HTMLInputElement | null>(null)
const uploadingFonts = ref(false)

async function addLibraryFonts(files: FileList | null): Promise<void> {
  if (files === null || files.length === 0) return
  uploadingFonts.value = true
  try {
    await API.uploadFonts([...files])
    await appActions.loadFonts()
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  } finally {
    uploadingFonts.value = false
    if (fontInput.value !== null) fontInput.value.value = ''
  }
}
</script>

<template>
  <div>
    <div class="section">
      <div class="section-title">{{ state.selection.length }} widgets selected</div>
      <div class="hint">
        Only properties shared by every selected widget are shown. Fields
        marked <span class="mixed-word">mixed</span> hold different values —
        an edit replaces the value on all selected widgets.
      </div>
      <div class="btn-row">
        <button @click="editor.duplicateEntries([...state.selection])">Duplicate</button>
        <button class="danger" @click="editor.deleteEntries([...state.selection])">Delete</button>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Transform</div>
      <div class="field">
        <label>Visible</label>
        <label class="check-row">
          <input
            type="checkbox"
            :class="{ mixed: visibleState.mixed }"
            :checked="visibleChecked"
            :indeterminate.prop="visibleState.mixed"
            title="Show every selected widget"
            @change="applyField('visible', ($event.target as HTMLInputElement).checked ? undefined : false)"
          />
          <span>{{ visibleState.mixed ? 'mixed visibility' : visibleChecked ? 'shown' : 'hidden' }}</span>
        </label>
      </div>
      <ExprField
        label="offset x"
        :model-value="offsetX.mixed ? undefined : (offsetX.value as number | string | undefined)"
        :mixed="offsetX.mixed"
        @update:model-value="(v) => applyField('offset_x', v)"
      />
      <ExprField
        label="offset y"
        :model-value="offsetY.mixed ? undefined : (offsetY.value as number | string | undefined)"
        :mixed="offsetY.mixed"
        @update:model-value="(v) => applyField('offset_y', v)"
      />
      <ExprField
        label="opacity"
        :model-value="opacity.mixed ? undefined : (opacity.value as number | string | undefined)"
        :mixed="opacity.mixed"
        :default-number="1"
        :step="0.05"
        @update:model-value="(v) => applyField('opacity', v)"
      />
      <ExprField
        label="rotation"
        :model-value="rotation.mixed ? undefined : (rotation.value as number | string | undefined)"
        :mixed="rotation.mixed"
        @update:model-value="(v) => applyField('rotation', v)"
      />
    </div>

    <div class="section">
      <div class="section-title">Style</div>
      <PaintStyleSection
        v-if="paintConfig !== null"
        :styles="styles"
        :config="paintConfig"
        :default-radius="4"
        @set="applyStyleToAll"
      />
      <div v-else class="hint">
        {{ hasInstance
          ? 'Component instances have no editable style.'
          : 'No shared style properties.' }}
      </div>

      <template v-if="!hasInstance && sameType && widgetTypes[0] === 'text'">
        <div class="field">
          <label>font</label>
          <select
            :class="{ mixed: family.mixed }"
            :value="family.mixed ? '__mixed__' : String(family.value)"
            @change="applyStyleToAll('family', ($event.target as HTMLSelectElement).value || undefined)"
          >
            <option v-if="family.mixed" value="__mixed__" disabled>— mixed —</option>
            <option value="">Default (built-in)</option>
            <option v-if="isCustomFamily" :value="String(family.value)">
              {{ family.value }} (custom path)
            </option>
            <optgroup v-if="appState.fonts.length > 0" label="Font library">
              <option v-for="font in appState.fonts" :key="`lib-${font}`" :value="`fonts/${font}`">
                {{ font }}
              </option>
            </optgroup>
            <optgroup v-if="fontAssets.length > 0" label="Scene assets">
              <option v-for="asset in fontAssets" :key="`scene-${asset}`" :value="`assets/${asset}`">
                {{ asset }}
              </option>
            </optgroup>
          </select>
        </div>
        <input
          ref="fontInput"
          type="file"
          multiple
          accept=".ttf,.otf"
          class="visually-hidden"
          @change="addLibraryFonts(($event.target as HTMLInputElement).files)"
        />
        <div class="field">
          <button class="mini-btn" :disabled="uploadingFonts" @click="fontInput?.click()">
            {{ uploadingFonts ? 'Uploading…' : 'Upload font to library…' }}
          </button>
        </div>
        <div class="grid2">
          <div class="field"><label>size (4..200)</label>
            <input
              type="number" min="4" max="200"
              :class="{ mixed: size.mixed }"
              :value="size.mixed ? '' : num(size.value)"
              :placeholder="size.mixed ? 'mixed' : ''"
              @input="numOrDropAll('size', ($event.target as HTMLInputElement).value, 24, true)"
            />
          </div>
          <div class="field"><label>line height ×</label>
            <input
              type="number" min="0.1" max="4" step="0.05"
              :class="{ mixed: leading.mixed }"
              :value="leading.mixed ? '' : num(leading.value)"
              :placeholder="leading.mixed ? 'mixed' : ''"
              @input="numOrDropAll('leading', ($event.target as HTMLInputElement).value, 1.2)"
            />
          </div>
        </div>
        <div class="grid2">
          <div class="field"><label>tracking (px)</label>
            <input
              type="number" min="-32" max="128"
              :class="{ mixed: tracking.mixed }"
              :value="tracking.mixed ? '' : num(tracking.value)"
              :placeholder="tracking.mixed ? 'mixed' : ''"
              @input="numOrDropAll('tracking', ($event.target as HTMLInputElement).value, 0, true)"
            />
          </div>
          <div class="field"><label>direction</label>
            <select
              :class="{ mixed: direction.mixed }"
              :value="direction.mixed ? '__mixed__' : String(direction.value)"
              @change="strOrDropAll('direction', ($event.target as HTMLSelectElement).value, 'ltr')"
            >
              <option v-if="direction.mixed" value="__mixed__" disabled>— mixed —</option>
              <option v-for="d in TEXT_DIRECTIONS" :key="d.value" :value="d.value">{{ d.label }}</option>
            </select>
          </div>
        </div>
      </template>

      <template v-else-if="!hasInstance && sameType && widgetTypes[0] === 'bar'">
        <div class="paint-row">
          <span class="paint-label">Progress</span>
          <input
            type="color"
            :class="{ mixed: progressColor.mixed }"
            :value="String(progressColor.value)"
            :title="progressColor.mixed ? 'Progress fill (mixed)' : 'Progress fill'"
            @input="applyStyleToAll('progress_color', ($event.target as HTMLInputElement).value)"
          />
          <select
            class="paint-select"
            :class="{ mixed: orientation.mixed }"
            :value="orientation.mixed ? '__mixed__' : String(orientation.value)"
            @change="applyStyleToAll('orientation', ($event.target as HTMLSelectElement).value)"
          >
            <option v-if="orientation.mixed" value="__mixed__" disabled>— mixed —</option>
            <option value="horizontal">horizontal</option>
            <option value="vertical">vertical</option>
          </select>
        </div>
      </template>

      <template v-else-if="!hasInstance && sameType && widgetTypes[0] === 'ring'">
        <div class="grid2">
          <div class="field"><label>start angle</label>
            <input
              type="number" min="-360" max="360"
              :class="{ mixed: startAngle.mixed }"
              :value="startAngle.mixed ? '' : num(startAngle.value)"
              :placeholder="startAngle.mixed ? 'mixed' : ''"
              @input="applyStyleToAll('start_angle', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
          <div class="field"><label>sweep (30..360)</label>
            <input
              type="number" min="30" max="360"
              :class="{ mixed: sweep.mixed }"
              :value="sweep.mixed ? '' : num(sweep.value)"
              :placeholder="sweep.mixed ? 'mixed' : ''"
              @input="applyStyleToAll('sweep', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>
      </template>

      <template v-else-if="!hasInstance && sameType && widgetTypes[0] === 'graph'">
        <div class="field"><label>scale max (empty = auto)</label>
          <input
            type="number" min="0" step="1"
            :class="{ mixed: scaleMax.mixed }"
            :value="scaleMax.mixed || scaleMax.value === undefined ? '' : num(scaleMax.value)"
            :placeholder="scaleMax.mixed ? 'mixed' : ''"
            @input="applyStyleToAll('scale_max', ($event.target as HTMLInputElement).value === '' ? undefined : Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.section {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.hint {
  color: var(--text-dim);
  font-size: 11px;
  margin-bottom: 8px;
  line-height: 1.4;
}

.mixed-word {
  color: var(--warning);
  border: 1px dashed var(--warning);
  border-radius: 4px;
  padding: 0 4px;
  font-style: italic;
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 8px;
}

.field {
  margin-bottom: 8px;
}

.field label {
  font-size: 11px;
}

.check-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  cursor: pointer;
}

.check-row input {
  width: auto;
}

.btn-row {
  display: flex;
  gap: 6px;
}

.btn-row button {
  flex: 1;
}

.mini-btn {
  padding: 3px 8px;
  font-size: 11px;
}

.paint-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.paint-row input[type='color'] {
  flex: none;
  width: 30px;
  height: 24px;
  padding: 1px;
}

.paint-label {
  flex: none;
  width: 52px;
  font-size: 11px;
  color: var(--text-dim);
}

.paint-select {
  flex: 1;
  width: auto;
  padding: 4px 6px;
  font-size: 12px;
}

/* Multi-selection state: the field holds differing values. */
select.mixed,
input.mixed {
  border: 1px dashed var(--warning) !important;
}

input.mixed::placeholder {
  color: var(--warning);
  font-style: italic;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
