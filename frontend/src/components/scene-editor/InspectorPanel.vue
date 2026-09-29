<script setup lang="ts">
/**
 * Inspector panel: properties of the selected entry (geometry, transform
 * with fx-expressions, content and style per widget type, animation),
 * component instance params, scene settings and background layers, plus
 * asset management.
 */
import { computed, ref } from 'vue'
import { API } from '../../api'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import {
  DATA_SOURCES,
  EASINGS,
  PAINT_SLOTS,
  TEXT_DIRECTIONS,
  isComponentInstance,
} from '../../scene-editor/types'
import type { EntryRaw, PaintSlotConfig } from '../../scene-editor/types'
import { viewCenter } from '../../scene-editor/viewState'
import ExprField from './ExprField.vue'
import MultiEditPanel from './MultiEditPanel.vue'
import PaintStyleSection from './PaintStyleSection.vue'

const { state: appState, actions: appActions, showError } = useDisplayStore()
const { state } = editor

const assetInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

// ---------------------------------------------------------------------
// Selection helpers
// ---------------------------------------------------------------------

const singleIndex = computed<number | null>(() =>
  state.selection.length === 1 ? state.selection[0]! : null,
)

const entry = computed<Record<string, unknown> | null>(() => {
  if (singleIndex.value === null) return null
  return (editor.getWidgets()[singleIndex.value] ?? null) as Record<string, unknown> | null
})

const isInstance = computed(() => entry.value !== null && isComponentInstance(entry.value as EntryRaw))
const widgetType = computed(() => (entry.value?.['type'] as string | undefined) ?? null)

const style = computed<Record<string, unknown>>(() => {
  const raw = entry.value?.['style']
  return raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
})

const instanceParams = computed<Array<[string, unknown]>>(() => {
  if (entry.value === null) return []
  const reserved = new Set([
    'use', 'at', 'animate', 'visible', 'offset_x', 'offset_y', 'opacity', 'rotation',
  ])
  return Object.entries(entry.value).filter(([key]) => !reserved.has(key))
})

// ---------------------------------------------------------------------
// Mutators
// ---------------------------------------------------------------------

function setField(key: string, value: unknown): void {
  if (singleIndex.value === null) return
  editor.setEntryField(singleIndex.value, key, value)
}

function setStyle(key: string, value: unknown): void {
  if (singleIndex.value === null) return
  editor.updateWidget(singleIndex.value, (e) => {
    const next = { ...(e['style'] as Record<string, unknown> | undefined) }
    if (value === undefined) delete next[key]
    else next[key] = value
    if (Object.keys(next).length === 0) delete e['style']
    else e['style'] = next
  })
}

function setRectPart(part: 0 | 1 | 2 | 3, value: number): void {
  if (singleIndex.value === null) return
  editor.updateWidget(singleIndex.value, (e) => {
    const rect = e['rect']
    if (!Array.isArray(rect) || rect.length !== 4) return
    const next = [...rect]
    next[part] = Math.round(value)
    e['rect'] = next
  })
}

function setAnimateValue(spec: { easing: string; duration: number } | null): void {
  if (singleIndex.value === null) return
  editor.updateWidget(singleIndex.value, (e) => {
    const animate = { ...(e['animate'] as Record<string, unknown> | undefined) }
    if (spec === null) delete animate['value']
    else animate['value'] = spec
    if (Object.keys(animate).length === 0) delete e['animate']
    else e['animate'] = animate
  })
}

// ---------------------------------------------------------------------
// Scene settings + background
// ---------------------------------------------------------------------

function setDoc(key: string, value: number): void {
  editor.mutate((doc) => {
    doc[key] = value
  })
}

function removeBackground(index: number): void {
  editor.mutate((doc) => {
    doc.background?.splice(index, 1)
  })
}

function addBackground(path: string): void {
  editor.mutate((doc) => {
    const layers = doc.background ?? []
    layers.push({ path, opacity: 1 })
    doc.background = layers
  })
}

function setBackgroundField(index: number, key: string, value: unknown): void {
  editor.mutate((doc) => {
    const layer = doc.background?.[index]
    if (layer === undefined) return
    if (value === undefined) delete layer[key]
    else layer[key] = value
  })
}

