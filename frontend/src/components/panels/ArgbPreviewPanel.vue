<script setup lang="ts">
/**
 * ARGB preview panel: live engine output, no controls.
 */
import { onMounted } from 'vue'
import ArgbPreview from '../argb/ArgbPreview.vue'
import { useArgbStore } from '../../argb/store'

const props = defineProps<{ deviceId?: string | null }>()
void props

const store = useArgbStore()

onMounted(() => {
  void store.actions.init()
  // Always re-mirror the active layout: another panel (or the editor)
  // may have applied a different scene since the last mount.
  void store.actions.refreshActiveLayout()
})
</script>

<template>
  <ArgbPreview />
</template>
