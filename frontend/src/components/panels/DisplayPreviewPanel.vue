<script setup lang="ts">
/**
 * Display preview panel: live panel frame, no controls — everything
 * operable lives in the display settings / scenes panels.
 */
import { computed, ref, watch } from 'vue'
import { useDisplayStore } from '../../composables/useDisplayStore'

const props = defineProps<{ deviceId?: string | null }>()
void props

const { state, previewUrl } = useDisplayStore()

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
</script>

<template>
  <div class="frame" :style="{ aspectRatio: panelRatioStyle }">
    <img v-if="shownUrl" :src="shownUrl" alt="Current display content" />
    <div v-else class="placeholder">
      <span>No frame yet</span>
    </div>
  </div>
</template>

<style scoped>
/* The frame height derives only from the card width and the panel aspect
   ratio, so it stays identical no matter which tab is open. */
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
</style>