const bgAssetChoice = ref('')

// ---------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------

const imageAssets = computed(() =>
  state.assets.filter((a) => /\.(png|jpe?g|gif|webp|bmp)$/i.test(a)),
)
const fontAssets = computed(() =>
  state.assets.filter((a) => /\.(ttf|otf|woff2?)$/i.test(a)),
)
const videoAssets = computed(() =>
  state.assets.filter((a) => /\.(mp4|webm|mov|m4v|avi|mkv)$/i.test(a)),
)

async function addAssets(files: FileList | null): Promise<void> {
  if (files === null || files.length === 0) return
  uploading.value = true
  try {
    await editor.uploadAssets([...files])
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  } finally {
    uploading.value = false
    if (assetInput.value !== null) assetInput.value.value = ''
  }
}

async function remove(name: string): Promise<void> {
  try {
    await editor.removeAsset(name)
  } catch (err) {
    showError(err instanceof Error ? err.message : String(err))
  }
}

// ---------------------------------------------------------------------
// Text typography: font picker over the shared library + scene assets
// ---------------------------------------------------------------------

const fontInput = ref<HTMLInputElement | null>(null)
const uploadingFonts = ref(false)

const familyValue = computed<string>(() => String(style.value['family'] ?? ''))

const isCustomFamily = computed<boolean>(() => {
  const value = familyValue.value
  if (value === '') return false
  return (
    !appState.fonts.some((font) => `fonts/${font}` === value) &&
    !fontAssets.value.some((asset) => `assets/${asset}` === value)
  )
})

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

/** Write a numeric style field, dropping the key at the schema default. */
function numOrDrop(key: string, raw: string, def: number, int = false): void {
  const value = Number(raw)
  if (!Number.isFinite(value) || value === def) {
    setStyle(key, undefined)
    return
  }
  setStyle(key, int ? Math.trunc(value) : value)
}

/** Write a string style field, dropping the key at the schema default. */
function strOrDrop(key: string, value: string, def: string): void {
  setStyle(key, value === def ? undefined : value)
}

/** Paint slot layout of the selected widget type, if it has a style. */
const paintConfig = computed<PaintSlotConfig | null>(() => {
  if (widgetType.value === null || isInstance.value) return null
  return PAINT_SLOTS[widgetType.value] ?? null
})

/** Radius used when switching corners from square to rounded. */
const defaultRadius = computed<number>(() => {
  const rect = entry.value?.['rect']
  const w = Array.isArray(rect) ? num(rect[2], 8) : 8
  const h = Array.isArray(rect) ? num(rect[3], 8) : 8
  return Math.max(1, Math.round(Math.min(w, h) / 2))
})
function insertImageAsset(name: string): void {
  const panel = state.resolutionOverride ?? appState.resolution
  editor.addWidget('image', viewCenter(panel.width, panel.height))
  if (singleIndex.value !== null) {
    editor.setEntryField(singleIndex.value, 'path', `assets/${name}`)
  }
}

function insertVideoAsset(name: string): void {
  const panel = state.resolutionOverride ?? appState.resolution
  editor.addWidget('video', viewCenter(panel.width, panel.height))
  if (singleIndex.value !== null) {
    editor.setEntryField(singleIndex.value, 'path', `assets/${name}`)
  }
}

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function layerPos(layer: Record<string, unknown>, part: 0 | 1): number {
  const pos = layer['pos']
  return Array.isArray(pos) ? num(pos[part]) : 0
}

const dataSourceList = [...DATA_SOURCES]
</script>

