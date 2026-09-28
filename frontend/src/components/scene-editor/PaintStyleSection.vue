<script setup lang="ts">
/**
 * Universal paint block: fill + stroke controls shared by every widget
 * type. Which rows appear is driven by the type's PaintSlotConfig; every
 * edit is emitted as (key, value) pairs where undefined drops the key at
 * its schema default, mirroring InspectorPanel.setStyle semantics.
 */
import { computed } from 'vue'
import type { PaintSlotConfig, StrokeAlign } from '../../scene-editor/types'

const props = defineProps<{
  style: Record<string, unknown>
  config: PaintSlotConfig
  /** Radius used when switching from square to rounded corners. */
  defaultRadius?: number
}>()

const emit = defineEmits<{ set: [key: string, value: unknown] }>()

function num(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

/** Write a numeric field, dropping the key at the schema default. */
function numOrDrop(key: string, raw: string, def: number): void {
  const value = Number(raw)
  if (!Number.isFinite(value) || value === def) {
    emit('set', key, undefined)
    return
  }
  emit('set', key, Math.trunc(value))
}

/** Write an enum field, dropping the key at the schema default. */
function strOrDrop(key: string, value: string, def: string): void {
  emit('set', key, value === def ? undefined : value)
}

const fillOn = computed(() => props.style['fill'] !== false)
const strokeOn = computed(() => num(props.style['stroke_width']) > 0)
const strokeAlign = computed<StrokeAlign>(() => {
  const value = props.style['stroke_align']
  return value === 'center' || value === 'outside' ? value : 'inside'
})
const cornerRounded = computed(() => num(props.style['radius']) > 0)

function setFill(on: boolean): void {
  emit('set', 'fill', on ? undefined : false)
}

function setStroke(on: boolean): void {
  // Turning the stroke back on starts from a 1 px outline.
  emit('set', 'stroke_width', on ? 1 : undefined)
}

function setStrokeAlign(value: StrokeAlign): void {
  strOrDrop('stroke_align', value, 'inside')
}

/** Square corners drop `radius`; rounded ones start from a sane default. */
function setCornerRounded(rounded: boolean): void {
  if (!rounded) {
    emit('set', 'radius', undefined)
    return
  }
  if (cornerRounded.value) return
  emit('set', 'radius', Math.max(1, props.defaultRadius ?? 4))
}
</script>

<template>
  <div>
    <div class="paint-grid">
      <div v-if="config.fill" class="paint-cell">
        <span class="paint-label">{{ config.fill.label }}</span>
        <input
          type="checkbox"
          class="paint-toggle"
          :checked="fillOn"
          title="Draw the fill"
          @change="setFill(($event.target as HTMLInputElement).checked)"
        />
        <input
          type="color"
          :value="String(style['fill_color'] ?? '#222222')"
          :disabled="!fillOn"
          :title="`${config.fill.label} fill color`"
          @input="emit('set', 'fill_color', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div v-if="config.stroke" class="paint-cell">
        <span class="paint-label">{{ config.stroke.label }}</span>
        <input
          type="checkbox"
          class="paint-toggle"
          :checked="strokeOn"
          title="Draw the stroke"
          @change="setStroke(($event.target as HTMLInputElement).checked)"
        />
        <input
          type="color"
          :value="String(style['stroke_color'] ?? '#888888')"
          :disabled="!strokeOn"
          :title="`${config.stroke.label} stroke color`"
          @input="emit('set', 'stroke_color', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>
    <div v-if="config.stroke" class="paint-row">
      <span class="paint-label">Weight</span>
      <input
        class="paint-num"
        type="number"
        min="0"
        max="64"
        :value="num(style['stroke_width'])"
        title="Stroke width"
        @input="numOrDrop('stroke_width', ($event.target as HTMLInputElement).value, 0)"
      />
      <span class="paint-unit">px</span>
    </div>
    <div v-if="config.stroke?.align" class="paint-row">
      <span class="paint-label">Align</span>
      <div class="seg-group">
        <button
          type="button"
          class="seg-btn"
          :class="{ active: strokeAlign === 'center' }"
          title="Align stroke: center"
          @click="setStrokeAlign('center')"
        >
          <svg viewBox="0 0 14 14" width="14" height="14">
            <rect x="5" y="5" width="6" height="6" fill="currentColor" opacity="0.3" />
            <rect x="4" y="4" width="8" height="8" fill="none" stroke="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ active: strokeAlign === 'inside' }"
          title="Align stroke: inside"
          @click="setStrokeAlign('inside')"
        >
          <svg viewBox="0 0 14 14" width="14" height="14">
            <rect x="4" y="4" width="7" height="7" fill="currentColor" opacity="0.3" />
            <rect x="4.5" y="4.5" width="6" height="6" fill="none" stroke="currentColor" />
          </svg>
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ active: strokeAlign === 'outside' }"
          title="Align stroke: outside"
          @click="setStrokeAlign('outside')"
        >
          <svg viewBox="0 0 14 14" width="14" height="14">
            <rect x="5" y="5" width="6" height="6" fill="currentColor" opacity="0.3" />
            <rect x="3.5" y="3.5" width="9" height="9" fill="none" stroke="currentColor" />
          </svg>
        </button>
      </div>
    </div>
    <div v-if="config.corners" class="paint-row">
      <span class="paint-label">Corner</span>
      <div class="seg-group">
        <button
          type="button"
          class="seg-btn"
          :class="{ active: !cornerRounded }"
          title="Square corners"
          @click="setCornerRounded(false)"
        >
          <svg viewBox="0 0 14 14" width="14" height="14">
            <path d="M4 11 V4 H11" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ active: cornerRounded }"
          title="Rounded corners"
          @click="setCornerRounded(true)"
        >
          <svg viewBox="0 0 14 14" width="14" height="14">
            <path d="M4 11 V8 Q4 4 8 4 H11" fill="none" stroke="currentColor" stroke-width="1.5" />
          </svg>
        </button>
      </div>
      <input
        class="paint-num"
        type="number"
        min="0"
        :value="num(style['radius'])"
        title="Corner radius"
        @input="numOrDrop('radius', ($event.target as HTMLInputElement).value, 0)"
      />
      <span class="paint-unit">px</span>
    </div>
  </div>
</template>

<style scoped>
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

.paint-cell .paint-label {
  width: auto;
}

.paint-cell input[type='color'] {
  flex: none;
  width: 30px;
  height: 24px;
  padding: 1px;
}

.paint-toggle {
  flex: none;
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
</style>
