<script setup lang="ts">
/**
 * Common dashboard panel shell: masonry tile sized by its content, with
 * header (title/subtitle, remove button) and drag handle. Content comes
 * through the default slot.
 */
const props = defineProps<{
  title: string
  subtitle?: string | null
  draggable?: boolean
}>()

const emit = defineEmits<{
  remove: []
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
    :class="{ draggable }"
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