<template>
  <div class="inspector">
    <div class="panel-title">Inspector</div>

    <!-- Multi selection -->
    <MultiEditPanel v-if="state.selection.length > 1" />

    <!-- Component instance -->
    <template v-else-if="entry !== null && isInstance">
      <div class="section">
        <div class="section-title">Component · {{ entry['use'] }}</div>
        <div class="hint">Instance of a reusable component; edit its internals via the YAML tab.</div>
        <div class="grid2">
          <div class="field">
            <label>at x</label>
            <input
              type="number"
              :value="num((entry['at'] as number[] | undefined)?.[0])"
              @input="setField('at', [Number(($event.target as HTMLInputElement).value), num((entry['at'] as number[] | undefined)?.[1])])"
            />
          </div>
          <div class="field">
            <label>at y</label>
            <input
              type="number"
              :value="num((entry['at'] as number[] | undefined)?.[1])"
              @input="setField('at', [num((entry['at'] as number[] | undefined)?.[0]), Number(($event.target as HTMLInputElement).value)])"
            />
          </div>
        </div>
        <div v-for="[param, value] in instanceParams" :key="param" class="field">
          <label>{{ param }}</label>
          <input
            type="text"
            :value="String(value)"
            @input="setField(param, ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
      <div class="section">
        <div class="section-title">Transform</div>
        <ExprField label="offset x" :model-value="entry['offset_x'] as number | string | undefined" @update:model-value="(v) => setField('offset_x', v)" />
        <ExprField label="offset y" :model-value="entry['offset_y'] as number | string | undefined" @update:model-value="(v) => setField('offset_y', v)" />
        <ExprField label="opacity" :model-value="entry['opacity'] as number | string | undefined" :default-number="1" :step="0.05" @update:model-value="(v) => setField('opacity', v)" />
        <ExprField label="rotation" :model-value="entry['rotation'] as number | string | undefined" @update:model-value="(v) => setField('rotation', v)" />
      </div>
    </template>

    <!-- Widget -->
    <template v-else-if="entry !== null">
      <div class="section">
        <div class="section-title">{{ widgetType }} widget</div>
        <div v-if="entry['locked'] === true" class="hint lock-hint">
          🔒 Locked: mouse-transparent on the canvas, protected from deletion.
        </div>
        <div class="grid4">
          <div class="field"><label>X</label>
            <input type="number" :value="num((entry['rect'] as number[] | undefined)?.[0])" @input="setRectPart(0, Number(($event.target as HTMLInputElement).value))" />
          </div>
          <div class="field"><label>Y</label>
            <input type="number" :value="num((entry['rect'] as number[] | undefined)?.[1])" @input="setRectPart(1, Number(($event.target as HTMLInputElement).value))" />
          </div>
          <div class="field"><label>W</label>
            <input type="number" min="1" :value="num((entry['rect'] as number[] | undefined)?.[2])" @input="setRectPart(2, Number(($event.target as HTMLInputElement).value))" />
          </div>
          <div class="field"><label>H</label>
            <input type="number" min="1" :value="num((entry['rect'] as number[] | undefined)?.[3])" @input="setRectPart(3, Number(($event.target as HTMLInputElement).value))" />
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Transform</div>
        <div class="field">
          <label>Visible</label>
          <div v-if="typeof entry['visible'] === 'string'" class="fx-inline">
            <textarea
              rows="1"
              spellcheck="false"
              class="fx-input"
              :value="String(entry['visible'])"
              @input="setField('visible', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
            <button class="mini-btn" title="Remove expression" @click="setField('visible', undefined)">×</button>
          </div>
          <label v-else class="check-row">
            <input
              type="checkbox"
              :checked="entry['visible'] !== false"
              @change="setField('visible', ($event.target as HTMLInputElement).checked ? undefined : false)"
            />
            <span>shown</span>
          </label>
        </div>
        <ExprField label="offset x" :model-value="entry['offset_x'] as number | string | undefined" @update:model-value="(v) => setField('offset_x', v)" />
        <ExprField label="offset y" :model-value="entry['offset_y'] as number | string | undefined" @update:model-value="(v) => setField('offset_y', v)" />
        <ExprField label="opacity" :model-value="entry['opacity'] as number | string | undefined" :default-number="1" :step="0.05" @update:model-value="(v) => setField('opacity', v)" />
        <ExprField label="rotation" :model-value="entry['rotation'] as number | string | undefined" @update:model-value="(v) => setField('rotation', v)" />
        <div class="hint">
          Rotation: degrees counter-clockwise around the box center; applies
          to every widget type.
        </div>
      </div>

      <div class="section">
        <div class="section-title">Content</div>
        <template v-if="widgetType === 'text'">
          <div class="field">
            <label>source</label>
            <input
              type="text"
              list="data-sources"
              :value="(entry['source'] as string | undefined) ?? ''"
              placeholder="cpu.percent or empty"
              @input="setField('source', ($event.target as HTMLInputElement).value || undefined)"
            />
          </div>
          <div class="field">
            <label>value / template ({'{'}value{'}'})</label>
            <input
              type="text"
              :value="(entry['value'] as string | undefined) ?? ''"
              @input="setField('value', ($event.target as HTMLInputElement).value || undefined)"
            />
          </div>
          <div class="field">
            <label>align</label>
            <select :value="(entry['align'] as string | undefined) ?? 'left'" @change="setField('align', ($event.target as HTMLSelectElement).value)">
              <option value="left">left</option>
              <option value="center">center</option>
              <option value="right">right</option>
            </select>
          </div>
        </template>
        <template v-else-if="widgetType === 'image'">
          <div class="field">
            <label>path</label>
            <input
              type="text"
              list="image-assets"
              :value="(entry['path'] as string | undefined) ?? ''"
              @input="setField('path', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <div class="field">
            <label>fit</label>
            <select :value="(entry['fit'] as string | undefined) ?? 'scale'" @change="setField('fit', ($event.target as HTMLSelectElement).value)">
              <option value="contain">Contain (fit inside rect)</option>
              <option value="cover">Cover (fill rect, crop)</option>
              <option value="stretch">Stretch (distort)</option>
              <option value="scale">Scale (legacy)</option>
            </select>
          </div>
          <div v-if="((entry['fit'] as string | undefined) ?? 'scale') === 'scale'" class="field">
            <label>scale</label>
            <input
              type="number"
              step="0.05"
              min="0"
              :value="num(entry['scale'], 1)"
              @input="setField('scale', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </template>
        <template v-else-if="widgetType === 'video'">
          <div class="field">
            <label>path</label>
            <input
              type="text"
              list="video-assets"
              :value="(entry['path'] as string | undefined) ?? ''"
              @input="setField('path', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <div class="field">
            <label>fit</label>
            <select :value="(entry['fit'] as string | undefined) ?? 'contain'" @change="setField('fit', ($event.target as HTMLSelectElement).value)">
              <option value="contain">Contain (fit inside rect)</option>
              <option value="cover">Cover (fill rect, crop)</option>
              <option value="stretch">Stretch (distort)</option>
            </select>
          </div>
          <div class="grid2">
            <div class="field">
              <label>fps (1..30)</label>
              <input
                type="number"
                min="1"
                max="30"
                :value="num(entry['fps'], 15)"
                @input="setField('fps', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="field">
              <label>start offset, s</label>
              <input
                type="number"
                min="0"
                step="0.1"
                :value="num(entry['start'], 0)"
                @input="setField('start', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
          <label class="check-row">
            <input
              type="checkbox"
              :checked="entry['loop'] !== false"
              @change="setField('loop', ($event.target as HTMLInputElement).checked ? undefined : false)"
            />
            <span>loop playback</span>
          </label>
        </template>
        <template v-else-if="widgetType === 'shape'">
          <div class="field">
            <label>shape</label>
            <select
              :value="(entry['shape'] as string | undefined) ?? 'rect'"
              @change="setField('shape', ($event.target as HTMLSelectElement).value)"
            >
              <option value="rect">Rectangle</option>
              <option value="ellipse">Ellipse</option>
              <option value="line">Line (diagonal)</option>
            </select>
          </div>
        </template>
        <template v-else>
          <div class="field">
            <label>source</label>
            <input
              type="text"
              list="data-sources"
              :value="(entry['source'] as string | undefined) ?? ''"
              @input="setField('source', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <div v-if="widgetType === 'graph'" class="field">
            <label>history samples (2..3600)</label>
            <input
              type="number"
              min="2"
              max="3600"
              :value="num(entry['history'], 60)"
              @input="setField('history', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </template>
      </div>

      <div class="section">
        <div class="section-title">Style</div>
        <PaintStyleSection
          v-if="widgetType !== null && paintConfig !== null"
          :styles="[style]"
          :config="paintConfig"
          :default-radius="defaultRadius"
          @set="setStyle"
        />
        <template v-if="widgetType === 'text'">
          <div class="field">
            <label>font</label>
            <select
              :value="familyValue"
              @change="setStyle('family', ($event.target as HTMLSelectElement).value || undefined)"
            >
              <option value="">Default (built-in)</option>
              <option v-if="isCustomFamily" :value="familyValue">
                {{ familyValue }} (custom path)
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
              <input type="number" min="4" max="200" :value="num(style['size'], 24)" @input="numOrDrop('size', ($event.target as HTMLInputElement).value, 24, true)" />
            </div>
            <div class="field"><label>line height ×</label>
              <input type="number" min="0.1" max="4" step="0.05" :value="num(style['leading'], 1.2)" @input="numOrDrop('leading', ($event.target as HTMLInputElement).value, 1.2)" />
            </div>
          </div>
          <div class="grid2">
            <div class="field"><label>tracking (px)</label>
              <input type="number" min="-32" max="128" :value="num(style['tracking'], 0)" @input="numOrDrop('tracking', ($event.target as HTMLInputElement).value, 0, true)" />
            </div>
            <div class="field"><label>direction</label>
              <select
                :value="(style['direction'] as string | undefined) ?? 'ltr'"
                @change="strOrDrop('direction', ($event.target as HTMLSelectElement).value, 'ltr')"
              >
                <option v-for="d in TEXT_DIRECTIONS" :key="d.value" :value="d.value">{{ d.label }}</option>
              </select>
            </div>
          </div>
        </template>
        <template v-else-if="widgetType === 'bar'">
          <div class="paint-row">
            <span class="paint-label">Progress</span>
            <input
              type="color"
              :value="String(style['progress_color'] ?? '#7CFC00')"
              title="Progress fill"
              @input="setStyle('progress_color', ($event.target as HTMLInputElement).value)"
            />
            <select
              class="paint-select"
              :value="(style['orientation'] as string | undefined) ?? 'horizontal'"
              @change="setStyle('orientation', ($event.target as HTMLSelectElement).value)"
            >
              <option value="horizontal">horizontal</option>
              <option value="vertical">vertical</option>
            </select>
          </div>
        </template>
        <template v-else-if="widgetType === 'ring'">
          <div class="grid2">
            <div class="field"><label>start angle</label>
              <input type="number" min="-360" max="360" :value="num(style['start_angle'], -90)" @input="setStyle('start_angle', Number(($event.target as HTMLInputElement).value))" />
            </div>
            <div class="field"><label>sweep (30..360)</label>
              <input type="number" min="30" max="360" :value="num(style['sweep'], 360)" @input="setStyle('sweep', Number(($event.target as HTMLInputElement).value))" />
            </div>
          </div>
        </template>
        <template v-else-if="widgetType === 'graph'">
          <div class="field"><label>scale max (empty = auto)</label>
            <input
              type="number"
              min="0"
              step="1"
              :value="style['scale_max'] === undefined || style['scale_max'] === null ? '' : num(style['scale_max'])"
              @input="setStyle('scale_max', ($event.target as HTMLInputElement).value === '' ? undefined : Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </template>
        <div v-else-if="widgetType !== null" class="hint">No extra options for this type.</div>
      </div>

      <div class="section">
        <div class="section-title">Animation</div>
        <template v-if="(entry['animate'] as Record<string, unknown> | undefined)?.['value'] !== undefined">
          <div class="field"><label>easing</label>
            <select
              :value="((entry['animate'] as Record<string, Record<string, unknown>>)['value']?.['easing'] as string | undefined) ?? 'ease-out-cubic'"
              @change="setAnimateValue({ easing: ($event.target as HTMLSelectElement).value, duration: num((entry['animate'] as Record<string, Record<string, unknown>>)['value']?.['duration'], 400) })"
            >
              <option v-for="easing in EASINGS" :key="easing" :value="easing">{{ easing }}</option>
            </select>
          </div>
          <div class="field"><label>duration ms (1..10000)</label>
            <input
              type="number"
              min="1"
              max="10000"
              :value="num((entry['animate'] as Record<string, Record<string, unknown>>)['value']?.['duration'], 400)"
              @input="setAnimateValue({ easing: String((entry['animate'] as Record<string, Record<string, unknown>>)['value']?.['easing'] ?? 'ease-out-cubic'), duration: Number(($event.target as HTMLInputElement).value) })"
            />
          </div>
          <button class="mini-btn" @click="setAnimateValue(null)">Remove value animation</button>
        </template>
        <button v-else class="mini-btn" @click="setAnimateValue({ easing: 'ease-out-cubic', duration: 400 })">
          Animate value transitions…
        </button>
      </div>

      <div class="section btn-row">
        <button @click="editor.duplicateEntries([singleIndex!])">Duplicate</button>
        <button
          class="danger"
          :disabled="entry['locked'] === true"
          :title="entry['locked'] === true ? 'Locked — unlock first' : 'Delete'"
          @click="editor.deleteEntries([singleIndex!])"
        >
          Delete
        </button>
      </div>
    </template>

    <!-- Nothing selected: scene settings + background -->
    <template v-else>
      <div class="section">
        <div class="section-title">Scene settings</div>
        <div class="grid2">
          <div class="field"><label>refresh Hz</label>
            <input type="number" min="0" max="60" step="0.1" :value="num(state.doc?.refresh, 1)" @input="setDoc('refresh', Number(($event.target as HTMLInputElement).value))" />
          </div>
          <div class="field"><label>max fps</label>
            <input type="number" min="0" max="60" :value="num(state.doc?.max_fps, 20)" @input="setDoc('max_fps', Number(($event.target as HTMLInputElement).value))" />
          </div>
          <div class="field"><label>keepalive s</label>
            <input type="number" min="0" step="0.1" :value="num(state.doc?.keepalive_interval, 2)" @input="setDoc('keepalive_interval', Number(($event.target as HTMLInputElement).value))" />
          </div>
        </div>
        <div class="hint">Brightness and JPEG quality are global display settings (⚙ Settings).</div>
      </div>

      <div class="section">
        <div class="section-title">Background layers</div>
        <div v-if="(state.doc?.background ?? []).length === 0" class="hint">No background layers.</div>
        <div
          v-for="(layer, index) in state.doc?.background ?? []"
          :key="index"
          class="bg-layer"
        >
          <div class="bg-head">
            <span class="label">{{ layer['path'] }}</span>
            <button class="mini-btn" title="Remove layer" @click="removeBackground(index)">×</button>
          </div>
          <div class="grid2">
            <div class="field"><label>scale</label>
              <input type="number" step="0.05" min="0" :value="num(layer['scale'], 1)" @input="setBackgroundField(index, 'scale', Number(($event.target as HTMLInputElement).value))" />
            </div>
            <div class="field"><label>opacity 0..1</label>
              <input type="number" step="0.05" min="0" max="1" :value="num(layer['opacity'], 1)" @input="setBackgroundField(index, 'opacity', Number(($event.target as HTMLInputElement).value))" />
            </div>
          </div>
          <label class="check-row">
            <input
              type="checkbox"
              :checked="layer['pos'] !== undefined && layer['pos'] !== null"
              @change="setBackgroundField(index, 'pos', ($event.target as HTMLInputElement).checked ? [0, 0] : undefined)"
            />
            <span>fixed position</span>
          </label>
          <div v-if="layer['pos'] !== undefined && layer['pos'] !== null" class="grid2">
            <div class="field"><label>pos x</label>
              <input type="number" :value="layerPos(layer, 0)" @input="setBackgroundField(index, 'pos', [Number(($event.target as HTMLInputElement).value), layerPos(layer, 1)])" />
            </div>
            <div class="field"><label>pos y</label>
              <input type="number" :value="layerPos(layer, 1)" @input="setBackgroundField(index, 'pos', [layerPos(layer, 0), Number(($event.target as HTMLInputElement).value)])" />
            </div>
          </div>
        </div>
        <div v-if="imageAssets.length > 0" class="btn-row">
          <select v-model="bgAssetChoice" class="grow">
            <option value="" disabled>choose an asset…</option>
            <option v-for="asset in imageAssets" :key="asset" :value="asset">{{ asset }}</option>
          </select>
          <button :disabled="bgAssetChoice === ''" @click="addBackground(`assets/${bgAssetChoice}`); bgAssetChoice = ''">
            Add
          </button>
        </div>
      </div>
    </template>

    <!-- Assets -->
    <div class="section">
      <div class="section-title">Assets</div>
      <div class="asset-list">
        <span v-for="asset in state.assets" :key="asset" class="badge asset">
          {{ asset }}
          <button
            v-if="/\.(png|jpe?g|gif|webp|bmp)$/i.test(asset)"
            class="asset-insert"
            title="Insert as image widget"
            @click="insertImageAsset(asset)"
          >
            +
          </button>
          <button
            v-else-if="/\.(mp4|webm|mov|m4v|avi|mkv)$/i.test(asset)"
            class="asset-insert"
            title="Insert as video widget"
            @click="insertVideoAsset(asset)"
          >
            +
          </button>
          <button class="asset-remove" title="Remove asset" @click="remove(asset)">×</button>
        </span>
        <span v-if="state.assets.length === 0" class="none">No assets uploaded</span>
      </div>
      <input
        ref="assetInput"
        type="file"
        multiple
        accept="image/*,.ttf,.otf,.woff,.woff2,.mp4,.webm,.mov,.m4v,.avi,.mkv"
        class="visually-hidden"
        @change="addAssets(($event.target as HTMLInputElement).files)"
      />
      <button :disabled="uploading" @click="assetInput?.click()">
        {{ uploading ? 'Uploading…' : 'Upload images / fonts / videos' }}
      </button>
    </div>

    <datalist id="data-sources">
      <option v-for="source in dataSourceList" :key="source" :value="source" />
    </datalist>
    <datalist id="image-assets">
      <option v-for="asset in imageAssets" :key="asset" :value="`assets/${asset}`" />
    </datalist>
    <datalist id="video-assets">
      <option v-for="asset in videoAssets" :key="asset" :value="`assets/${asset}`" />
    </datalist>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding-bottom: 10px;
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

