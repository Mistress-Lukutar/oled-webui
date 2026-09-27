<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'
import FileDropZone from './FileDropZone.vue'

const { state, actions } = useDisplayStore()

const file = ref<File | null>(null)
const fps = ref(30)
const loop = ref(false)
const rotation = ref(0)
const fit = ref<'contain' | 'stretch' | 'width' | 'height'>('contain')
const starting = ref(false)

const playing = computed(() => state.video.playing)

async function start(): Promise<void> {
  if (file.value === null) return
  starting.value = true
  await actions.startVideo(file.value, fps.value, loop.value, {
    rotation: rotation.value,
    fit: fit.value,
  })
  starting.value = false
}
</script>

<template>
  <div>
    <div v-if="playing" class="playing card">
      <div class="row">
        <span class="badge active">{{ state.video.preparing ? 'Preparing…' : 'Playing' }}</span>
        <span class="file">{{ state.video.file }}</span>
      </div>
      <div class="meta">
        {{ state.video.fps }} fps · loop: {{ state.video.loop ? 'on' : 'off' }} ·
        {{ state.video.frames_sent }} frames sent
      </div>
      <button class="danger" @click="actions.stopVideo()">Stop playback</button>
    </div>

    <template v-else>
      <FileDropZone
        v-model="file"
        accept="video/*,.gif"
        :mime-types="['video/', 'image/gif']"
        :extensions="['.mp4', '.avi', '.mkv', '.mov', '.webm', '.gif', '.m4v']"
        icon="video"
        preview="video"
        title="Drop a video here"
        hint="or click to browse · Ctrl+V pastes from clipboard"
        formats="MP4 · AVI · MKV · MOV · WEBM · GIF"
      />

      <div class="row field">
        <div>
          <label>FPS: {{ fps }}</label>
          <input v-model.number="fps" type="range" min="1" max="60" />
        </div>
        <div>
          <label>Fit</label>
          <select v-model="fit">
            <option value="contain">Contain</option>
            <option value="stretch">Stretch</option>
            <option value="width">Fit width</option>
            <option value="height">Fit height</option>
          </select>
        </div>
      </div>

      <div class="row field">
        <div>
          <label>Rotation</label>
          <select v-model.number="rotation">
            <option :value="0">0°</option>
            <option :value="90">90°</option>
            <option :value="180">180°</option>
            <option :value="270">270°</option>
          </select>
        </div>
      </div>

      <label class="loop field">
        <input v-model="loop" type="checkbox" />
        Loop playback
      </label>

      <button
        class="primary send"
        :disabled="!state.connected || file === null || starting"
        @click="start"
      >
        {{ starting ? 'Starting…' : 'Start playback' }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.playing {
  background: var(--bg-input);
}

.playing .file {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta {
  color: var(--text-dim);
  font-size: 12px;
  margin: 10px 0;
}

.loop {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  font-size: 13px;
}

.send {
  width: 100%;
}
</style>
