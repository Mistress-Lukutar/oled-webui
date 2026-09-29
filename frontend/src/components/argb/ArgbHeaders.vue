<script setup lang="ts">
/**
 * Hardware tab (editor side panel): ARGB headers mapped to OpenRGB zones
 * and their device chains, with chain reordering. Previously header
 * management was only reachable via the inspector's "nothing selected"
 * state.
 */
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

function num(event: Event): number {
  return Number((event.target as HTMLInputElement).value) || 0
}

function deviceLabel(id: string): string {
  const device = state.layout.devices.find((item) => item.id === id)
  return device === undefined ? '?' : `${device.name} · ${store.deviceLeds(device)} LEDs`
}

function onZoneChange(event: Event, headerId: string): void {
  const index = num(event)
  const zone = state.status.zones.find((item) => item.index === index)
  const header = state.layout.headers.find((item) => item.id === headerId)
  store.actions.updateHeader(headerId, {
    zone_index: index,
    size: zone !== undefined ? zone.leds : (header?.size ?? null),
  })
}
</script>

<template>
  <div class="headers">
    <div
      v-for="header in state.layout.headers"
      :key="header.id"
      class="header-card"
      :class="{ selected: state.selection.kind === 'header' && state.selection.id === header.id }"
    >
      <div class="head" @click="store.actions.select('header', header.id)">
        <span class="name">{{ header.name }}</span>
        <span class="mono">
          {{ store.headerUsage(header).used }}<template v-if="header.size !== null">/{{ header.size }}</template>
        </span>
      </div>

      <label class="field">
        <span>Zone</span>
        <select
          v-if="state.status.zones.length > 0"
          :value="header.zone_index"
          @change="onZoneChange($event, header.id)"
        >
          <option v-for="zone in state.status.zones" :key="zone.index" :value="zone.index">
            {{ zone.name }} ({{ zone.leds }})
          </option>
        </select>
        <input
          v-else
          type="number"
          min="0"
          :value="header.zone_index"
          @input="store.actions.updateHeader(header.id, { zone_index: num($event) })"
        />
      </label>

      <div class="chain">
        <span class="label">Chain</span>
        <p v-if="header.devices.length === 0" class="hint">No devices on this header.</p>
        <div v-for="(deviceId, i) in header.devices" :key="deviceId" class="chain-row">
          <span class="pos mono">{{ i + 1 }}</span>
          <button
            class="chip"
            :class="{ on: state.deviceSelection.includes(deviceId) }"
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
            :disabled="i === header.devices.length - 1"
            title="Later in chain"
            @click="store.actions.reorderDevice(deviceId, 1)"
          >
            ▼
          </button>
        </div>
      </div>

      <button
        class="small danger"
        :disabled="header.devices.length > 0"
        :title="header.devices.length > 0 ? 'Remove its devices first' : 'Delete header'"
        @click="store.actions.deleteHeader(header.id)"
      >
        Delete
      </button>
    </div>

    <button class="small" @click="store.actions.addHeader()">+ Add header</button>
    <p class="hint">
      Chain order is the physical wiring order on the header — LED #0 of the
      first device is the first pixel the controller receives.
    </p>
  </div>
</template>

<style scoped>
.headers {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  min-height: 0;
}

.header-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.header-card.selected {
  border-color: var(--accent-dim);
}

.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
}

.head .name {
  font-size: 13px;
  font-weight: 600;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: var(--text-dim);
}

.label {
  font-size: 12px;
  color: var(--text-dim);
}

.chain {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chain-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pos {
  width: 14px;
  text-align: right;
  font-size: 11px;
  color: var(--text-dim);
}

.chip {
  flex: 1;
  min-width: 0;
  text-align: left;
  font-size: 12px;
  padding: 3px 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip.on {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}
</style>
