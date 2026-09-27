<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, previewUrl, actions } = useDisplayStore()
const busy = ref(false)

const panelRatioStyle = computed(() => `${state.resolution.width} / ${state.resolution.height}`)

// Swap the shown frame only after the next one has fully loaded: directly
// patching src flashes black while the new JPEG is being fetched.
const shownUrl = ref<string | null>(null)
watch(
  previewUrl,
  (url) => {
    if (!url) {
      shownUrl.value = null
      return
    }
    const loader = new Image()
    loader.onload = () => {
      if (previewUrl.value === url) shownUrl.value = url
    }
    loader.src = url
  },
  { immediate: true },
)

async function withBusy(action: () => Promise<boolean>): Promise<void> {
  busy.value = true
  await action()
  busy.value = false
}
</script>

<template>
  <div class="card preview-card">
    <h2>Display preview</h2>
    <div class="frame" :style="{ aspectRatio: panelRatioStyle }">
      <img
        v-if="shownUrl"
        :src="shownUrl"
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
/* The frame height derives only from the card width and the panel aspect
   ratio, so it stays identical no matter which tab is open. */
.preview-card {
  display: flex;
  flex-direction: column;
}

.frame {
  aspect-ratio: 16 / 9;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  overflow: hidden;
  margin-bottom: 12px;
}

.frame img {
  width: 100%;
  height: 100%;
  display: block;
  /* Stored frames carry the 180° base panel rotation; flip back so the
     preview matches what is physically visible on the panel. */
  transform: rotate(180deg);
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
