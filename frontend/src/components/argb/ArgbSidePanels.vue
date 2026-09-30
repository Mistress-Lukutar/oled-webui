<script setup lang="ts">
/**
 * ARGB section side panels for the unified scene editor: the classic
 * Effects/Hardware tab pair (effect layers and headers/chains).
 */
import { ref } from 'vue'
import ArgbHeaders from './ArgbHeaders.vue'
import ArgbLayersPanel from './ArgbLayersPanel.vue'

const sideTab = ref<'effects' | 'hardware'>('effects')
</script>

<template>
  <div class="argb-side">
    <div class="side-tabs">
      <button :class="{ on: sideTab === 'effects' }" @click="sideTab = 'effects'">Effects</button>
      <button :class="{ on: sideTab === 'hardware' }" @click="sideTab = 'hardware'">Hardware</button>
    </div>
    <div class="side-content">
      <ArgbLayersPanel v-show="sideTab === 'effects'" />
      <ArgbHeaders v-show="sideTab === 'hardware'" />
    </div>
  </div>
</template>

<style scoped>
.argb-side {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.side-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex: none;
}

.side-tabs button {
  flex: 1;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-dim);
}

.side-tabs button.on {
  color: var(--accent);
  background: var(--accent-dim);
}

.side-content {
  flex: 1;
  min-height: 0;
  padding: 10px;
  overflow-y: auto;
}
</style>
