<script setup lang="ts">
/**
 * Scene viewport: canvas mirror of the server renderer with zoom/pan.
 * Selection handles and drag interactions arrive in the next stage.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { expandDocument } from '../../scene-editor/expand'
import { evaluateEntries, makePlaceholderProvider } from '../../scene-editor/runtime'
import { createImageCache, drawScene } from '../../scene-editor/render/draw'
import { ensureFont } from '../../scene-editor/render/fonts'
import type { SceneDocumentRaw } from '../../scene-editor/types'

const { state: appState } = useDisplayStore()
const { state } = editor

const container = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)

const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const spaceHeld = ref(false)
const panning = ref(false)
const redrawTick = ref(0)

const provider = makePlaceholderProvider()
const images = createImageCache(() => {
  redrawTick.value += 1
})

const panelWidth = computed(
  () => state.resolutionOverride?.width ?? appState.resolution.width,
)
const panelHeight = computed(
  () => state.resolutionOverride?.height ?? appState.resolution.height,
)

const expansion = computed(() => {
  // Depends on doc + components; redrawTick keeps async asset loads in sync.
  void redrawTick.value
  if (state.doc === null) return { entries: [], errors: [] as string[] }
  return expandDocument(state.doc as SceneDocumentRaw, state.components)
})

watchEffect(() => {
  // Preload custom fonts used by text widgets; resolution bumps redrawTick.
  const doc = state.doc
  if (doc === null) return
  for (const widget of editor.getWidgets()) {
    const style = widget['style']
    const family =
      style !== null && typeof style === 'object'
        ? (style as Record<string, unknown>)['family']
        : null
    if (typeof family === 'string' && family !== '') {
      void ensureFont(state.sceneId, family).then((family_) => {
        if (family_ !== null) redrawTick.value += 1
      })
    }
  }
})

function fit(): void {
  const box = container.value
  if (box === null) return
  const margin = 32
  const zw = (box.clientWidth - margin) / panelWidth.value
  const zh = (box.clientHeight - margin) / panelHeight.value
  zoom.value = Math.max(0.05, Math.min(zw, zh))
  panX.value = 0
  panY.value = 0
}

let observer: ResizeObserver | null = null

watch([panelWidth, panelHeight], () => fit())

onMounted(() => {
  fit()
  // The container size can settle across the first frames (CSS/fonts);
  // re-fit until the layout stabilizes.
  requestAnimationFrame(() => fit())
  void document.fonts.ready.then(() => fit())
  observer = new ResizeObserver(() => fit())
  if (container.value !== null) observer.observe(container.value)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
})

function onKeydown(event: KeyboardEvent): void {
  if (event.code === 'Space' && isCanvasTarget(event)) {
    spaceHeld.value = true
    event.preventDefault()
  }
}

function onKeyup(event: KeyboardEvent): void {
  if (event.code === 'Space') spaceHeld.value = false
}

function isCanvasTarget(event: Event): boolean {
  return (
    container.value !== null &&
    container.value.contains(event.target as Node) &&
    !isFormTarget(event.target)
  )
}

function isFormTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
  const next = Math.max(0.05, Math.min(12, zoom.value * factor))
  // Keep the point under the cursor stationary.
  const rect = canvas.value?.getBoundingClientRect()
  if (rect) {
    const cx = event.clientX - (rect.left + rect.width / 2)
    const cy = event.clientY - (rect.top + rect.height / 2)
    const scale = next / zoom.value
    panX.value = cx - (cx - panX.value) * scale
    panY.value = cy - (cy - panY.value) * scale
  }
  zoom.value = next
}

function onPointerdown(event: PointerEvent): void {
  if (spaceHeld.value || event.button === 1) {
    panning.value = true
    ;(event.target as Element).setPointerCapture?.(event.pointerId)
    event.preventDefault()
  }
}

function onPointermove(event: PointerEvent): void {
  if (!panning.value) return
  panX.value += event.movementX
  panY.value += event.movementY
}

function onPointerup(): void {
  panning.value = false
}

const transformStyle = computed(() => ({
  width: `${panelWidth.value * zoom.value}px`,
  height: `${panelHeight.value * zoom.value}px`,
  transform: `translate(${panX.value}px, ${panY.value}px)`,
}))

// Main draw effect: re-runs whenever the document, time or view changes.
watchEffect(() => {
  const panel = canvas.value
  if (panel === null) return
  const ctx = panel.getContext('2d')
  if (ctx === null) return
  void zoom.value
  void state.time
  void redrawTick.value

  const width = panelWidth.value
  const height = panelHeight.value
  if (panel.width !== width || panel.height !== height) {
    panel.width = width
    panel.height = height
  }
  const doc = state.doc
  const background = (doc?.background ?? []) as readonly Record<string, unknown>[]
  const evaluated = evaluateEntries(expansion.value.entries, {
    time: state.time,
    maxFps: typeof doc?.max_fps === 'number' ? doc.max_fps : 20,
    provider,
  })
  drawScene({
    ctx,
    background,
    entries: evaluated,
    width,
    height,
    sceneId: state.sceneId,
    images,
    showGrid: true,
    gridPixelSize: 20,
  })
})
</script>

<template>
  <div
    ref="container"
    class="viewport"
    :class="{ pan: spaceHeld || panning }"
    @wheel="onWheel"
    @pointerdown="onPointerdown"
    @pointermove="onPointermove"
    @pointerup="onPointerup"
    @pointercancel="onPointerup"
  >
    <div class="canvas-holder" :style="transformStyle">
      <canvas ref="canvas" class="scene-canvas"></canvas>
    </div>
    <div class="zoom-label">{{ Math.round(zoom * 100) }}%</div>
  </div>
</template>

<style scoped>
.viewport {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    repeating-conic-gradient(#1a1a1a 0% 25%, #151515 0% 50%) 0 0 / 24px 24px;
}

.viewport.pan {
  cursor: grab;
}

.viewport.pan:active {
  cursor: grabbing;
}

.canvas-holder {
  position: relative;
  flex: none;
  box-shadow: 0 0 0 1px var(--border), 0 6px 30px rgba(0, 0, 0, 0.5);
}

.scene-canvas {
  display: block;
  width: 100%;
  height: 100%;
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
