<script setup lang="ts">
import { onMounted, ref } from 'vue'
import StatusBar from './components/StatusBar.vue'
import PreviewPane from './components/PreviewPane.vue'
import ImagePanel from './components/ImagePanel.vue'
import ColorPanel from './components/ColorPanel.vue'
import TextPanel from './components/TextPanel.vue'
import VideoPanel from './components/VideoPanel.vue'
import ScenePanel from './components/ScenePanel.vue'
import PresetsPanel from './components/PresetsPanel.vue'
import ArgbPanel from './components/argb/ArgbPanel.vue'
import { useDisplayStore } from './composables/useDisplayStore'

const { state } = useDisplayStore()

type DeviceTab = 'oled' | 'argb'
const deviceTab = ref<DeviceTab>('oled')

type Tab = 'image' | 'color' | 'text' | 'video' | 'scene'
const activeTab = ref<Tab>('image')
const tabs: { id: Tab; label: string }[] = [
  { id: 'image', label: 'Image' },
  { id: 'color', label: 'Color' },
  { id: 'text', label: 'Text' },
  { id: 'video', label: 'Video' },
  { id: 'scene', label: 'Scene' },
]

onMounted(() => {
  void useDisplayStore().actions.init()
})
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <img src="/favicon.svg" alt="" class="logo" />
      <h1>OledWebUI</h1>
    </div>
    <nav class="device-tabs" aria-label="Devices">
      <span class="group-label">Devices</span>
      <button :class="{ active: deviceTab === 'oled' }" @click="deviceTab = 'oled'">
        OLED
      </button>
      <button :class="{ active: deviceTab === 'argb' }" @click="deviceTab = 'argb'">
        ARGB
      </button>
    </nav>
    <StatusBar />
  </header>

  <template v-if="deviceTab === 'oled'">
    <main class="layout">
      <section class="left">
        <PreviewPane />
      </section>
      <section class="right">
        <nav class="tabs">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </nav>
        <div class="card">
          <ImagePanel v-show="activeTab === 'image'" />
          <ColorPanel v-show="activeTab === 'color'" />
          <TextPanel v-show="activeTab === 'text'" />
          <VideoPanel v-show="activeTab === 'video'" />
          <ScenePanel v-show="activeTab === 'scene'" />
        </div>
      </section>
    </main>

    <PresetsPanel />
  </template>

  <ArgbPanel v-else />

  <div v-if="state.error" class="error-toast">{{ state.error }}</div>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand h1 {
  font-size: 18px;
  margin: 0;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.device-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.group-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  margin-right: 2px;
}

.device-tabs button {
  padding: 5px 18px;
}

.device-tabs button.active {
  background: var(--bg-panel);
  border-color: var(--accent-dim);
  color: var(--accent);
}

.logo {
  width: 26px;
  height: 26px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.tabs button {
  flex: 1;
  background: transparent;
  border-color: var(--border);
}

.tabs button.active {
  background: var(--bg-panel);
  border-color: var(--accent-dim);
  color: var(--accent);
}
</style>
