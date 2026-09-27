/**
 * Reactive state store for the scene editor modal. The parsed YAML
 * document (a plain object) is the editing truth; YAML text is derived
 * after graphical mutations and parsed back after text edits.
 */

import { reactive, readonly } from 'vue'
import { API } from '../api'
import type { SceneDetail } from '../api'
import { parseSceneYaml, stringifySceneYaml, validateSceneDoc } from './yamlSync'
import type { EntryRaw, SceneDocumentRaw } from './types'

export type ViewMode = 'design' | 'yaml' | 'split'

interface EditorState {
  sceneId: string
  name: string
  yamlText: string
  doc: SceneDocumentRaw | null
  /** Semantic validation problems (schema ranges, unknown keys). */
  errors: string[]
  /** Syntax error from the last text edit; doc is stale while set. */
  syntaxError: string | null
  assets: string[]
  components: Record<string, string>
  /** Indices into doc.widgets of the selected entries. */
  selection: number[]
  dirty: boolean
  viewMode: ViewMode
  /** Timeline state shared by the canvas and the timeline panel. */
  time: number
  playing: boolean
  loopDuration: number
}

const state = reactive<EditorState>({
  sceneId: '',
  name: '',
  yamlText: '',
  doc: null,
  errors: [],
  syntaxError: null,
  assets: [],
  components: {},
  selection: [],
  dirty: false,
  viewMode: 'design',
  time: 0,
  playing: false,
  loopDuration: 10,
})

function applyText(text: string, markDirty: boolean): void {
  const result = parseSceneYaml(text)
  state.yamlText = text
  state.doc = result.doc
  // A syntax error is already surfaced via syntaxError; avoid duplicating it.
  state.errors = result.doc === null ? [] : result.errors
  state.syntaxError = result.doc === null ? (result.errors[0] ?? 'YAML error') : null
  state.selection = state.selection.filter((i) => i < (result.doc?.widgets?.length ?? 0))
  if (markDirty) state.dirty = true
}

function setYamlText(text: string): void {
  applyText(text, true)
}

/** Widgets of the current document in z-order (first = bottom layer). */
function getWidgets(): readonly EntryRaw[] {
  return (state.doc?.widgets ?? []) as readonly EntryRaw[]
}

/**
 * Apply a mutation to the raw document and regenerate the YAML text.
 * All graphical edits must go through this to keep both views in sync.
 */
function mutate(fn: (doc: SceneDocumentRaw) => void): void {
  if (state.doc === null || state.syntaxError !== null) return
  fn(state.doc)
  state.yamlText = stringifySceneYaml(state.doc)
  state.errors = validateSceneDoc(state.doc)
  state.selection = state.selection.filter((i) => i < (state.doc?.widgets?.length ?? 0))
  state.dirty = true
}

function setSelection(indices: number[]): void {
  state.selection = indices
}

function setViewMode(mode: ViewMode): void {
  state.viewMode = mode
}

function setName(name: string): void {
  state.name = name
  state.dirty = true
}

function setTime(time: number): void {
  state.time = Math.max(0, Math.min(state.loopDuration, time))
}

function setPlaying(playing: boolean): void {
  state.playing = playing
}

function setLoopDuration(seconds: number): void {
  state.loopDuration = Math.max(0.5, seconds)
  state.time = Math.min(state.time, state.loopDuration)
}

async function load(sceneId: string): Promise<void> {
  const detail: SceneDetail = await API.getScene(sceneId)
  state.sceneId = sceneId
  state.name = detail.scene.name
  state.assets = [...detail.assets]
  state.components = { ...detail.components }
  state.selection = []
  state.dirty = false
  state.time = 0
  state.playing = false
  state.viewMode = 'design'
  applyText(detail.yaml, false)
}

async function save(): Promise<void> {
  if (state.syntaxError !== null) {
    throw new Error(`Fix the YAML syntax error first: ${state.syntaxError}`)
  }
  const saved = await API.saveScene(
    state.sceneId,
    state.yamlText,
    state.name.trim() || undefined,
  )
  state.dirty = false
  if (state.name.trim() === '') state.name = saved.scene.name
}

async function uploadAssets(files: File[]): Promise<void> {
  const stored = await API.uploadSceneAssets(state.sceneId, files)
  state.assets = stored.assets
}

async function removeAsset(name: string): Promise<void> {
  const result = await API.deleteSceneAsset(state.sceneId, name)
  state.assets = result.assets
}

export const editor = {
  state: readonly(state),
  load,
  save,
  setYamlText,
  mutate,
  getWidgets,
  setSelection,
  setViewMode,
  setName,
  setTime,
  setPlaying,
  setLoopDuration,
  uploadAssets,
  removeAsset,
}

export type EditorStore = typeof editor
