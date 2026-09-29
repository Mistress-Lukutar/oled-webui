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
})
</script>

<template>
  <ArgbPreview />
</template>
