<script setup lang="ts">
/**
 * Common dashboard panel shell: header with title/subtitle, span cycler,
 * remove button, drag handle. Content comes through the default slot.
 */
const props = defineProps<{
  title: string
  subtitle?: string | null
  span: number
  draggable?: boolean
}>()

const emit = defineEmits<{
  remove: []
  cycleSpan: []
  dragStart: []
  dragEnter: []
  dropOn: []
  dragEnd: []
}>()

void props
</script>

<template>
  <section
    class="card panel"
    :class="[`span-${Math.min(3, Math.max(1, span))}`, { draggable }]"
    :draggable="draggable ?? false"
    @dragstart="emit('dragStart')"
    @dragenter.prevent="emit('dragEnter')"
    @dragover.prevent
    @drop.prevent="emit('dropOn')"
    @dragend="emit('dragEnd')"
  >
    <header class="head">
      <span class="grip" title="Drag to rearrange">⠿</span>
      <div class="titles">
        <h2>{{ title }}</h2>
        <span v-if="subtitle" class="subtitle">{{ subtitle }}</span>
      </div>
      <button class="icon" title="Resize panel" @click="emit('cycleSpan')">⤢</button>
      <button class="icon" title="Remove panel" @click="emit('remove')">×</button>
    </header>
    <div class="body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
  min-width: 0;
}

.panel.draggable {
  cursor: grab;
}

.panel.draggable:active {
  cursor: grabbing;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.grip {
  color: var(--text-dim);
  font-size: 13px;
  cursor: grab;
}

.titles {
  flex: 1;
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.titles h2 {
  margin: 0;
}

.subtitle {
  font-size: 12px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

button.icon {
  padding: 2px 8px;
  font-size: 13px;
  line-height: 1.3;
  flex: none;
}

.body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
</style>

<style>
/* Span classes are shared with the dashboard grid, so they live globally. */
.span-1 {
  grid-column: span 1;
}

.span-2 {
  grid-column: span 2;
}

.span-3 {
  grid-column: 1 / -1;
}

@media (max-width: 1100px) {
  .span-1,
  .span-2,
  .span-3 {
    grid-column: 1 / -1;
  }
}
</style>
