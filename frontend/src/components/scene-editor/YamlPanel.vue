<script setup lang="ts">
/**
 * YAML source tab: textarea with live parse feedback and an error strip.
 */
import { editor } from '../../scene-editor/docStore'

const { state } = editor

function onInput(event: Event): void {
  editor.setYamlText((event.target as HTMLTextAreaElement).value)
}
</script>

<template>
  <div class="yaml-panel">
    <textarea
      class="yaml-text"
      spellcheck="false"
      :value="state.yamlText"
      @input="onInput"
    ></textarea>
    <div
      v-if="state.syntaxError !== null || state.errors.length > 0"
      class="error-strip"
    >
      <div v-if="state.syntaxError !== null" class="error-line syntax">
        {{ state.syntaxError }}
      </div>
      <div v-for="(error, i) in state.errors" :key="i" class="error-line">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.yaml-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.yaml-text {
  flex: 1;
  resize: none;
  border-radius: 0;
  border: none;
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  tab-size: 2;
  white-space: pre;
}

.error-strip {
  border-top: 1px solid var(--danger);
  background: #2a1717;
  max-height: 130px;
  overflow-y: auto;
  padding: 6px 10px;
}

.error-line {
  color: #f0b0b0;
  font-size: 12px;
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  line-height: 1.5;
}

.error-line.syntax {
  color: #ffb0b0;
  font-weight: 600;
}
</style>
