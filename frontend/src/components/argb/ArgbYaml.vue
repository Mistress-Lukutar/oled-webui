<script setup lang="ts">
/**
 * YAML source view of the ARGB layout: valid YAML applies to the draft
 * immediately (one undo snapshot per replace); parse errors strip below.
 * Schema-level errors surface when the layout is saved/applied.
 */
import { ref, watch } from 'vue'
import { parse as parseYaml, stringify as stringifyYaml } from 'yaml'
import type { ArgbLayout } from '../../argb/types'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const text = ref('')
const error = ref<string | null>(null)
const focused = ref(false)

function serialize(): string {
  return stringifyYaml(state.layout, { lineWidth: 120 })
}

// Resync from the store (undo, external edits) unless the user is typing,
// which would fight the caret; blur re-serializes canonically.
watch(
  () => state.layout,
  () => {
    if (focused.value) return
    text.value = serialize()
  },
  { deep: true, immediate: true },
)

function looksLikeLayout(doc: unknown): doc is ArgbLayout {
  if (typeof doc !== 'object' || doc === null) return false
  const d = doc as Record<string, unknown>
  return (
    Array.isArray(d['headers']) &&
    Array.isArray(d['devices']) &&
    Array.isArray(d['layers'])
  )
}

function onInput(): void {
  try {
    const doc: unknown = parseYaml(text.value)
    if (!looksLikeLayout(doc)) {
      error.value = 'Layout YAML must contain headers, devices and layers lists.'
      return
    }
    store.actions.replaceLayout(doc)
    error.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}

function onBlur(): void {
  focused.value = false
  text.value = serialize()
  error.value = null
}
</script>

<template>
  <div class="yaml-wrap">
    <textarea
      v-model="text"
      class="yaml"
      spellcheck="false"
      @input="onInput"
      @focus="focused = true"
      @blur="onBlur"
    />
    <div v-if="error !== null" class="error-strip">{{ error }}</div>
  </div>
</template>

<style scoped>
.yaml-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.yaml {
  flex: 1;
  min-height: 0;
  resize: none;
  font-family: ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.45;
  white-space: pre;
  overflow: auto;
}

.error-strip {
  padding: 6px 10px;
  border: 1px solid var(--danger);
  border-radius: var(--radius);
  color: var(--danger);
  font-size: 12px;
  white-space: pre-wrap;
}
</style>
