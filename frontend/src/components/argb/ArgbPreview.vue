<script setup lang="ts">
/**
 * Read-only live preview for the ARGB tab: the workspace fit into the
 * pane, devices colored from the preview buffers with the brightness LUT
 * applied client-side — what the engine dispatches to hardware.
 */
import { onBeforeUnmount, onMounted, ref, watchEffect } from 'vue'
import { drawPreview } from '../../argb/render'
import { WORKSPACE_HEIGHT, WORKSPACE_WIDTH } from '../../argb/types'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const canvas = ref<HTMLCanvasElement | null>(null)

watchEffect(() => {
  // Read reactive sources up front so the effect re-runs on changes;
  // drawing itself is a side effect on the canvas context.
  const layout = state.layout
  const preview = state.preview
  const brightness = layout.brightness
  const el = canvas.value
  if (el === null) return
  const ctx = el.getContext('2d')
  if (ctx === null) return
  drawPreview(
    ctx,
    layout,
    preview,
    brightness,
    WORKSPACE_WIDTH,
    WORKSPACE_HEIGHT,
  )
})

onMounted(() => {
  store.startPreviewPolling()
})

onBeforeUnmount(() => {
  store.stopPreviewPolling()
})
</script>

<template>
  <canvas
    ref="canvas"
    class="argb-preview"
    :width="WORKSPACE_WIDTH"
    :height="WORKSPACE_HEIGHT"
  />
</template>

<style scoped>
.argb-preview {
  display: block;
  width: 100%;
  aspect-ratio: 8 / 5;
  border-radius: var(--radius);
}
</style>
