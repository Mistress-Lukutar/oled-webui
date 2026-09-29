/**
 * Singleton reactive store for the ARGB device designer modal: YAML source
 * of truth for one device definition, canvas selection and shape edits.
 */

import { reactive } from 'vue'
import { parse as parseYaml } from 'yaml'
import type { DecorShape, DeviceDefinition, LedShape } from './types'
import { defCenter, generateDual, generateRing, generateStrip } from './deviceDef'
import { stringifyYamlWithComments } from '../scene-editor/yamlSync'
import { API } from '../api'
import { useArgbStore } from './store'

/** Which list a selected shape belongs to (LEDs or decor). */
export interface ShapeRef {
  list: 'leds' | 'decor'
  index: number
}

export interface DesignerState {
  /** Definition id being edited; null = creating a new one. */
  defId: string | null
  yamlText: string
  doc: DeviceDefinition | null
  syntaxError: string | null
  dirty: boolean
  selected: ShapeRef | null
}

const BLANK_TEMPLATE = `\
# Device definition: one shape per LED in ` + '`leds`' + ` (list order = LED
# index); fills come from the effect engine. ` + '`decor`' + ` is artwork only.
id: my-device
name: My Device
size: [120, 120]
leds:
  - type: circle
    center: [60, 20]
    radius: 5
decor:
  - type: circle
    center: [60, 60]
    radius: 50
    fill: false
    stroke_color: "#3a3a3a"
    stroke_width: 2
`

const state = reactive<DesignerState>({
  defId: null,
  yamlText: BLANK_TEMPLATE,
  doc: null,
  syntaxError: null,
  dirty: false,
  selected: null,
})

function parseDoc(): void {
  try {
    const doc: unknown = parseYaml(state.yamlText)
    if (doc !== null && typeof doc === 'object' && !Array.isArray(doc)) {
      state.doc = doc as DeviceDefinition
      state.syntaxError = null
    } else {
      state.doc = null
      state.syntaxError = 'Definition must be a YAML mapping'
    }
  } catch (err) {
    state.doc = null
    state.syntaxError = err instanceof Error ? err.message : String(err)
  }
}

/** Edit the parsed document; the YAML text regenerates (comments grafted). */
function mutate(fn: (doc: DeviceDefinition) => void): void {
  if (state.doc === null) return
  fn(state.doc)
  state.yamlText = stringifyYamlWithComments(state.doc, state.yamlText)
  state.dirty = true
  parseDoc()
}

export function useDeviceDesigner() {
  const argb = useArgbStore()

  async function open(defId: string | null): Promise<void> {
    state.defId = defId
    state.selected = null
    state.dirty = false
    if (defId === null) {
      state.yamlText = BLANK_TEMPLATE
      parseDoc()
      return
    }
    try {
      const { yaml } = await API.getArgbDevice(defId)
      state.yamlText = yaml
      parseDoc()
    } catch (err) {
      argb.showError(err instanceof Error ? err.message : String(err))
      state.yamlText = BLANK_TEMPLATE
      parseDoc()
    }
  }

  function setYamlText(text: string): void {
    state.yamlText = text
    state.dirty = true
    parseDoc()
  }

  function select(ref: ShapeRef | null): void {
    state.selected = ref
  }

  function selectedShape(): LedShape | DecorShape | null {
    const { doc, selected } = state
    if (doc === null || selected === null) return null
    const list = selected.list === 'leds' ? doc.leds : doc.decor
    return list[selected.index] ?? null
  }

  function shiftShape(shape: LedShape | DecorShape, dx: number, dy: number): void {
    if (shape.type === 'rect') {
      shape.rect = [shape.rect[0] + dx, shape.rect[1] + dy, shape.rect[2], shape.rect[3]]
    } else if (shape.type === 'circle') {
      shape.center = [shape.center[0] + dx, shape.center[1] + dy]
    } else {
      shape.points = shape.points.map(([px, py]) => [px + dx, py + dy])
    }
  }

  /** Move the selected shape by a local-space delta (canvas drag). */
  function moveSelectedBy(dx: number, dy: number): void {
    const shape = selectedShape()
    if (shape === null) return
    mutate((doc) => {
      const list: (LedShape | DecorShape)[] =
        state.selected?.list === 'leds' ? doc.leds : doc.decor
      const shape2 = list[state.selected!.index]
      if (shape2 !== undefined) shiftShape(shape2, dx, dy)
    })
  }

  function deleteSelected(): void {
    const { selected } = state
    if (selected === null) return
    mutate((doc) => {
      const list = selected.list === 'leds' ? doc.leds : doc.decor
      if (list.length > 1 || selected.list === 'decor') list.splice(selected.index, 1)
    })
    state.selected = null
  }

  function defaultLedShape(doc: DeviceDefinition): LedShape {
    const c = defCenter(doc)
    return {
      type: 'circle',
      center: [Math.round(c.x), Math.round(c.y)],
      radius: 5,
    }
  }

  function defaultDecorShape(doc: DeviceDefinition): DecorShape {
    const c = defCenter(doc)
    return {
      type: 'rect',
      rect: [Math.round(c.x - 25), Math.round(c.y - 25), 50, 50],
      radius: 4,
      fill: false,
      fill_color: '#222222',
      stroke_color: '#3a3a3a',
      stroke_width: 2,
      stroke_align: 'inside',
      opacity: 1,
    }
  }

  function addShape(list: 'leds' | 'decor'): void {
    let addedIndex = -1
    mutate((doc) => {
      const shape =
        list === 'leds' ? defaultLedShape(doc) : defaultDecorShape(doc)
      const target: (LedShape | DecorShape)[] =
        list === 'leds' ? doc.leds : doc.decor
      if (target.length < 512) {
        target.push(shape)
        addedIndex = target.length - 1
      }
    })
    if (addedIndex >= 0) state.selected = { list, index: addedIndex }
  }

  /** Replace the whole design with a generated strip/ring/dual. */
  function generate(
    kind: 'strip' | 'ring' | 'dual',
    count: number,
    side: number,
  ): void {
    const generated =
      kind === 'strip'
        ? generateStrip(count)
        : kind === 'ring'
          ? generateRing(count)
          : generateDual(count, side)
    mutate((doc) => {
      doc.leds = generated.leds
      doc.decor = generated.decor
    })
    state.selected = null
  }

  async function save(): Promise<boolean> {
    if (state.doc === null || state.syntaxError !== null) return false
    const ok =
      state.defId === null
        ? await argb.actions.createDeviceDefinition(state.yamlText)
        : await argb.actions.updateDeviceDefinition(state.defId, state.yamlText)
    if (ok) {
      state.defId = state.doc.id
      state.dirty = false
    }
    return ok
  }

  return {
    state,
    open,
    setYamlText,
    select,
    moveSelectedBy,
    deleteSelected,
    addShape,
    generate,
    save,
  }
}
