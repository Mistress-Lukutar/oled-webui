<script setup lang="ts">
/**
 * Timeline: transport (play/pause, loop duration), a scrub ruler with
 * playhead and per-widget rows with curves of their expression-driven
 * properties (offset_x/offset_y/opacity/rotation/visible). The scene
 * schema is procedural (expressions of t), so the timeline previews and
 * scrubs those curves; `animate.value` blocks are shown as badges.
 */
import { computed, onBeforeUnmount, ref, watchEffect } from 'vue'
import { editor } from '../../scene-editor/docStore'
import { Expression } from '../../scene-editor/exprEval'
import { expandDocument } from '../../scene-editor/expand'
import { entryLabel, isComponentInstance } from '../../scene-editor/types'
import type { EntryRaw, SceneDocumentRaw } from '../../scene-editor/types'

const { state } = editor

const collapsed = ref(false)
const playing = computed(() => state.playing)

const PROPS: Array<{ key: string; color: string; label: string }> = [
  { key: 'offset_x', color: '#4FC3F7', label: 'x' },
  { key: 'offset_y', color: '#FFB74D', label: 'y' },
  { key: 'opacity', color: '#CE93D8', label: 'o' },
  { key: 'rotation', color: '#A5D6A7', label: 'r' },
  { key: 'visible', color: '#90CAF9', label: 'v' },
]

interface Curve {
  color: string
  samples: number[]
  ok: boolean
}

interface Row {
  index: number
  label: string
  isInstance: boolean
  curves: Curve[]
  hasValueAnim: boolean
  animateEasing: string | null
}

const redrawTick = ref(0)

const rows = computed<Row[]>(() => {
  void redrawTick.value
  const doc = state.doc
  if (doc === null) return []
  const widgets = editor.getWidgets()
  const expansion = expandDocument(doc as SceneDocumentRaw, state.components)
  // Errors from expansion are surfaced elsewhere; skip those entries here.
  const perSource = new Map<number, EntryRaw[]>()
  for (const expanded of expansion.entries) {
    const list = perSource.get(expanded.sourceIndex) ?? []
    list.push(expanded.widget)
    perSource.set(expanded.sourceIndex, list)
  }
  const result: Row[] = []
  widgets.forEach((entry, index) => {
    const children = perSource.get(index) ?? []
    const curves: Curve[] = []
    let hasValueAnim = false
    let animateEasing: string | null = null
    const check = (widget: Record<string, unknown>): void => {
      const animate = widget['animate']
      if (
        animate !== null &&
        typeof animate === 'object' &&
        (animate as Record<string, unknown>)['value'] !== undefined
      ) {
        hasValueAnim = true
        const spec = (animate as Record<string, Record<string, unknown>>)['value']
        animateEasing = typeof spec?.['easing'] === 'string' ? spec['easing'] : 'ease-out-cubic'
      }
      for (const prop of PROPS) {
        const value = widget[prop.key]
        if (typeof value !== 'string') continue
        try {
          const expr = new Expression(value)
          const samples: number[] = []
          const steps = 96
          for (let i = 0; i <= steps; i += 1) {
            samples.push(expr.evaluate({ t: (i / steps) * state.loopDuration, dt: 0.05, v: 0 }))
          }
          curves.push({ color: prop.color, samples, ok: true })
        } catch {
          curves.push({ color: prop.color, samples: [], ok: false })
        }
      }
    }
    if (isComponentInstance(entry)) {
      for (const child of children) check(child as Record<string, unknown>)
    } else {
      check(entry as Record<string, unknown>)
    }
    if (curves.length === 0 && !hasValueAnim) return
    result.push({
      index,
      label: entryLabel(entry, index),
      isInstance: isComponentInstance(entry),
      curves,
      hasValueAnim,
      animateEasing,
    })
  })
  return result
})

// ----------------------------------------------------------------------
// Curve drawing
// ----------------------------------------------------------------------

const curveCanvases = ref<Map<number, HTMLCanvasElement>>(new Map())

function setCurveRef(index: number, el: unknown): void {
  if (el instanceof HTMLCanvasElement) curveCanvases.value.set(index, el)
  else curveCanvases.value.delete(index)
}

