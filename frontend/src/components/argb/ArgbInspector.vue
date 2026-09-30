<script setup lang="ts">
/**
 * Inspector panel: properties of the selected device, layer (effect
 * params + mask) or header; layout globals when nothing is selected.
 */
import { computed } from 'vue'
import { useArgbStore } from '../../argb/store'
import type { ArgbDevice, ArgbHeader, ArgbLayer, EffectType, GradientEffect } from '../../argb/types'
import { DATA_SOURCES } from '../../scene-editor/types'

const store = useArgbStore()
const { state } = store

const EFFECT_TYPES: { value: EffectType; label: string }[] = [
  { value: 'fill', label: 'Fill' },
  { value: 'gradient', label: 'Gradient' },
  { value: 'rainbow', label: 'Rainbow' },
  { value: 'breathing', label: 'Breathing' },
  { value: 'comet', label: 'Comet (moving pixel)' },
  { value: 'scanner', label: 'Scanner' },
  { value: 'meter', label: 'Meter (data source)' },
]

const selectedDevice = computed<ArgbDevice | null>(() =>
  state.selection.kind === 'device'
    ? (state.layout.devices.find((d) => d.id === state.selection.id) ?? null)
    : null,
)

const selectedLayer = computed<ArgbLayer | null>(() =>
  state.selection.kind === 'layer'
    ? (state.layout.layers.find((l) => l.id === state.selection.id) ?? null)
    : null,
)

const selectedHeader = computed<ArgbHeader | null>(() =>
  state.selection.kind === 'header'
    ? (state.layout.headers.find((h) => h.id === state.selection.id) ?? null)
    : null,
)

const editingMask = computed(
  () => state.maskLayerId !== null && state.maskLayerId === selectedLayer.value?.id,
)

const deviceHeader = computed<ArgbHeader | null>(() =>
  selectedDevice.value !== null
    ? (state.layout.headers.find((h) => h.id === selectedDevice.value?.header_id) ?? null)
    : null,
)

const chainUsage = computed(() => {
  const header = deviceHeader.value
  if (header === null) return null
  return store.headerUsage(header)
})

const chainPosition = computed(() => {
  const header = deviceHeader.value
  const device = selectedDevice.value
  if (header === null || device === null) return 0
  return header.devices.indexOf(device.id) + 1
})

function num(event: Event): number {
  const value = Number((event.target as HTMLInputElement).value)
  return Number.isFinite(value) ? value : 0
}

function updateDeviceField(field: keyof ArgbDevice, value: unknown): void {
  const device = selectedDevice.value
  if (device !== null) store.actions.updateDevice(device.id, { [field]: value })
}

function onDeviceDefinitionChange(event: Event): void {
  const device = selectedDevice.value
  if (device === null) return
  store.actions.changeDeviceDefinition(
    device.id,
    (event.target as HTMLSelectElement).value,
  )
}

function upd(field: string, value: unknown): void {
  const layer = selectedLayer.value
  if (layer !== null) store.actions.updateEffect(layer.id, { [field]: value })
}

function stops(): GradientEffect['stops'] {
  const layer = selectedLayer.value
  if (layer === null || layer.effect.type !== 'gradient') return []
  return layer.effect.stops.map((stop) => ({ ...stop }))
}

function updateStop(index: number, patch: Partial<{ pos: number; color: string }>): void {
  const next = stops()
  if (next.length === 0) return
  next[index] = { ...next[index], ...patch }
  upd('stops', next)
}

function addStop(): void {
  const next = stops()
  if (next.length === 0) return
  next.push({ pos: 1, color: '#FFFFFF' })
  upd('stops', next)
}

function removeStop(index: number): void {
  const next = stops()
  if (next.length <= 2) return
  next.splice(index, 1)
  upd('stops', next)
}

function addBreathColor(): void {
  const layer = selectedLayer.value
  if (layer === null || layer.effect.type !== 'breathing') return
  upd('colors', [...layer.effect.colors, '#FFFFFF'])
}

