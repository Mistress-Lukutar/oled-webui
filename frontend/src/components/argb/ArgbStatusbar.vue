<script setup lang="ts">
/**
 * ARGB section statusbar: OpenRGB connection state, engine activity and
 * the selected device's chain usage. Shown in the unified scene editor
 * while the ARGB section tab is active.
 */
import { computed } from 'vue'
import { useArgbStore } from '../../argb/store'

const store = useArgbStore()
const { state } = store

const statusText = computed(() =>
  state.status.connected
    ? `${state.status.controller ?? 'OpenRGB'} · ${state.status.zones.length} zones`
    : 'OpenRGB not connected',
)

const chainInfo = computed(() => {
  const { kind, id } = state.selection
  let header = null
  if (kind === 'device' && id !== null) {
    const device = state.layout.devices.find((item) => item.id === id)
    header =
      device !== undefined
        ? (state.layout.headers.find((item) => item.id === device.header_id) ?? null)
        : null
  } else if (kind === 'header' && id !== null) {
    header = state.layout.headers.find((item) => item.id === id) ?? null
  }
  return header !== null ? store.headerUsage(header) : null
})
</script>

<template>
  <span
    class="dot"
    :class="{ on: state.status.connected, run: state.status.running }"
    :title="state.status.connected ? 'OpenRGB connected' : 'OpenRGB not connected'"
  />
  <span>{{ statusText }}</span>
  <span v-if="state.status.running">
    running @ {{ state.status.fps }} fps · {{ state.status.frames_sent }} frames sent
  </span>
  <button v-if="!state.status.connected" class="small" @click="store.actions.connect()">
    Connect
  </button>
  <button v-else class="small" @click="store.actions.disconnect()">Disconnect</button>
  <span v-if="chainInfo !== null" class="mono">
    Chain {{ chainInfo.used }}<template v-if="chainInfo.capacity !== null">/{{ chainInfo.capacity }}</template> LEDs
  </span>
  <span class="dim">Drag to move · Wheel to zoom · Del to delete</span>
</template>

<style scoped>
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--danger);
  flex: none;
}

.dot.on {
  background: var(--accent);
}

.dot.run {
  box-shadow: 0 0 6px var(--accent);
}

.statusbar-extras .small {
  font-size: 11px;
  padding: 2px 8px;
}

.mono {
  font-variant-numeric: tabular-nums;
}

.dim {
  opacity: 0.75;
}
</style>
