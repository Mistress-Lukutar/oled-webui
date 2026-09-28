<script setup lang="ts">
/**
 * Dual number/expression field for transform properties. The "fx" toggle
 * switches between a plain number input and an expression string; the
 * expression is compiled client-side for instant validation and shows
 * its current value at the timeline scrub position.
 */
import { computed, ref } from 'vue'
import { editor } from '../../scene-editor/docStore'
import { Expression } from '../../scene-editor/exprEval'

const props = defineProps<{
  label: string
  modelValue: number | string | undefined
  /** Value used when switching from fx back to a plain number. */
  defaultNumber?: number
  /** Sample value for the "v" variable display. */
  sampleV?: number
  step?: number
  /** Multi-selection: values differ across the selection. */
  mixed?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: number | string | undefined] }>()

const { state } = editor

const isFx = computed(() => typeof props.modelValue === 'string')
const editing = ref<string | null>(null)

const numberValue = computed((): number => {
  const value = props.modelValue
  if (typeof value === 'number') return value
  return props.defaultNumber ?? 0
})

const compiled = computed(() => {
  if (typeof props.modelValue !== 'string') return null
  try {
    return new Expression(props.modelValue)
  } catch {
    return null
  }
})

const fxError = computed((): string | null => {
  if (typeof props.modelValue !== 'string') return null
  if (editing.value !== null) {
    try {
      new Expression(editing.value)
    } catch (err) {
      return (err as Error).message
    }
    return null
  }
  return compiled.value === null ? 'Invalid expression' : null
})

/** Live value of the expression at the current scrub time (v = sampleV). */
const fxValue = computed((): string => {
  if (compiled.value === null) return '—'
  try {
    const dt = state.loopDuration > 0 ? 1 / 20 : 0.05
    const value = compiled.value.evaluate({
      t: state.time,
      dt,
      v: props.sampleV ?? 0,
    })
    return String(Math.round(value * 100) / 100)
  } catch {
    return '—'
  }
})

function onNumberInput(event: Event): void {
  const raw = (event.target as HTMLInputElement).value
  const value = Number(raw)
  if (Number.isFinite(value)) emit('update:modelValue', value)
}

function onFxInput(event: Event): void {
  const value = (event.target as HTMLTextAreaElement).value
  editing.value = value
  emit('update:modelValue', value)
}

function toggleFx(): void {
  editing.value = null
  if (isFx.value) {
    emit('update:modelValue', props.defaultNumber ?? 0)
  } else {
    emit('update:modelValue', String(numberValue.value))
  }
}

function commitFx(): void {
  if (editing.value !== null && editing.value.trim() === '') {
    editing.value = null
    emit('update:modelValue', props.defaultNumber ?? 0)
  } else {
    editing.value = null
  }
}
</script>

<template>
  <div class="expr-field">
    <div class="head">
      <label>{{ label }}</label>
      <button
        class="fx"
        :class="{ on: isFx }"
        :title="isFx ? 'Switch to plain number' : 'Switch to expression (t, dt, v)'"
        @click="toggleFx"
      >
        fx
      </button>
    </div>
    <input
      v-if="!isFx"
      type="number"
      :step="step ?? 1"
      :class="{ mixed: props.mixed }"
      :value="props.mixed ? '' : numberValue"
      :placeholder="props.mixed ? 'mixed' : ''"
      title="mixed — the selection holds different values; editing applies to all"
      @input="onNumberInput"
    />
    <div v-else class="fx-area">
      <textarea
        class="fx-input"
        :class="{ bad: fxError !== null }"
        rows="1"
        spellcheck="false"
        :value="String(modelValue)"
        title="Variables: t (seconds), dt, v (source value) · sin cos tan abs min max floor ceil sqrt round clamp · pi tau e"
        @input="onFxInput"
        @blur="commitFx"
      ></textarea>
      <div class="fx-meta">
        <span v-if="fxError !== null" class="fx-error">{{ fxError }}</span>
        <span v-else class="fx-value">= {{ fxValue }} @ t={{ Math.round(state.time * 100) / 100 }}s</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.expr-field {
  margin-bottom: 8px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 3px;
}

label {
  margin: 0;
}

.fx {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: none;
  color: var(--text-dim);
  font-size: 10px;
  padding: 1px 6px;
  font-family: ui-monospace, Consolas, monospace;
}

.fx.on {
  color: var(--accent);
  border-color: var(--accent-dim);
}

.fx-area {
  min-width: 0;
}

.fx-input {
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  padding: 5px 8px;
  resize: none;
  min-height: 0;
}

.fx-input.bad {
  border-color: var(--danger);
}

.fx-meta {
  font-size: 10px;
  margin-top: 2px;
  min-height: 13px;
}

.fx-error {
  color: var(--danger);
}

.fx-value {
  color: var(--text-dim);
}

/* Multi-selection state: the field holds differing values. */
input.mixed {
  border: 1px dashed var(--warning);
}

input.mixed::placeholder {
  color: var(--warning);
  font-style: italic;
}
</style>