function drawCurve(canvas: HTMLCanvasElement, row: Row): void {
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  if (width === 0 || height === 0) return
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
  const ctx = canvas.getContext('2d')
  if (ctx === null) return
  ctx.clearRect(0, 0, width, height)
  for (const curve of row.curves) {
    if (!curve.ok || curve.samples.length < 2) continue
    let min = Infinity
    let max = -Infinity
    for (const s of curve.samples) {
      min = Math.min(min, s)
      max = Math.max(max, s)
    }
    const span = max - min
    ctx.strokeStyle = curve.color
    ctx.lineWidth = 1.5
    ctx.beginPath()
    curve.samples.forEach((s, i) => {
      const x = (i / (curve.samples.length - 1)) * width
      const y = span === 0 ? height / 2 : 2 + (height - 4) * (1 - (s - min) / span)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }
}

watchEffect(() => {
  void rows.value
  void state.loopDuration
  void redrawTick.value
  requestAnimationFrame(() => {
    for (const [index, canvas] of curveCanvases.value) {
      const row = rows.value.find((r) => r.index === index)
      if (row !== undefined) drawCurve(canvas, row)
    }
  })
})

// ----------------------------------------------------------------------
// Playback: interval-driven so preview keeps ticking even when the pane
// is throttled by the browser (rAF pauses in background panes).
// ----------------------------------------------------------------------

let intervalId: number | null = null
let lastTick: number | null = null

function tick(now: number): void {
  if (lastTick !== null) {
    const dt = Math.min(0.25, (now - lastTick) / 1000)
    let next = state.time + dt
    if (next > state.loopDuration) next -= state.loopDuration
    editor.setTime(next)
  }
  lastTick = now
}

function togglePlay(): void {
  if (state.playing) {
    editor.setPlaying(false)
    stopInterval()
  } else {
    editor.setPlaying(true)
    lastTick = null
    intervalId = window.setInterval(() => tick(performance.now()), 16)
  }
}

function stopInterval(): void {
  if (intervalId !== null) {
    window.clearInterval(intervalId)
    intervalId = null
  }
  lastTick = null
}

onBeforeUnmount(() => {
  stopInterval()
  editor.setPlaying(false)
})

// ----------------------------------------------------------------------
// Scrubbing
// ----------------------------------------------------------------------

const track = ref<HTMLDivElement | null>(null)

function scrubTo(event: PointerEvent): void {
  const el = track.value
  if (el === null) return
  const rect = el.getBoundingClientRect()
  const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  editor.setTime(fraction * state.loopDuration)
}

let scrubbing = false

function onTrackDown(event: PointerEvent): void {
  scrubbing = true
  try {
    track.value?.setPointerCapture(event.pointerId)
  } catch {
    // Synthetic pointers (tests) have no active pointer to capture.
  }
  scrubTo(event)
}

function onTrackMove(event: PointerEvent): void {
  if (scrubbing) scrubTo(event)
}

function onTrackUp(): void {
  scrubbing = false
}

function selectRow(index: number): void {
  editor.setSelection([index])
}

function timeLabel(t: number): string {
  return `${t.toFixed(2)}s`
}

function loopInput(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value) && value > 0) editor.setLoopDuration(value)
}
</script>

