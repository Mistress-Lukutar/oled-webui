<script setup lang="ts">
import { ref } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const { state, actions } = useDisplayStore()

const presetName = ref('')
const saving = ref(false)
const applyingId = ref<string | null>(null)

async function saveCurrent(): Promise<void> {
  const name = presetName.value.trim()
  if (name === '') return
  saving.value = true
  const ok = await actions.saveCurrent(name)
  if (ok) presetName.value = ''
  saving.value = false
}

async function apply(id: string): Promise<void> {
  applyingId.value = id
  await actions.applyPreset(id)
  applyingId.value = null
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}
</script>

<template>
  <section class="card presets">
    <h2>Presets</h2>

    <div class="save-row">
      <input
        v-model="presetName"
        type="text"
        placeholder="Save current content as…"
        maxlength="100"
        @keyup.enter="saveCurrent"
      />
      <button
        class="primary"
        :disabled="!state.connected || presetName.trim() === '' || saving"
        @click="saveCurrent"
      >
        {{ saving ? 'Saving…' : 'Save current' }}
      </button>
    </div>

    <div v-if="state.presets.length === 0" class="empty">
      No presets yet. Send an image, color or text to the display and save it here.
    </div>

    <ul v-else class="list">
      <li v-for="preset in state.presets" :key="preset.id" class="item">
        <div class="info">
          <span class="name">{{ preset.name }}</span>
          <span class="badge">{{ preset.type }}</span>
          <span class="time">{{ formatTime(preset.created_at) }}</span>
        </div>
        <div class="actions">
          <button
            class="primary"
            :disabled="!state.connected || applyingId === preset.id"
            @click="apply(preset.id)"
          >
            {{ applyingId === preset.id ? '…' : 'Apply' }}
          </button>
          <button class="danger" @click="actions.deletePreset(preset.id)">
            Delete
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.presets {
  margin-bottom: 32px;
}

.save-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.save-row input {
  flex: 1;
}

.empty {
  color: var(--text-dim);
  font-size: 13px;
  padding: 8px 0;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.info {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  font-size: 11px;
  color: var(--text-dim);
}

.actions {
  display: flex;
  gap: 6px;
  flex: none;
}
</style>
