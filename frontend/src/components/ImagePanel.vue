<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, actions } = useDisplayStore()

const file = ref<File | null>(null)
const localPreview = ref<string | null>(null)
const rotation = ref(0)
const brightness = ref(100)
const fit = ref<'contain' | 'stretch' | 'width' | 'height'>('contain')
const quality = ref(95)
const sending = ref(false)

const canSend = computed(() => file.value !== null && state.connected)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0] ?? null
  file.value = selected
  if (localPreview.value !== null) URL.revokeObjectURL(localPreview.value)
  localPreview.value = selected ? URL.createObjectURL(selected) : null
}

async function send(): Promise<void> {
  if (file.value === null) return
  sending.value = true
  await actions.uploadImage(file.value, {
    rotation: rotation.value,
    brightness: brightness.value,
    fit: fit.value,
    quality: quality.value,
  })
  sending.value = false
}
</script>

<template>
  <div>
    <div class="field">
      <label>Image file</label>
      <input type="file" accept="image/*" @change="onFileChange" />
    </div>

    <div v-if="localPreview" class="local-preview">
      <img :src="localPreview" alt="Selected image" />
    </div>

    <div class="row field">
      <div>
        <label>Rotation: {{ rotation }}°</label>
        <select v-model.number="rotation">
          <option :value="0">0°</option>
          <option :value="90">90°</option>
          <option :value="180">180°</option>
          <option :value="270">270°</option>
        </select>
      </div>
      <div>
        <label>Fit</label>
        <select v-model="fit">
          <option value="contain">Contain (letterbox)</option>
          <option value="stretch">Stretch</option>
          <option value="width">Fit width</option>
          <option value="height">Fit height</option>
        </select>
      </div>
    </div>

    <div class="field">
      <label>Brightness: {{ brightness }}%</label>
      <input v-model.number="brightness" type="range" min="0" max="200" />
    </div>

    <div class="field">
      <label>JPEG quality: {{ quality }}</label>
      <input v-model.number="quality" type="range" min="10" max="100" />
    </div>

    <button class="primary send" :disabled="!canSend || sending" @click="send">
      {{ sending ? 'Sending…' : 'Send to display' }}
    </button>
  </div>
</template>

<style scoped>
.local-preview {
  margin-bottom: 12px;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
  background: #000;
  text-align: center;
}

.local-preview img {
  max-width: 100%;
  max-height: 160px;
}

.send {
  width: 100%;
}
</style>