function updateBreathColor(index: number, event: Event): void {
  const layer = selectedLayer.value
  if (layer === null || layer.effect.type !== 'breathing') return
  const value = (event.target as HTMLInputElement).value
  upd(
    'colors',
    layer.effect.colors.map((c, i) => (i === index ? value : c)),
  )
}

function removeBreathColor(index: number): void {
  const layer = selectedLayer.value
  if (layer === null || layer.effect.type !== 'breathing') return
  if (layer.effect.colors.length <= 1) return
  upd(
    'colors',
    layer.effect.colors.filter((_, i) => i !== index),
  )
}

function setLayoutFps(event: Event): void {
  const value = Math.round(Number((event.target as HTMLInputElement).value) || 30)
  store.mutate((layout) => {
    layout.fps = Math.min(60, Math.max(1, value))
  })
}

function setLayoutBrightness(event: Event): void {
  const value = Math.round(Number((event.target as HTMLInputElement).value) || 0)
  store.mutate((layout) => {
    layout.brightness = Math.min(200, Math.max(0, value))
  })
}

/** Human-readable mask run list, e.g. "Strip 1: 0-4, 8". */
function maskSummary(): { name: string; text: string }[] {
  const layer = selectedLayer.value
  if (layer === null) return []
  const out: { name: string; text: string }[] = []
  for (const [deviceId, runs] of Object.entries(layer.mask.runs)) {
    const device = state.layout.devices.find((item) => item.id === deviceId)
    if (device === undefined || runs.length === 0) continue
    const text = runs.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(', ')
    out.push({ name: device.name, text })
  }
  return out
}

function togglePaint(): void {
  const layer = selectedLayer.value
  if (layer === null) return
  if (state.maskLayerId === layer.id) store.actions.stopMaskPaint()
  else {
    if (layer.mask.all) store.actions.maskFillAll(layer.id)
    store.actions.startMaskPaint(layer.id)
  }
}

function zoneLabel(index: number): string {
  const zone = state.status.zones.find((item) => item.index === index)
  if (zone === undefined) return `zone ${index}`
  const device = zone.device_name ? `${zone.device_name} · ` : ''
  return `${device}${zone.name} (${zone.leds} LEDs)`
}

function deviceLabel(id: string): string {
  const device = state.layout.devices.find((item) => item.id === id)
  return device === undefined ? '?' : `${device.name} · ${store.deviceLeds(device)} LEDs`
}

/** Empty input = auto capacity (follows the chain length). */
function onSizeInput(event: Event): void {
  const header = selectedHeader.value
  if (header === null) return
  const raw = (event.target as HTMLInputElement).value.trim()
  if (raw === '') {
    store.actions.updateHeader(header.id, { size: null })
    return
  }
  const value = Math.round(Number(raw))
  if (Number.isFinite(value) && value >= 1) {
    store.actions.updateHeader(header.id, { size: Math.min(1024, value) })
  }
}

function onZoneChange(event: Event): void {
  const header = selectedHeader.value
  if (header === null) return
  const index = num(event)
  const zone = state.status.zones.find((item) => item.index === index)
  // Adopt the reported capacity only when the zone has LEDs; ITE-style
  // zones report 0 until resized, which would wipe the size.
  store.actions.updateHeader(header.id, {
    zone_index: index,
    size:
      zone !== undefined && zone.leds > 0
        ? zone.leds
        : header.size,
  })
}
</script>