.lock-hint {
  color: var(--warning);
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 8px;
}

.grid4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0 6px;
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

/* Fill / stroke section, graphic-editor style */
.paint-grid {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}

.paint-cell {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.paint-cell input[type='color'] {
  flex: none;
  width: 30px;
  height: 24px;
  padding: 1px;
}

.paint-cell .paint-label {
  width: auto;
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

.paint-unit {
  font-size: 11px;
  color: var(--text-dim);
}

.paint-num {
  width: 48px;
  padding: 3px 6px;
  font-size: 12px;
}

.paint-select {
  flex: 1;
  width: auto;
  padding: 4px 6px;
  font-size: 12px;
}

.seg-group {
  display: flex;
  flex: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.seg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 24px;
  padding: 0;
  background: var(--bg-input);
  border: none;
  border-right: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
}

.seg-btn:last-child {
  border-right: none;
}

.seg-btn:hover {
  color: var(--text);
}

.seg-btn.active {
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent-dim);
}

.fx-inline {
  display: flex;
  gap: 4px;
  align-items: flex-start;
}

.fx-inline .fx-input {
  flex: 1;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  padding: 4px 6px;
  resize: none;
}

.grow {
  flex: 1;
}

.bg-layer {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
}

.bg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  min-width: 0;
}

.bg-head .label {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.asset {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.asset-insert {
  background: none;
  border: none;
  color: var(--accent);
  padding: 0 2px;
  font-size: 13px;
  line-height: 1;
}

.asset-insert:hover {
  color: var(--accent-dim);
}

.asset-remove {
  background: none;
  border: none;
  color: var(--text-dim);
  padding: 0 2px;
  font-size: 14px;
  line-height: 1;
}

.asset-remove:hover {
  color: var(--danger);
}

.none {
  color: var(--text-dim);
  font-size: 12px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