<template>
  <div class="timeline" :class="{ collapsed }">
    <div class="transport">
      <button class="play" :title="playing ? 'Pause' : 'Play'" @click="togglePlay">
        {{ playing ? '⏸' : '▶' }}
      </button>
      <span class="time">{{ timeLabel(state.time) }}</span>
      <span class="sep">/</span>
      <input
        class="loop"
        type="number"
        min="0.5"
        step="0.5"
        :value="state.loopDuration"
        title="Loop duration in seconds (window for expression preview)"
        @change="loopInput"
      />
      <span class="hint">s loop · scrub or press play to preview expressions</span>
      <span class="spacer"></span>
      <button class="mini-btn" @click="collapsed = !collapsed">
        {{ collapsed ? '▲ Timeline' : '▼' }}
      </button>
    </div>

    <div v-if="!collapsed" class="body">
      <div class="labels">
        <div class="ruler-spacer"></div>
        <div
          v-for="row in rows"
          :key="row.index"
          class="label-row"
          :class="{ selected: state.selection.includes(row.index) }"
          @click="selectRow(row.index)"
        >
          <span class="label">{{ row.label }}</span>
          <span
            v-if="row.hasValueAnim"
            class="badge"
            :title="`value animation: ${row.animateEasing}`"
          >{{ row.animateEasing }}</span>
        </div>
        <div v-if="rows.length === 0" class="empty">
          No animated properties. Give a widget an fx expression (offset, opacity, rotation) to see its curve here.
        </div>
      </div>
      <div ref="track" class="track" @pointerdown="onTrackDown" @pointermove="onTrackMove" @pointerup="onTrackUp" @pointercancel="onTrackUp">
        <div class="ruler">
          <div
            v-for="tickIndex in 11"
            :key="tickIndex"
            class="tick"
            :style="{ left: `${(tickIndex - 1) * 10}%` }"
          >
            <span>{{ ((tickIndex - 1) * state.loopDuration / 10).toFixed(1) }}</span>
          </div>
        </div>
        <div class="rows">
          <div
            v-for="row in rows"
            :key="row.index"
            class="curve-row"
            :class="{ selected: state.selection.includes(row.index) }"
            @click="selectRow(row.index)"
          >
            <canvas
              :ref="(el) => setCurveRef(row.index, el)"
              class="curve"
            ></canvas>
            <div class="playhead" :style="{ left: `${(state.time / state.loopDuration) * 100}%` }"></div>
          </div>
          <div v-if="rows.length === 0" class="curve-empty"></div>
          <div class="playhead main" :style="{ left: `${(state.time / state.loopDuration) * 100}%` }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  flex: none;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
  max-height: 170px;
}

.timeline.collapsed {
  max-height: none;
}

.transport {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
}

.play {
  width: 30px;
  padding: 4px 0;
  font-size: 12px;
}

.time {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  color: var(--accent);
  min-width: 52px;
  text-align: center;
}

.sep {
  color: var(--text-dim);
}

.loop {
  width: 60px;
  padding: 3px 6px;
  font-size: 12px;
}

.hint {
  font-size: 11px;
  color: var(--text-dim);
}

.spacer {
  flex: 1;
}

.mini-btn {
  padding: 3px 8px;
  font-size: 11px;
}

.body {
  display: flex;
  min-height: 0;
  overflow: hidden;
  border-top: 1px solid var(--border);
}

.labels {
  width: 220px;
  flex: none;
  overflow: hidden;
  border-right: 1px solid var(--border);
}

.ruler-spacer {
  height: 18px;
  border-bottom: 1px solid var(--border);
}

.label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 8px;
  font-size: 11px;
  cursor: pointer;
  border-bottom: 1px solid rgba(51, 51, 51, 0.5);
  overflow: hidden;
}

.label-row:hover {
  background: var(--bg-input);
}

.label-row.selected {
  background: var(--accent-dim);
  color: #fff;
}

.label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  font-size: 9px;
  padding: 0 5px;
}

.empty {
  color: var(--text-dim);
  font-size: 11px;
  padding: 8px;
}

.track {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: col-resize;
  min-width: 0;
}

.ruler {
  position: relative;
  height: 18px;
  border-bottom: 1px solid var(--border);
}

.tick {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px solid rgba(51, 51, 51, 0.6);
  padding-left: 3px;
  font-size: 9px;
  color: var(--text-dim);
  pointer-events: none;
}

.rows {
  position: relative;
}

.curve-row {
  position: relative;
  height: 26px;
  border-bottom: 1px solid rgba(51, 51, 51, 0.5);
}

.curve-row.selected {
  background: rgba(53, 201, 142, 0.08);
}

.curve {
  display: block;
  width: 100%;
  height: 100%;
}

.curve-empty {
  height: 40px;
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--accent);
  pointer-events: none;
}

.playhead::before {
  content: '';
  position: absolute;
  top: 0;
  left: -4px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 6px solid var(--accent);
}

.playhead.main {
  top: -18px;
  height: calc(100% + 18px);
}
</style>
