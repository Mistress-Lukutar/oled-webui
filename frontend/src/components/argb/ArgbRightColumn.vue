<script setup lang="ts">
/**
 * ARGB right column: the Layout/Device/Layer inspector on top and the
 * Channels stack (OpenRGB zones) below it. Each pane scrolls
 * independently so the channel list stays visible while properties are
 * edited.
 */
import ArgbHeaders from './ArgbHeaders.vue'
import ArgbInspector from './ArgbInspector.vue'
</script>

<template>
  <div class="argb-right">
    <div class="pane inspector-pane">
      <ArgbInspector />
    </div>
    <div class="pane hardware-pane">
      <ArgbHeaders />
    </div>
  </div>
</template>

<style scoped>
.argb-right {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.pane {
  min-height: 0;
  overflow-y: auto;
}

.inspector-pane {
  flex: 1 1 55%;
}

.hardware-pane {
  flex: 1 1 45%;
  min-height: 160px;
  margin-top: 10px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}
</style>
