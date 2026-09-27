<script setup lang="ts">
/**
 * Reusable drop zone for picking a single file by drag & drop,
 * clipboard paste (Ctrl+V) or the native file browser.
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useDisplayStore } from '../composables/useDisplayStore'

const props = withDefaults(
  defineProps<{
    modelValue: File | null
    /** `accept` filter passed to the hidden file input. */
    accept: string
    /** Allowed MIME type prefixes, e.g. ['image/'] or ['video/', 'image/gif']. */
    mimeTypes: string[]
    /** Fallback extension check for files with an empty MIME type. */
    extensions?: string[]
    icon?: 'image' | 'video'
    title?: string
    hint?: string
    formats?: string
    /** Element used for the local thumbnail of the selected file. */
    preview?: 'image' | 'video'
  }>(),
  {
    extensions: () => [],
    icon: 'image',
    title: 'Drop a file here',
    hint: 'or click to browse · Ctrl+V pastes from clipboard',
    formats: '',
    preview: 'image',
  },
)

const emit = defineEmits<{ 'update:modelValue': [File | null] }>()

const { showError } = useDisplayStore()

const dragging = ref(false)
const previewUrl = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
let dragDepth = 0

watch(
  () => props.modelValue,
  (next) => {
    if (previewUrl.value !== null) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = next ? URL.createObjectURL(next) : null
  },
  { immediate: true },
)

onUnmounted(() => {
  if (previewUrl.value !== null) URL.revokeObjectURL(previewUrl.value)
})

function matches(next: File): boolean {
  if (props.mimeTypes.some((prefix) => next.type.startsWith(prefix))) return true
  const name = next.name.toLowerCase()
  return props.extensions.some((ext) => name.endsWith(ext))
}

function setFile(next: File | null): void {
  if (next !== null && !matches(next)) {
    showError(`Unsupported file: ${next.name || 'clipboard content'}`)
    return
  }
  emit('update:modelValue', next)
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  setFile(input.files?.[0] ?? null)
  // Reset so picking the same file again re-triggers change.
  input.value = ''
}

function browse(): void {
  fileInput.value?.click()
}

function clearFile(): void {
  setFile(null)
}

function onDragEnter(event: DragEvent): void {
  event.preventDefault()
  dragDepth += 1
  dragging.value = true
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
}

function onDragLeave(event: DragEvent): void {
  event.preventDefault()
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragging.value = false
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  dragDepth = 0
  dragging.value = false
  setFile(event.dataTransfer?.files[0] ?? null)
}

function onPaste(event: ClipboardEvent): void {
  const pasted = event.clipboardData?.files[0]
  if (pasted !== undefined) setFile(pasted)
}

onMounted(() => window.addEventListener('paste', onPaste))
onUnmounted(() => window.removeEventListener('paste', onPaste))

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
</script>

<template>
  <div>
    <input
      ref="fileInput"
      type="file"
      :accept="accept"
      class="hidden-input"
      @change="onFileChange"
    />

    <div
      class="dropzone"
      :class="{ dragging, 'has-file': previewUrl !== null }"
      role="button"
      tabindex="0"
      @click="browse"
      @keydown.enter="browse"
      @keydown.space.prevent="browse"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <template v-if="previewUrl">
        <video
          v-if="preview === 'video'"
          :src="previewUrl"
          class="thumb"
          muted
        ></video>
        <img v-else :src="previewUrl" alt="Selected file" class="thumb" />
        <div class="file-meta">
          <span class="file-name" :title="modelValue?.name">
            {{ modelValue?.name }}
          </span>
          <span class="file-size">
            {{ modelValue ? formatSize(modelValue.size) : '' }}
          </span>
          <button class="clear" title="Remove" @click.stop="clearFile">×</button>
        </div>
      </template>
      <template v-else>
        <svg
          v-if="icon === 'video'"
          class="zone-icon"
          :class="{ active: dragging }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M10 9.5l5 2.5-5 2.5z" />
        </svg>
        <svg
          v-else
          class="zone-icon"
          :class="{ active: dragging }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
        <span class="zone-title">{{ dragging ? 'Drop to load' : title }}</span>
        <span class="zone-hint">{{ hint }}</span>
        <span v-if="formats" class="zone-formats">{{ formats }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.hidden-input {
  display: none;
}

.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 170px;
  padding: 18px;
  margin-bottom: 14px;
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  background: var(--bg-input);
  text-align: center;
  cursor: pointer;
  user-select: none;
  transition: border-color 0.15s, background 0.15s;
  overflow: hidden;
}

.dropzone:hover,
.dropzone:focus-visible {
  border-color: var(--accent-dim);
  outline: none;
}

.dropzone.dragging {
  border-color: var(--accent);
  border-style: solid;
  background: rgba(53, 201, 142, 0.07);
}

.dropzone.has-file {
  border-style: solid;
  align-items: stretch;
  min-height: 0;
  padding: 10px;
}

.dropzone.has-file:hover {
  border-color: var(--border);
}

.thumb {
  width: 100%;
  max-height: 160px;
  object-fit: contain;
  border-radius: 4px;
  background: #000;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px 0;
}

.file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text);
  text-align: left;
}

.file-size {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-dim);
}

.clear {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  padding: 0;
  line-height: 1;
  font-size: 14px;
  border-radius: 50%;
  color: var(--text-dim);
}

.clear:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}

.zone-icon {
  width: 36px;
  height: 36px;
  color: var(--text-dim);
  transition: color 0.15s;
}

.zone-icon.active {
  color: var(--accent);
}

.zone-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.zone-hint {
  font-size: 12px;
  color: var(--text-dim);
}

.zone-formats {
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--text-dim);
  opacity: 0.7;
}
</style>
