<script setup lang="ts">
/**
 * Shared interactive canvas stage: a logical canvas of fixed size with
 * zoom/pan, box selection, drag/resize/rotate, marquee, snap guides and
 * the interaction overlay. The host supplies a StageAdapter (applies
 * changes to its document) and a drawContent callback (renders content;
 * its reactive reads are tracked and re-draw the stage).
 */
import { onMounted, ref, watchEffect } from 'vue'
import { createStageController } from '../../canvas/stage'
import type { StageAdapter } from '../../canvas/stage'
import { drawStageOverlay } from '../../canvas/overlay'
import { useViewport } from '../../canvas/viewport'

const props = defineProps<{
  /** Logical canvas size in canvas pixels. */
  width: number
  height: number
  adapter: StageAdapter
  /** Draw content in logical canvas coordinates. */
  drawContent: (ctx: CanvasRenderingContext2D, width: number, height: number) => void
  /** Render at logical resolution with hard pixels (OLED panel preview). */
  pixelated?: boolean
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)

const viewport = useViewport(
  () => props.width,
  () => props.height,
)
const { zoom, panX, panY, spaceHeld, transformStyle, fit, onWheel } = viewport

const controller = createStageController({
  adapter: props.adapter,
  canvas: () => canvasEl.value,
  zoom: () => zoom.value,
  canvasWidth: () => props.width,
  canvasHeight: () => props.height,
  pan: (x, y) => {
    panX.value = x
    panY.value = y
  },
  getPan: () => ({ x: panX.value, y: panY.value }),
  spaceHeld: () => spaceHeld.value,
})

// Main draw effect: re-runs whenever the content's reactive inputs, the
// selection/overlay state or the view change. The drawContent callback's
// own reactive reads are tracked here automatically.
watchEffect(() => {
  const panel = canvasEl.value
  if (panel === null) return
  const ctx = panel.getContext('2d')
  if (ctx === null) return
  void zoom.value
  void controller.marquee.value
  void controller.guides.value

  // Pixelated hosts render 1:1 logical pixels; others rasterize at
  // device resolution (clamped) so content stays sharp when zoomed in.
  const scale = props.pixelated
    ? 1
    : Math.min(3, Math.max(1, zoom.value * (window.devicePixelRatio || 1)))
  const backingW = Math.round(props.width * scale)
  const backingH = Math.round(props.height * scale)
  if (panel.width !== backingW || panel.height !== backingH) {
    panel.width = backingW
    panel.height = backingH
  }
  ctx.setTransform(scale, 0, 0, scale, 0, 0)

  props.drawContent(ctx, props.width, props.height)
  drawStageOverlay(ctx, props.width, props.height, {
    boxes: props.adapter.getBoxes(),
    selection: props.adapter.getSelection(),
    marquee: controller.marquee.value,
    guides: controller.guides.value,
    zoom: zoom.value,
  })
})

onMounted(() => {
  // Font loading can change metrics-only layouts; refit is harmless.
  void document.fonts.ready.then(() => fit())
})

defineExpose({ fit, zoom, panX, panY })
</script>

<template>
  <div
    :ref="(el) => { viewport.container.value = el as HTMLDivElement | null }"
    class="stage"
    :class="{ pan: spaceHeld }"
    :style="{ cursor: controller.hoverCursor.value ?? (spaceHeld ? 'grab' : 'default') }"
    @wheel="onWheel"
    @pointerdown="controller.onPointerdown"
    @pointermove="controller.onPointermove"
    @pointerup="controller.onPointerup"
    @pointercancel="controller.onPointerup"
  >
    <div class="canvas-holder" :style="transformStyle">
      <canvas ref="canvasEl" class="stage-canvas" :class="{ pixelated }"></canvas>
    </div>
    <div class="zoom-label">{{ Math.round(zoom * 100) }}%</div>
  </div>
</template>

<style scoped>
.stage {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    repeating-conic-gradient(#1a1a1a 0% 25%, #151515 0% 50%) 0 0 / 24px 24px;
  touch-action: none;
}

.stage.pan {
  cursor: grab;
}

.stage.pan:active {
  cursor: grabbing;
}

.canvas-holder {
  position: relative;
  flex: none;
  box-shadow: 0 0 0 1px var(--border), 0 6px 30px rgba(0, 0, 0, 0.5);
}

.stage-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.stage-canvas.pixelated {
  image-rendering: pixelated;
}

.zoom-label {
  position: absolute;
  left: 10px;
  bottom: 8px;
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 8px;
  pointer-events: none;
}
</style>
