<script setup lang="ts">
/**
 * ARGB device designer: YAML source of truth for one device definition
 * with a live canvas preview. The canvas supports selecting and dragging
 * shapes; precise coordinates, paints and generators live in the YAML
 * panel and toolbar. LED shapes are tinted by their index so the chain
 * order stays readable.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import type { DecorShape, LedShape } from '../../argb/types'
import { defBounds, ledHue, shapeCenter, shapeExtent } from '../../argb/deviceDef'
import { useDeviceDesigner } from '../../argb/designerStore'
import type { ShapeRef } from '../../argb/designerStore'

const props = defineProps<{ id?: string | null }>()
const emit = defineEmits<{ close: [] }>()

const designer = useDeviceDesigner()
const { state } = designer

const canvas = ref<HTMLCanvasElement | null>(null)
const genKind = ref<'strip' | 'ring' | 'dual'>('strip')
const genCount = ref(24)
const genSide = ref(8)

const CANVAS_W = 420
const CANVAS_H = 420

/** Fit of definition-local coordinates into the canvas. */
function viewTransform(doc: NonNullable<typeof state.doc>): {
  scale: number
  ox: number
  oy: number
} {
  const b = doc.size !== null
    ? { x: 0, y: 0, w: doc.size[0], h: doc.size[1] }
    : defBounds(doc)
  const scale = Math.min(
    (CANVAS_W - 40) / Math.max(b.w, 1),
    (CANVAS_H - 40) / Math.max(b.h, 1),
  )
  return {
    scale,
    ox: CANVAS_W / 2 - (b.x + b.w / 2) * scale,
    oy: CANVAS_H / 2 - (b.y + b.h / 2) * scale,
  }
}

function toLocal(px: number, py: number): { x: number; y: number } {
  const doc = state.doc
  if (doc === null) return { x: 0, y: 0 }
  const view = viewTransform(doc)
  return { x: (px - view.ox) / view.scale, y: (py - view.oy) / view.scale }
}

function paintDecorShape(
  ctx: CanvasRenderingContext2D,
  shape: DecorShape,
): void {
  ctx.globalAlpha = shape.opacity
  traceShape(ctx, shape)
  if (shape.type !== 'polyline') {
    if (shape.fill) {
      ctx.fillStyle = shape.fill_color
      ctx.fill()
    }
    if (shape.stroke_width > 0) {
      ctx.strokeStyle = shape.stroke_color
      ctx.lineWidth = shape.stroke_width
      ctx.stroke()
    }
  } else if (shape.stroke_width > 0) {
    ctx.strokeStyle = shape.stroke_color
    ctx.lineWidth = shape.stroke_width
    ctx.stroke()
  }
  ctx.globalAlpha = 1
}

function traceShape(ctx: CanvasRenderingContext2D, shape: LedShape | DecorShape): void {
  ctx.beginPath()
  if (shape.type === 'rect') {
    ctx.roundRect(shape.rect[0], shape.rect[1], shape.rect[2], shape.rect[3], shape.radius ?? 0)
  } else if (shape.type === 'circle') {
    ctx.arc(shape.center[0], shape.center[1], shape.radius, 0, Math.PI * 2)
  } else {
    ctx.moveTo(shape.points[0][0], shape.points[0][1])
    for (let i = 1; i < shape.points.length; i += 1) {
      ctx.lineTo(shape.points[i][0], shape.points[i][1])
    }
    if (shape.type !== 'polyline') ctx.closePath()
  }
}