<template>
  <div class="inspector">
    <!-- ================= Device ================= -->
    <template v-if="selectedDevice !== null">
      <div class="head">
        <h3>Device</h3>
        <button
          class="danger small"
          @click="store.actions.deleteDevices(state.deviceSelection.length > 0 ? [...state.deviceSelection] : [selectedDevice.id])"
        >
          Delete{{ state.deviceSelection.length > 1 ? ` (${state.deviceSelection.length})` : '' }}
        </button>
      </div>

      <label class="field">
        <span>Name</span>
        <input
          :value="selectedDevice.name"
          maxlength="100"
          @input="updateDeviceField('name', ($event.target as HTMLInputElement).value)"
        />
      </label>

      <label class="field">
        <span>Definition</span>
        <select :value="selectedDevice.device" @change="onDeviceDefinitionChange">
          <option v-for="item in state.library" :key="item.id" :value="item.id">
            {{ item.name }} — {{ item.leds }} LEDs
          </option>
        </select>
      </label>

      <label class="field">
        <span>Header</span>
        <select
          :value="selectedDevice.header_id"
          @change="store.actions.assignDeviceToHeader(selectedDevice.id, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="h in state.layout.headers" :key="h.id" :value="h.id">
            {{ h.name }} — {{ zoneLabel(h.zone_index) }}
          </option>
        </select>
      </label>

      <div class="field">
        <span>Chain order</span>
        <div class="inline">
          <button class="small" :disabled="chainPosition <= 1" @click="store.actions.reorderDevice(selectedDevice.id, -1)">◀</button>
          <span class="mono">{{ chainPosition }} / {{ deviceHeader?.devices.length ?? 1 }}</span>
          <button
            class="small"
            :disabled="deviceHeader !== null && chainPosition >= deviceHeader.devices.length"
            @click="store.actions.reorderDevice(selectedDevice.id, 1)"
          >
            ▶
          </button>
        </div>
      </div>

      <p v-if="chainUsage !== null" class="hint" :class="{ warn: chainUsage.capacity !== null && chainUsage.used > chainUsage.capacity }">
        Chain: {{ chainUsage.used }}<template v-if="chainUsage.capacity !== null"> / {{ chainUsage.capacity }} LEDs</template>
      </p>

      <div class="grid2">
        <label class="field">
          <span>X</span>
          <input type="number" :value="selectedDevice.x" @input="updateDeviceField('x', num($event))" />
        </label>
        <label class="field">
          <span>Y</span>
          <input type="number" :value="selectedDevice.y" @input="updateDeviceField('y', num($event))" />
        </label>
        <label class="field">
          <span>Rotation°</span>
          <input type="number" min="-360" max="360" :value="selectedDevice.rotation" @input="updateDeviceField('rotation', num($event))" />
        </label>
        <label class="field">
          <span>Scale</span>
          <input type="number" min="0.2" max="5" step="0.1" :value="selectedDevice.scale" @input="updateDeviceField('scale', num($event))" />
        </label>
      </div>
    </template>

    <!-- ================= Layer ================= -->
    <template v-else-if="selectedLayer !== null">
      <div class="head">
        <h3>Layer</h3>
        <button class="danger small" @click="store.actions.deleteLayer(selectedLayer.id)">Delete</button>
      </div>

      <label class="field">
        <span>Name</span>
        <input
          :value="selectedLayer.name"
          maxlength="100"
          @input="store.actions.updateLayer(selectedLayer.id, { name: ($event.target as HTMLInputElement).value })"
        />
      </label>

      <div class="grid2">
        <label class="field">
          <span>Effect</span>
          <select
            :value="selectedLayer.effect.type"
            @change="store.actions.setEffectType(selectedLayer.id, ($event.target as HTMLSelectElement).value as EffectType)"
          >
            <option v-for="t in EFFECT_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </label>
        <label class="field">
          <span>Opacity</span>
          <input
            type="number" min="0" max="1" step="0.05"
            :value="selectedLayer.opacity"
            @input="store.actions.updateLayer(selectedLayer.id, { opacity: num($event) })"
          />
        </label>
      </div>

      <!-- Per-effect parameters -->
      <template v-if="selectedLayer.effect.type === 'fill'">
        <label class="field">
          <span>Color</span>
          <input type="color" :value="selectedLayer.effect.color" @input="upd('color', ($event.target as HTMLInputElement).value)" />
        </label>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'gradient'">
        <div class="field">
          <span>Color stops</span>
          <div v-for="(stop, i) in selectedLayer.effect.stops" :key="i" class="inline">
            <input
              type="number" min="0" max="1" step="0.05" :value="stop.pos"
              @input="updateStop(i, { pos: num($event) })"
            />
            <input
              type="color" :value="stop.color"
              @input="updateStop(i, { color: ($event.target as HTMLInputElement).value })"
            />
            <button class="small" :disabled="selectedLayer.effect.stops.length <= 2" @click="removeStop(i)">×</button>
          </div>
          <button class="small" @click="addStop">+ Stop</button>
        </div>
        <div class="grid2">
          <label class="field">
            <span>Tile (LEDs)</span>
            <input type="number" min="2" max="1024" :value="selectedLayer.effect.scale" @input="upd('scale', num($event))" />
          </label>
          <label class="field">
            <span>Speed (tiles/s)</span>
            <input type="number" min="-20" max="20" step="0.05" :value="selectedLayer.effect.speed" @input="upd('speed', num($event))" />
          </label>
        </div>
        <label class="field">
          <span>Mode</span>
          <select :value="selectedLayer.effect.mode" @change="upd('mode', ($event.target as HTMLSelectElement).value)">
            <option value="static">Static</option>
            <option value="scroll">Scroll</option>
            <option value="pingpong">Ping-pong</option>
          </select>
        </label>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'rainbow'">
        <div class="grid2">
          <label class="field">
            <span>Speed (cycles/s)</span>
            <input type="number" min="0" max="20" step="0.05" :value="selectedLayer.effect.speed" @input="upd('speed', num($event))" />
          </label>
          <label class="field">
            <span>Cycle (LEDs)</span>
            <input type="number" min="2" max="1024" :value="selectedLayer.effect.scale" @input="upd('scale', num($event))" />
          </label>
          <label class="field">
            <span>Direction</span>
            <select
              :value="String(selectedLayer.effect.direction)"
              @change="upd('direction', Number(($event.target as HTMLSelectElement).value))"
            >
              <option value="1">Forward</option>
              <option value="-1">Reverse</option>
            </select>
          </label>
          <label class="field">
            <span>Saturation</span>
            <input type="number" min="0" max="1" step="0.05" :value="selectedLayer.effect.saturation" @input="upd('saturation', num($event))" />
          </label>
        </div>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'breathing'">
        <div class="field">
          <span>Colors</span>
          <div v-for="(color, i) in selectedLayer.effect.colors" :key="i" class="inline">
            <input
              type="color"
              :value="color"
              @input="updateBreathColor(i, $event)"
            />
            <button class="small" :disabled="selectedLayer.effect.colors.length <= 1" @click="removeBreathColor(i)">×</button>
          </div>
          <button class="small" @click="addBreathColor">+ Color</button>
        </div>
        <div class="grid2">
          <label class="field">
            <span>Period (s)</span>
            <input type="number" min="0.1" max="60" step="0.1" :value="selectedLayer.effect.period" @input="upd('period', num($event))" />
          </label>
          <label class="field">
            <span>Min level</span>
            <input type="number" min="0" max="1" step="0.05" :value="selectedLayer.effect.min_level" @input="upd('min_level', num($event))" />
          </label>
        </div>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'comet'">
        <label class="field">
          <span>Color</span>
          <input type="color" :value="selectedLayer.effect.color" @input="upd('color', ($event.target as HTMLInputElement).value)" />
        </label>
        <div class="grid2">
          <label class="field">
            <span>Tail (LEDs)</span>
            <input type="number" min="0" max="512" :value="selectedLayer.effect.tail" @input="upd('tail', num($event))" />
          </label>
          <label class="field">
            <span>Speed (LEDs/s)</span>
            <input type="number" min="0" max="500" :value="selectedLayer.effect.speed" @input="upd('speed', num($event))" />
          </label>
          <label class="field">
            <span>Direction</span>
            <select
              :value="String(selectedLayer.effect.direction)"
              @change="upd('direction', Number(($event.target as HTMLSelectElement).value))"
            >
              <option value="1">Forward</option>
              <option value="-1">Reverse</option>
            </select>
          </label>
          <label class="field">
            <span>Mode</span>
            <select :value="selectedLayer.effect.mode" @change="upd('mode', ($event.target as HTMLSelectElement).value)">
              <option value="loop">Loop</option>
              <option value="bounce">Bounce</option>
            </select>
          </label>
        </div>
        <label class="check">
          <input
            type="checkbox"
            :checked="selectedLayer.effect.fade"
            @change="upd('fade', ($event.target as HTMLInputElement).checked)"
          />
          <span>Fade the tail</span>
        </label>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'scanner'">
        <label class="field">
          <span>Color</span>
          <input type="color" :value="selectedLayer.effect.color" @input="upd('color', ($event.target as HTMLInputElement).value)" />
        </label>
        <div class="grid2">
          <label class="field">
            <span>Width (LEDs)</span>
            <input type="number" min="1" max="512" :value="selectedLayer.effect.width" @input="upd('width', num($event))" />
          </label>
          <label class="field">
            <span>Period (s)</span>
            <input type="number" min="0.1" max="60" step="0.1" :value="selectedLayer.effect.period" @input="upd('period', num($event))" />
          </label>
        </div>
      </template>

      <template v-else-if="selectedLayer.effect.type === 'meter'">
        <label class="field">
          <span>Data source</span>
          <select :value="selectedLayer.effect.source" @change="upd('source', ($event.target as HTMLSelectElement).value)">
            <option v-for="src in DATA_SOURCES" :key="src" :value="src">{{ src }}</option>
          </select>
        </label>
        <div class="grid2">
          <label class="field">
            <span>Low color</span>
            <input type="color" :value="selectedLayer.effect.color_low" @input="upd('color_low', ($event.target as HTMLInputElement).value)" />
          </label>
          <label class="field">
            <span>High color</span>
            <input type="color" :value="selectedLayer.effect.color_high" @input="upd('color_high', ($event.target as HTMLInputElement).value)" />
          </label>
          <label class="field">
            <span>Max value</span>
            <input type="number" min="0.1" :value="selectedLayer.effect.max_value" @input="upd('max_value', num($event))" />
          </label>
          <label class="field">
            <span>Mode</span>
            <select :value="selectedLayer.effect.mode" @change="upd('mode', ($event.target as HTMLSelectElement).value)">
              <option value="bar">Bar</option>
              <option value="fill">Fill</option>
            </select>
          </label>
        </div>
      </template>

      <!-- ================= Mask ================= -->
      <h4>Mask</h4>
      <label class="check">
        <input
          type="checkbox"
          :checked="selectedLayer.mask.all"
          @change="store.actions.maskSetAll(selectedLayer.id, ($event.target as HTMLInputElement).checked)"
        />
        <span>All pixels</span>
      </label>
      <template v-if="!selectedLayer.mask.all">
        <div class="inline wrap">
          <button class="small" @click="store.actions.maskFillAll(selectedLayer.id)">All</button>
          <button class="small" @click="store.actions.maskClear(selectedLayer.id)">None</button>
          <button class="small" @click="store.actions.maskInvert(selectedLayer.id)">Invert</button>
          <button class="small" :class="{ on: editingMask }" @click="togglePaint">
            {{ editingMask ? '✓ Painting' : 'Paint on canvas' }}
          </button>
        </div>
        <div v-for="entry in maskSummary()" :key="entry.name" class="hint">
          <span class="mono">{{ entry.name }}:</span> {{ entry.text }}
        </div>
        <p v-if="maskSummary().length === 0" class="hint">No pixels selected — layer is invisible.</p>
      </template>
    </template>

    <!-- ================= Header ================= -->
    <template v-else-if="selectedHeader !== null">
      <div class="head">
        <h3>Channel</h3>
        <button
          class="danger small"
          :disabled="selectedHeader.devices.length > 0"
          :title="selectedHeader.devices.length > 0 ? 'Remove its devices first' : 'Delete header'"
          @click="store.actions.deleteHeader(selectedHeader.id)"
        >
          Delete
        </button>
      </div>
      <label class="field">
        <span>Name</span>
        <input
          :value="selectedHeader.name"
          maxlength="100"
          @input="store.actions.updateHeader(selectedHeader.id, { name: ($event.target as HTMLInputElement).value })"
        />
      </label>
      <label v-if="state.status.zones.length > 0" class="field">
        <span>OpenRGB zone</span>
        <select :value="selectedHeader.zone_index" @change="onZoneChange">
          <option v-for="zone in state.status.zones" :key="zone.index" :value="zone.index">
            {{ zone.name }} ({{ zone.leds }} LEDs)
          </option>
        </select>
      </label>
      <label v-else class="field">
        <span>Zone index</span>
        <input
          type="number" min="0" :value="selectedHeader.zone_index"
          @input="store.actions.updateHeader(selectedHeader.id, { zone_index: num($event) })"
        />
      </label>
      <label class="field">
        <span>LEDs (capacity)</span>
        <input
          type="number" min="1" max="1024"
          :value="selectedHeader.size ?? ''"
          placeholder="auto"
          title="Channel capacity in LEDs; empty = follow the chain length"
          @input="onSizeInput"
        />
      </label>
      <div class="field">
        <span>Chain</span>
        <p class="hint">
          {{ store.headerUsage(selectedHeader).used
          }}<template v-if="selectedHeader.size !== null"> / {{ selectedHeader.size }} LEDs</template>
        </p>
        <p v-if="selectedHeader.devices.length === 0" class="hint">No devices on this channel.</p>
        <div v-for="(deviceId, i) in selectedHeader.devices" :key="deviceId" class="inline">
          <span class="mono">{{ i + 1 }}</span>
          <button
            class="small chain-chip"
            :title="deviceLabel(deviceId)"
            @click="store.actions.select('device', deviceId)"
          >
            {{ deviceLabel(deviceId) }}
          </button>
          <button
            class="small"
            :disabled="i === 0"
            title="Earlier in chain"
            @click="store.actions.reorderDevice(deviceId, -1)"
          >
            ▲
          </button>
          <button
            class="small"
            :disabled="i === selectedHeader.devices.length - 1"
            title="Later in chain"
            @click="store.actions.reorderDevice(deviceId, 1)"
          >
            ▼
          </button>
        </div>
      </div>
    </template>

    <!-- ================= Nothing selected ================= -->
    <template v-else>
      <h3>Layout</h3>
      <div class="grid2">
        <label class="field">
          <span>FPS</span>
          <input type="number" min="1" max="60" :value="state.layout.fps" @input="setLayoutFps" />
        </label>
        <label class="field">
          <span>Brightness %</span>
          <input type="number" min="0" max="200" :value="state.layout.brightness" @input="setLayoutBrightness" />
        </label>
      </div>

      <p class="hint">
        Click a device on the canvas to edit it, a layer in the Effects
        stack for its effect, a channel in the Channels stack below for
        its wiring.
      </p>
    </template>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h3 {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}

h4 {
  margin: 8px 0 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.inline {
  display: flex;
  align-items: center;
  gap: 6px;
}

.inline.wrap {
  flex-wrap: wrap;
}

.inline input[type='number'] {
  width: 64px;
}

.inline input[type='color'] {
  width: 42px;
  padding: 1px;
}

.chain-chip {
  flex: 1;
  min-width: 0;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  cursor: pointer;
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}

.hint.warn {
  color: var(--warning);
}

.mono {
  font-variant-numeric: tabular-nums;
}

button.small {
  font-size: 12px;
  padding: 3px 8px;
}

button.on {
  border-color: var(--accent-dim);
  color: var(--accent);
}

input[type='color'] {
  height: 26px;
}
</style>
