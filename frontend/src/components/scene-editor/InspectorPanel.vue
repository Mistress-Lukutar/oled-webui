<script setup lang="ts">
/**
 * Inspector panel: per-widget properties (added in later stages) plus
 * scene asset management, which lives here from the start.
 */
import { ref } from 'vue'
import { editor } from '../../scene-editor/docStore'

const { state } = editor
const assetInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

async function addAssets(files: FileList | null): Promise<void> {
  if (files === null || files.length === 0) return
  uploading.value = true
  try {
    await editor.uploadAssets([...files])
  } finally {
    uploading.value = false
    if (assetInput.value !== null) assetInput.value.value = ''
  }
}

async function remove(name: string): Promise<void> {
  await editor.removeAsset(name)
}
</script>

<template>
  <div class="inspector">
    <div class="panel-title">Inspector</div>
    <div class="hint">
      Select a widget on the canvas or in Layers to edit its properties.
    </div>

    <div class="section">
      <div class="section-title">Assets</div>
      <div class="asset-list">
        <span v-for="asset in state.assets" :key="asset" class="badge asset">
          {{ asset }}
          <button class="asset-remove" title="Remove asset" @click="remove(asset)">
            ×
          </button>
        </span>
        <span v-if="state.assets.length === 0" class="none">No assets uploaded</span>
      </div>
      <input
        ref="assetInput"
        type="file"
        multiple
        accept="image/*,.ttf,.otf,.woff,.woff2"
        class="visually-hidden"
        @change="addAssets(($event.target as HTMLInputElement).files)"
      />
      <button :disabled="uploading" @click="assetInput?.click()">
        {{ uploading ? 'Uploading…' : 'Upload images / fonts' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding-bottom: 10px;
}

.panel-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 10px 12px 6px;
  flex: none;
}

.hint {
  color: var(--text-dim);
  font-size: 12px;
  padding: 0 12px 8px;
}

.section {
  padding: 8px 12px 0;
  border-top: 1px solid var(--border);
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.asset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.asset {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.asset-remove {
  background: none;
  border: none;
  color: var(--text-dim);
  padding: 0 2px;
  font-size: 14px;
  line-height: 1;
}

.asset-remove:hover {
  color: var(--danger);
}

.none {
  color: var(--text-dim);
  font-size: 12px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
