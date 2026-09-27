<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, actions } = useDisplayStore()

const text = ref('Hello, OLED!')
const fontSize = ref(64)
const color = ref('#ffffff')
const background = ref('#000000')
const align = ref<'left' | 'center' | 'right'>('center')
const valign = ref<'top' | 'middle' | 'bottom'>('middle')
const padding = ref(20)
const rotation = ref(0)
const fontName = ref<string>('')
const sending = ref(false)

onMounted(() => {
  void actions.loadFonts()
})

async function send(): Promise<void> {
  sending.value = true
  await actions.sendText({
    text: text.value,
    font_size: fontSize.value,
    color: color.value.replace('#', ''),
    background: background.value.replace('#', ''),
    align: align.value,
    valign: valign.value,
    padding: padding.value,
    rotation: rotation.value,
    font_name: fontName.value === '' ? null : fontName.value,
  })
  sending.value = false
}
</script>

<template>
  <div>
    <div class="field">
      <label>Text (multi-line supported)</label>
      <textarea v-model="text" rows="3" />
    </div>

    <div class="row field">
      <div>
        <label>Font size: {{ fontSize }}px</label>
        <input v-model.number="fontSize" type="range" min="12" max="300" />
      </div>
      <div>
        <label>Rotation</label>
        <select v-model.number="rotation">
          <option :value="0">0°</option>
          <option :value="90">90°</option>
          <option :value="180">180°</option>
          <option :value="270">270°</option>
        </select>
      </div>
    </div>

    <div class="row field">
      <div>
        <label>Text color</label>
        <input v-model="color" type="color" />
      </div>
      <div>
        <label>Background</label>
        <input v-model="background" type="color" />
      </div>
    </div>

    <div class="row field">
      <div>
        <label>Align</label>
        <select v-model="align">
          <option value="left">Left</option>
          <option value="center">Center</option>
          <option value="right">Right</option>
        </select>
      </div>
      <div>
        <label>Vertical</label>
        <select v-model="valign">
          <option value="top">Top</option>
          <option value="middle">Middle</option>
          <option value="bottom">Bottom</option>
        </select>
      </div>
      <div>
        <label>Font</label>
        <select v-model="fontName">
          <option value="">System default</option>
          <option v-for="font in state.fonts" :key="font" :value="font">
            {{ font }}
          </option>
        </select>
      </div>
    </div>

    <div class="field">
      <label>Padding: {{ padding }}px</label>
      <input v-model.number="padding" type="range" min="0" max="200" />
    </div>

    <button class="primary send" :disabled="!state.connected || sending" @click="send">
      {{ sending ? 'Sending…' : 'Render to display' }}
    </button>
  </div>
</template>

<style scoped>
.send {
  width: 100%;
}
</style>
