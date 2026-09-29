<script setup lang="ts">
/**
 * Static thumbnail of a device definition: decor + LED shapes tinted by
 * chain order. Used in the device library list.
 */
import { ref, watchEffect } from 'vue'
import type { DeviceDefinition } from '../../argb/types'
import { drawDefinitionThumbnail } from '../../argb/deviceDef'

const props = defineProps<{ definition: DeviceDefinition }>()

const canvas = ref<HTMLCanvasElement | null>(null)

const W = 96
const H = 64

watchEffect(() => {
  const el = canvas.value
  if (el === null) return
  const ctx = el.getContext('2d')
  if (ctx === null) return
  drawDefinitionThumbnail(ctx, props.definition, W, H)
})
</script>

<template>
  <canvas ref="canvas" class="thumb" :width="W" :height="H" />
</template>

<style scoped>
.thumb {
  display: block;
  width: 96px;
  height: 64px;
  background: #101210;
  border: 1px solid var(--border);
  border-radius: 4px;
  flex: none;
}
</style>