function draw(): void {
  const el = canvas.value
  const doc = state.doc
  if (el === null || doc === null) return
  const ctx = el.getContext('2d')
  if (ctx === null) return
  ctx.clearRect(0, 0, CANVAS_W, CANVAS_H)
  ctx.fillStyle = '#101210'
  ctx.fillRect(0, 0, CANVAS_W, CANVAS_H)

  const view = viewTransform(doc)
  ctx.save()
  ctx.translate(view.ox, view.oy)
  ctx.scale(view.scale, view.scale)

  // Local grid.
  const b = doc.size !== null
    ? { x: 0, y: 0, w: doc.size[0], h: doc.size[1] }
    : defBounds(doc)
  ctx.strokeStyle = 'rgba(255,255,255,0.06)'
  ctx.lineWidth = 1 / view.scale
  ctx.beginPath()
  for (let gx = Math.ceil(b.x / 10) * 10; gx <= b.x + b.w; gx += 10) {
    ctx.moveTo(gx, b.y)
    ctx.lineTo(gx, b.y + b.h)
  }
  for (let gy = Math.ceil(b.y / 10) * 10; gy <= b.y + b.h; gy += 10) {
    ctx.moveTo(b.x, gy)
    ctx.lineTo(b.x + b.w, gy)
  }
  ctx.stroke()

  for (const shape of doc.decor) paintDecorShape(ctx, shape)
  doc.leds.forEach((led, i) => {
    traceShape(ctx, led)
    ctx.fillStyle = ledHue(i, doc.leds.length)
    ctx.fill()
    if (led.stroke_color && (led.stroke_width ?? 0) > 0) {
      ctx.strokeStyle = led.stroke_color
      ctx.lineWidth = led.stroke_width ?? 1
      ctx.stroke()
    }
  })

  // Selected shape outline.
  const sel = state.selected
  const selShape =
    sel !== null ? (sel.list === 'leds' ? doc.leds[sel.index] : doc.decor[sel.index]) : null
  if (selShape !== undefined && selShape !== null) {
    const c = shapeCenter(selShape)
    const ext = shapeExtent(selShape) + 4
    ctx.strokeStyle = '#4aa3ff'
    ctx.lineWidth = 1.5 / view.scale
    ctx.setLineDash([4 / view.scale, 3 / view.scale])
    ctx.strokeRect(c.x - ext, c.y - ext, ext * 2, ext * 2)
    ctx.setLineDash([])
  }
  ctx.restore()
}

watch(
  () => [state.yamlText, state.selected],
  () => draw(),
  { deep: true },
)
watchEffect(() => {
  if (canvas.value !== null) draw()
})

// Dragging: pick the topmost shape under the pointer, then shift it.
let drag: { startX: number; startY: number; moved: boolean } | null = null

function hitShape(px: number, py: number): ShapeRef | null {
  const doc = state.doc
  if (doc === null) return null
  const p = toLocal(px, py)
  const hit = (shape: LedShape | DecorShape): boolean => {
    const c = shapeCenter(shape)
    const ext = shapeExtent(shape)
    return Math.abs(p.x - c.x) <= ext && Math.abs(p.y - c.y) <= ext
  }
  for (let i = doc.leds.length - 1; i >= 0; i -= 1) {
    if (hit(doc.leds[i])) return { list: 'leds', index: i }
  }
  for (let i = doc.decor.length - 1; i >= 0; i -= 1) {
    if (hit(doc.decor[i])) return { list: 'decor', index: i }
  }
  return null
}

function onPointerDown(event: PointerEvent): void {
  const el = canvas.value
  if (el === null) return
  const rect = el.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * CANVAS_W
  const y = ((event.clientY - rect.top) / rect.height) * CANVAS_H
  const ref = hitShape(x, y)
  designer.select(ref)
  if (ref !== null) {
    const local = toLocal(x, y)
    drag = { startX: local.x, startY: local.y, moved: false }
    el.setPointerCapture(event.pointerId)
  }
}

function onPointerMove(event: PointerEvent): void {
  if (drag === null) return
  const el = canvas.value
  if (el === null) return
  const rect = el.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * CANVAS_W
  const y = ((event.clientY - rect.top) / rect.height) * CANVAS_H
  const local = toLocal(x, y)
  const dx = Math.round(local.x - drag.startX)
  const dy = Math.round(local.y - drag.startY)
  if (dx !== 0 || dy !== 0) {
    designer.moveSelectedBy(dx, dy)
    // The doc re-parses after each move; anchor the drag to the new doc.
    drag.startX = local.x
    drag.startY = local.y
    drag.moved = true
  }
}

function onPointerUp(): void {
  drag = null
}

function onGenerate(): void {
  if (
    (state.doc?.leds.length ?? 0) > 0 &&
    !window.confirm('Replace all shapes with the generated design?')
  ) {
    return
  }
  designer.generate(genKind.value, Math.max(1, genCount.value), Math.max(0, genSide.value))
}

async function onSave(): Promise<void> {
  await designer.save()
}

