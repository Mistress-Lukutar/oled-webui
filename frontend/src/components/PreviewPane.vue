<script setup lang="ts">
import { ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, previewUrl, actions } = useDisplayStore()
const busy = ref(false)

async function withBusy(action: () => Promise<boolean>): Promise<void> {
  busy.value = true
  await action()
  busy.value = false
}
</script>

<template>
  <div class="card preview-card">
    <h2>Display preview</h2>
    <div class="frame">
      <img
        v-if="previewUrl"
        :key="previewUrl"
        :src="previewUrl"
        alt="Current display content"
      />
      <div v-else class="placeholder">
        <span>No frame yet</span>
      </div>
    </div>
    <div class="controls">
      <button :disabled="busy || !state.connected" @click="withBusy(actions.powerOff)">
        Off
      </button>
      <button :disabled="busy || !state.connected" @click="withBusy(actions.powerOn)">
        On
      </button>
      <button
        class="primary"
        :disabled="busy || !state.connected"
        @click="withBusy(() => actions.runTest(1.0))"
      >
        Test pattern
      </button>
    </div>
  </div>
</template>

<style scoped>
.preview-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.frame {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  min-height: 220px;
  overflow: hidden;
  margin-bottom: 12px;
}

.frame img {
  max-width: 100%;
  max-height: 55vh;
  display: block;
}

.placeholder {
  color: #555;
  font-size: 14px;
}

.controls {
  display: flex;
  gap: 8px;
}

.controls button {
  flex: 1;
}
</style>
