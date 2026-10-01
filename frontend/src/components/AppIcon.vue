<script setup lang="ts">
/**
 * Shared inline-SVG icon. Glyphs come from the central registry in
 * icons.ts; sizing and stroke attributes are fixed here so every icon
 * in the app inherits `currentColor` and aligns with the text baseline.
 */
import { computed } from 'vue'
import { ICONS, type IconName } from './icons'

const props = withDefaults(
  defineProps<{
    name: IconName
    /** Rendered square size in px. */
    size?: number
  }>(),
  { size: 14 },
)

const body = computed(() => ICONS[props.name])
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="body"
  />
</template>
