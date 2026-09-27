<script setup lang="ts">
import { ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'
import DisplaySettingsModal from './DisplaySettingsModal.vue'

const { state, actions } = useDisplayStore()
const showSettings = ref(false)
</script>

<template>
  <div class="status">
    <span class="dot" :class="{ up: state.connected }" />
    <span class="state-text">
      {{ state.connected ? 'Connected' : 'Disconnected' }}
    </span>
    <span v-if="state.device" class="resolution">
      {{ state.device.vid.toString(16).toUpperCase().padStart(4, '0') }}:{{
        state.device.pid.toString(16).toUpperCase().padStart(4, '0')
      }}
      · {{ state.device.resolution.width }}×{{
        state.device.resolution.height
      }}
    </span>

    <button class="settings" title="Display settings" @click="showSettings = true">
      ⚙ Settings
    </button>

    <span class="badge" :class="{ active: state.video.playing }">
      {{ state.video.playing ? `Video: ${state.video.file}` : 'Video idle' }}
    </span>

    <button v-if="!state.connected" class="primary" @click="actions.connect()">
      Connect
    </button>
    <button v-else @click="actions.disconnect()">Disconnect</button>
  </div>

  <DisplaySettingsModal v-if="showSettings" @close="showSettings = false" />
</template>

<style scoped>
.status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--danger);
  flex: none;
}

.dot.up {
  background: var(--accent);
}

.state-text {
  font-size: 13px;
}

.resolution {
  font-size: 12px;
  color: var(--text-dim);
  font-family: Consolas, monospace;
}

.settings {
  font-size: 13px;
}
</style>