async function onSaveClose(): Promise<void> {
  const ok = await designer.save()
  if (ok) emit('close')
}

function requestClose(): void {
  if (state.dirty && !window.confirm('Discard unsaved changes?')) return
  emit('close')
}

function onKeydown(event: KeyboardEvent): void {
  const typing = event.target instanceof HTMLElement && event.target.tagName === 'TEXTAREA'
  if (event.key === 'Escape') {
    if (typing) return
    if (state.selected !== null) {
      designer.select(null)
      return
    }
    requestClose()
    return
  }
  if ((event.key === 'Delete' || event.key === 'Backspace') && !typing) {
    event.preventDefault()
    designer.deleteSelected()
  }
}

onMounted(() => {
  void designer.open(props.id ?? null)
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

const ledCount = computed(() => state.doc?.leds.length ?? 0)
const decorCount = computed(() => state.doc?.decor.length ?? 0)
</script>

<template>
  <Teleport to="body">
    <div class="designer-overlay" @click.self="requestClose()">
      <div class="designer-modal">
        <div class="toolbar">
          <span class="title">Device designer</span>
          <span class="mono">{{ state.defId === null ? 'new' : state.defId }}</span>
          <span class="spacer" />
          <span class="counter" :class="{ bad: ledCount === 0 }">
            {{ ledCount }} LEDs · {{ decorCount }} decor
          </span>
          <button :disabled="state.doc === null" @click="onSave()">Save</button>
          <button class="primary" :disabled="state.doc === null" @click="onSaveClose">Save &amp; close</button>
          <button class="danger" @click="requestClose()">Close</button>
        </div>

        <div class="body">
          <div class="left-pane">
            <div class="shape-bar">
              <span class="group">LED:</span>
              <button class="small" :disabled="state.doc === null" @click="designer.addShape('leds')">+ LED</button>
              <span class="group">Decor:</span>
              <button class="small" :disabled="state.doc === null" @click="designer.addShape('decor')">+ Rect</button>
              <span class="grow" />
              <select v-model="genKind" class="small">
                <option value="strip">Strip</option>
                <option value="ring">Ring</option>
                <option value="dual">Dual</option>
              </select>
              <input v-model="genCount" type="number" min="1" max="512" class="small num" title="LED count" />
              <input v-if="genKind === 'dual'" v-model="genSide" type="number" min="0" max="256" class="small num" title="Side LEDs" />
              <button class="small" :disabled="state.doc === null" @click="onGenerate">Generate</button>
              <button class="small danger" :disabled="state.selected === null" @click="designer.deleteSelected()">Del</button>
            </div>
            <canvas
              ref="canvas"
              class="design-canvas"
              :width="CANVAS_W"
              :height="CANVAS_H"
              @pointerdown="onPointerDown"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="onPointerUp"
            />
            <div class="hint">
              Drag shapes to move them · Del deletes the selection · LED colors show chain order
            </div>
          </div>

          <div class="right-pane">
            <textarea
              class="yaml"
              spellcheck="false"
              :value="state.yamlText"
              @input="designer.setYamlText(($event.target as HTMLTextAreaElement).value)"
            />
            <div v-if="state.syntaxError !== null" class="error-strip">{{ state.syntaxError }}</div>
            <div v-else class="hint">YAML is the source of truth — edit shapes, paints and size here.</div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.designer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
}

.designer-modal {
  width: min(920px, 92vw);
  height: min(640px, 88vh);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}

.title {
  font-weight: 600;
  font-size: 13px;
}

.spacer,
.grow {
  flex: 1;
}

.counter {
  font-size: 12px;
  color: var(--text-dim);
}

.counter.bad {
  color: var(--danger);
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.left-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 10px;
  gap: 8px;
}

.shape-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.group {
  font-size: 11px;
  color: var(--text-dim);
}

.design-canvas {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  touch-action: none;
}

.right-pane {
  width: 380px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border-left: 1px solid var(--border);
  min-height: 0;
}

.yaml {
  flex: 1;
  min-height: 0;
  resize: none;
  font-family: ui-monospace, 'Cascadia Mono', 'Segoe UI Mono', Menlo, Consolas, monospace;
  font-size: 12px;
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

.hint {
  font-size: 11px;
  color: var(--text-dim);
}

.num {
  width: 56px;
}
</style>
