/**
 * Reactive state store for the scene editor modal. The parsed YAML
 * document (a plain object) is the editing truth; YAML text is derived
 * after graphical mutations and parsed back after text edits.
 */

import { reactive, readonly, ref } from 'vue'
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
  /** Canvas size override (panel profiles) for editing without hardware. */
  resolutionOverride: { width: number; height: number } | null
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
  resolutionOverride: null,
  time: 0,
  playing: false,
  loopDuration: 10,
})

// ----------------------------------------------------------------------
// Undo/redo: JSON snapshots of the whole document. Batches (drags) push
// exactly one snapshot via beginBatch()/endBatch().
// ----------------------------------------------------------------------

const MAX_HISTORY = 100
let undoStack: string[] = []
let redoStack: string[] = []
let batchDepth = 0
/** Bump whenever history contents change, for reactive canUndo/canRedo. */
const historyVersion = ref(0)

function snapshot(): string {
  return JSON.stringify(state.doc)
}

function restore(snapshotText: string): void {
  if (state.doc === null) return
  const doc = JSON.parse(snapshotText) as SceneDocumentRaw
  Object.assign(state.doc, doc)
  // Drop keys that disappeared (Object.assign keeps stale extras).
  for (const key of Object.keys(state.doc)) {
    if (!(key in doc)) delete state.doc[key]
  }
  state.yamlText = stringifySceneYaml(state.doc)
  state.errors = validateSceneDoc(state.doc)
  state.selection = state.selection.filter((i) => i < (state.doc?.widgets?.length ?? 0))
  state.dirty = true
  historyVersion.value += 1
}

function pushHistory(): void {
  undoStack.push(snapshot())
  if (undoStack.length > MAX_HISTORY) undoStack.shift()
  redoStack = []
  historyVersion.value += 1
}

function beginBatch(): void {
  if (batchDepth === 0) pushHistory()
  batchDepth += 1
}

function endBatch(): void {
  batchDepth = Math.max(0, batchDepth - 1)
}

function undo(): void {
  if (undoStack.length === 0 || batchDepth > 0) return
  redoStack.push(snapshot())
  restore(undoStack.pop()!)
}

function redo(): void {
  if (redoStack.length === 0 || batchDepth > 0) return
  undoStack.push(snapshot())
  restore(redoStack.pop()!)
}

function canUndo(): boolean {
  void historyVersion.value
  return undoStack.length > 0
}

function canRedo(): boolean {
  void historyVersion.value
  return redoStack.length > 0
}

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
 * History: batches capture one snapshot via beginBatch(); standalone
 * calls capture automatically.
 */
function mutate(fn: (doc: SceneDocumentRaw) => void): void {
  if (state.doc === null || state.syntaxError !== null) return
  if (batchDepth === 0) pushHistory()
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

function setResolutionOverride(
  resolution: { width: number; height: number } | null,
): void {
  state.resolutionOverride = resolution
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
  undoStack = []
  redoStack = []
  batchDepth = 0
  historyVersion.value += 1
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

/** Delete raw widget entries by index (indices must be sorted asc). */
function deleteEntries(indices: number[]): void {
  mutate((doc) => {
    const widgets = doc.widgets ?? []
    for (const index of [...indices].sort((a, b) => b - a)) {
      if (index >= 0 && index < widgets.length) widgets.splice(index, 1)
    }
  })
}

/** Deep-clone raw entries and insert the copies after the last source. */
function duplicateEntries(indices: number[]): void {
  mutate((doc) => {
    const widgets = doc.widgets ?? []
    const clones = indices
      .filter((i) => i >= 0 && i < widgets.length)
      .map((i) => JSON.parse(JSON.stringify(widgets[i])) as EntryRaw)
    widgets.splice(Math.max(...indices) + 1, 0, ...clones)
  })
}

/** Move an entry to a new position (layers panel reorder = z-order). */
function moveEntry(from: number, to: number): void {
  mutate((doc) => {
    const widgets = doc.widgets ?? []
    if (from < 0 || from >= widgets.length) return
    const target = Math.max(0, Math.min(widgets.length - 1, to))
    const [entry] = widgets.splice(from, 1)
    if (entry !== undefined) widgets.splice(target, 0, entry)
  })
}

/** Set one field on a raw entry (graphical edits, inspector). */
function setEntryField(index: number, field: string, value: unknown): void {
  mutate((doc) => {
    const widgets = doc.widgets ?? []
    const entry = widgets[index]
    if (entry === undefined || !isObject(entry)) return
    if (value === undefined) delete entry[field]
    else entry[field] = value
  })
}

/** Apply an arbitrary update to one raw entry (inspector forms). */
function updateWidget(index: number, update: (entry: Record<string, unknown>) => void): void {
  mutate((doc) => {
    const entry = doc.widgets?.[index]
    if (entry === undefined || !isObject(entry)) return
    update(entry)
  })
}

/** Default widget templates for the add palette. */
const WIDGET_DEFAULTS: Record<string, Record<string, unknown>> = {
  text: {
    type: 'text',
    value: 'Text',
    align: 'center',
    style: { size: 24, color: '#FFFFFF' },
  },
  bar: {
    type: 'bar',
    source: 'cpu.percent',
    style: { fg: '#7CFC00', bg: '#222222', radius: 4 },
  },
  ring: {
    type: 'ring',
    source: 'cpu.percent',
    style: { fg: '#7CFC00', bg: '#222222', width: 8 },
  },
  graph: {
    type: 'graph',
    source: 'cpu.percent',
    history: 60,
    style: { fg: '#7CFC00', fill: true, line_width: 2 },
  },
  image: {
    type: 'image',
    path: '',
    scale: 1,
  },
}

const WIDGET_SIZES: Record<string, [number, number, number, number]> = {
  text: [-100, -20, 200, 40],
  bar: [-100, -8, 200, 16],
  ring: [-45, -45, 90, 90],
  graph: [-100, -40, 200, 80],
  image: [-32, -32, 64, 64],
}

/** Insert a new widget of the given type centered on the viewport. */
function addWidget(type: string, center: { x: number; y: number }): void {
  const defaults = WIDGET_DEFAULTS[type]
  const offset = WIDGET_SIZES[type]
  if (defaults === undefined || offset === undefined) return
  let newIndex = -1
  mutate((doc) => {
    const widgets = doc.widgets ?? []
    newIndex = widgets.length
    const entry: Record<string, unknown> = {
      ...JSON.parse(JSON.stringify(defaults)),
      rect: [
        Math.round(center.x) + offset[0],
        Math.round(center.y) + offset[1],
        offset[2],
        offset[3],
      ],
    }
    widgets.push(entry as EntryRaw)
    doc.widgets = widgets
  })
  if (newIndex >= 0) setSelection([newIndex])
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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
  setResolutionOverride,
  setName,
  setTime,
  setPlaying,
  setLoopDuration,
  uploadAssets,
  removeAsset,
  beginBatch,
  endBatch,
  undo,
  redo,
  canUndo,
  canRedo,
  deleteEntries,
  duplicateEntries,
  moveEntry,
  setEntryField,
  updateWidget,
  addWidget,
}

export type EditorStore = typeof editor
