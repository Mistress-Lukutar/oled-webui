<script setup lang="ts">
import { ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, actions } = useDisplayStore()

const color = ref('#ff0000')
const sending = ref(false)

const swatches: { hex: string; name: string }[] = [
  { hex: '#ff0000', name: 'Red' },
  { hex: '#00ff00', name: 'Green' },
  { hex: '#0000ff', name: 'Blue' },
  { hex: '#ffffff', name: 'White' },
  { hex: '#000000', name: 'Black' },
  { hex: '#ffa500', name: 'Orange' },
  { hex: '#00ffff', name: 'Cyan' },
  { hex: '#ff00ff', name: 'Magenta' },
]

async function send(): Promise<void> {
  sending.value = true
  await actions.sendColor(color.value.replace('#', ''))
  sending.value = false
}
</script>

<template>
  <div>
    <div class="field">
      <label>Color</label>
      <div class="row">
        <input v-model="color" type="color" class="picker" />
        <input v-model="color" type="text" maxlength="7" />
      </div>
    </div>

    <div class="swatches">
      <button
        v-for="swatch in swatches"
        :key="swatch.hex"
        class="swatch"
        :style="{ background: swatch.hex }"
        :title="swatch.name"
        @click="color = swatch.hex"
      />
    </div>

    <button class="primary send" :disabled="!state.connected || sending" @click="send">
      {{ sending ? 'Sending…' : 'Fill display' }}
    </button>
  </div>
</template>

<style scoped>
.picker {
  flex: none !important;
  width: 52px !important;
}

.swatches {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 6px;
  margin-bottom: 12px;
}

.swatch {
  height: 28px;
  padding: 0;
  border: 1px solid var(--border);
}

.send {
  width: 100%;
}
</style>
