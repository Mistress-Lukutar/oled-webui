<script setup lang="ts">
/**
 * Font family picker shared by the single- and multi-edit inspectors:
 * built-in default, the shared font library, scene font assets and a
 * custom path option, plus a hidden uploader that adds files to the
 * font library. Supports the multi-selection "mixed" state.
 */
import { computed, ref } from 'vue'
import { API } from '../../api'
import { errMsg } from '../../composables/useErrorToast'
import { useDisplayStore } from '../../composables/useDisplayStore'
import { editor } from '../../scene-editor/docStore'
import { FONT_PATTERN } from '../../scene-editor/types'

const props = withDefaults(
  defineProps<{
    /** Current font-family value ('' = built-in default). */
    family?: string
    /** Multi-selection: the selection holds differing values. */
    mixed?: boolean
  }>(),
  { family: '', mixed: false },
)

/** Emitted as (key, value) pairs, matching PaintStyleSection; `undefined`
 *  drops the family key (back to the built-in font). */
const emit = defineEmits<{ set: [key: string, value: string | undefined] }>()

const { state: appState, actions: appActions, showError } = useDisplayStore()
const { state } = editor

const fontInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

const fontAssets = computed(() => state.assets.filter((asset) => FONT_PATTERN.test(asset)))

const familyValue = computed(() => String(props.family))

const isCustomFamily = computed(() => {
  const value = familyValue.value
  if (value === '' || props.mixed) return false
  return (
    !appState.fonts.some((font) => `fonts/${font}` === value) &&
    !fontAssets.value.some((asset) => `assets/${asset}` === value)
  )
})

async function addLibraryFonts(files: FileList | null): Promise<void> {
  if (files === null || files.length === 0) return
  uploading.value = true
  try {
    await API.uploadFonts([...files])
    await appActions.loadFonts()
  } catch (err) {
    showError(errMsg(err))
  } finally {
    uploading.value = false
    if (fontInput.value !== null) fontInput.value.value = ''
  }
}
</script>

<template>
  <div class="field">
    <label>font</label>
    <select
      :class="{ mixed }"
      :value="mixed ? '__mixed__' : familyValue"
      @change="emit('set', 'family', ($event.target as HTMLSelectElement).value || undefined)"
    >
      <option v-if="mixed" value="__mixed__" disabled>— mixed —</option>
      <option value="">Default (built-in)</option>
      <option v-if="isCustomFamily" :value="familyValue">{{ familyValue }} (custom path)</option>
      <optgroup v-if="appState.fonts.length > 0" label="Font library">
        <option v-for="font in appState.fonts" :key="`lib-${font}`" :value="`fonts/${font}`">
          {{ font }}
        </option>
      </optgroup>
      <optgroup v-if="fontAssets.length > 0" label="Scene assets">
        <option v-for="asset in fontAssets" :key="`scene-${asset}`" :value="`assets/${asset}`">
          {{ asset }}
        </option>
      </optgroup>
    </select>
  </div>
  <input
    ref="fontInput"
    type="file"
    multiple
    accept=".ttf,.otf"
    class="visually-hidden"
    @change="addLibraryFonts(($event.target as HTMLInputElement).files)"
  />
  <div class="field">
    <button class="mini-btn" :disabled="uploading" @click="fontInput?.click()">
      {{ uploading ? 'Uploading…' : 'Upload font…' }}
    </button>
  </div>
</template>
