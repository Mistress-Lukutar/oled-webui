<script lang="ts">
/**
 * Generic masonry layout. Column count derives from the container width
 * and a desired minimum column width; items flow in order into the
 * shortest column — the same scheme as Synth-Gallery's gallery-masonry.
 * Item heights are measured from the rendered DOM (ResizeObserver) and
 * only fall back to the aspect-ratio estimate before the first measure.
 */

/** Scoped-slot props passed for every rendered item. */
export interface MasonrySlotProps<T> {
  item: T
  /** Rendered column width in px. */
  columnWidth: number
  /** Height this item currently occupies: measured, or the aspect
   * estimate before the first measurement. */
  height: number
}

/** Aspect clamp keeps extreme ratios from breaking height estimates. */
export const ASPECT_MIN = 0.4
export const ASPECT_MAX = 4.0
</script>

<script setup lang="ts" generic="T">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    /** Items in reading order; each goes into the currently shortest column. */
    items: readonly T[]
    /** Width-over-height ratio used to estimate item height until measured. */
    aspectOf: (item: T) => number
    /** Stable key per item; defaults to the item's `key` property. */
    keyOf?: (item: T) => PropertyKey
    /** Desired minimum column width in px. */
    minColumnWidth?: number
    /** Gap between columns and between stacked items, px. */
    gap?: number
    minColumns?: number
    maxColumns?: number
  }>(),
  {
    keyOf: (item: T) => (item as { key: PropertyKey }).key,
    minColumnWidth: 280,
    gap: 16,
    minColumns: 1,
    maxColumns: 8,
  },
)

const container = ref<HTMLElement | null>(null)
const width = ref(0)
let observer: ResizeObserver | null = null

// clientWidth is read directly: ResizeObserver callbacks are not delivered
// while the tab renders in the background (embedded viewers), and the
// initial measurement must not depend on that.
function measure(): void {
  const measured = container.value?.clientWidth ?? 0
  if (measured > 0) width.value = measured
}

onMounted(() => {
  measure()
  observer = new ResizeObserver(measure)
  if (container.value !== null) observer.observe(container.value)
})
onBeforeUnmount(() => observer?.disconnect())

const columnCount = computed(() => {
  if (width.value <= 0) return props.minColumns
  const fit = Math.floor(width.value / props.minColumnWidth)
  return Math.min(props.maxColumns, Math.max(props.minColumns, fit))
})

const columnWidth = computed(() => {
  if (columnCount.value <= 1) return width.value
  return (width.value - props.gap * (columnCount.value - 1)) / columnCount.value
})

// Measured rendered height per item key; drives the column balancing.
const measuredHeights = reactive(new Map<PropertyKey, number>())
const itemEls = new Map<PropertyKey, HTMLElement>()
const elKeys = new Map<HTMLElement, PropertyKey>()

const itemObserver = new ResizeObserver((entries) => {
  for (const entry of entries) {
    const key = elKeys.get(entry.target as HTMLElement)
    if (key !== undefined) measuredHeights.set(key, (entry.target as HTMLElement).offsetHeight)
  }
})

/** Template ref callback: tracks one item wrapper for height measuring. */
function bindItem(key: PropertyKey): (el: unknown) => void {
  return (el) => {
    if (el === null) {
      const prev = itemEls.get(key)
      if (prev !== undefined) {
        itemObserver.unobserve(prev)
        itemEls.delete(key)
        elKeys.delete(prev)
        measuredHeights.delete(key)
      }
      return
    }
    const node = el as HTMLElement
    itemEls.set(key, node)
    elKeys.set(node, key)
    itemObserver.observe(node)
  }
}

onBeforeUnmount(() => itemObserver.disconnect())

const columns = computed<{ item: T; height: number }[][]>(() => {
  const count = columnCount.value
  const result = Array.from({ length: count }, () => [] as { item: T; height: number }[])
  const heights = new Array<number>(count).fill(0)
  for (const item of props.items) {
    const key = props.keyOf(item)
    const aspect = Math.min(ASPECT_MAX, Math.max(ASPECT_MIN, props.aspectOf(item)))
    const estimate = columnWidth.value / aspect
    const height = measuredHeights.get(key) ?? estimate
    let shortest = 0
    for (let i = 1; i < count; i += 1) {
      if (heights[i] < heights[shortest]) shortest = i
    }
    result[shortest].push({ item, height })
    heights[shortest] += height + props.gap
  }
  return result
})
</script>

<template>
  <div ref="container" class="masonry" :style="{ gap: `${gap}px` }">
    <template v-if="width > 0">
      <div
        v-for="(column, index) in columns"
        :key="index"
        class="masonry-column"
        :style="{ gap: `${gap}px` }"
      >
        <div
          v-for="placed in column"
          :key="keyOf(placed.item)"
          :ref="bindItem(keyOf(placed.item))"
          class="masonry-item"
        >
          <slot :item="placed.item" :column-width="columnWidth" :height="placed.height" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.masonry {
  display: flex;
  align-items: flex-start;
  width: 100%;
}

.masonry-column {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.masonry-item {
  min-width: 0;
}
</style>
