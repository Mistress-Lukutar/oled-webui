/**
 * Client-side validation of a scene file's ``argb`` section, mirroring
 * src/oled_webui/argb/schema.py (extra="forbid" + ranges + cross
 * references). The server stays authoritative on save; these checks give
 * instant feedback while typing.
 */

import { isObject } from '../scene-editor/types'

const EFFECT_KEYS: Record<string, Set<string>> = {
  fill: new Set(['type', 'color']),
  gradient: new Set(['type', 'stops', 'scale', 'mode', 'speed']),
  rainbow: new Set(['type', 'speed', 'scale', 'direction', 'saturation', 'value']),
  breathing: new Set(['type', 'colors', 'period', 'min_level']),
  comet: new Set(['type', 'color', 'tail', 'speed', 'direction', 'mode', 'fade']),
  scanner: new Set(['type', 'color', 'width', 'period']),
  meter: new Set(['type', 'source', 'color_low', 'color_high', 'max_value', 'mode']),
}

const LAYOUT_KEYS = new Set(['fps', 'brightness', 'headers', 'devices', 'layers'])
const HEADER_KEYS = new Set(['id', 'name', 'zone_index', 'size', 'devices'])
const DEVICE_KEYS = new Set(['id', 'name', 'device', 'header_id', 'x', 'y', 'rotation', 'scale'])
const LAYER_KEYS = new Set(['id', 'name', 'enabled', 'opacity', 'mask', 'effect'])
const MASK_KEYS = new Set(['all', 'runs'])

const COLOR_RE = /^#?[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/

function fmt(value: unknown): string {
  return typeof value === 'string' ? `"${value}"` : String(value)
}

function isNum(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function int(
  errors: string[],
  where: string,
  value: unknown,
  min: number,
  max: number,
): void {
  if (!isNum(value)) return
  if (!Number.isInteger(value) || value < min || value > max) {
    errors.push(`${where}: must be an integer ${min}..${max}, got ${fmt(value)}`)
  }
}

function num(
  errors: string[],
  where: string,
  value: unknown,
  min: number,
  max: number,
): void {
  if (!isNum(value)) return
  if (value < min || value > max) {
    errors.push(`${where}: must be ${min}..${max}, got ${fmt(value)}`)
  }
}

function gt(
  errors: string[],
  where: string,
  value: unknown,
  min: number,
  max: number | null,
): void {
  if (!isNum(value)) return
  if (value <= min) {
    errors.push(`${where}: must be > ${min}, got ${fmt(value)}`)
  } else if (max !== null && value > max) {
    errors.push(`${where}: must be <= ${max}, got ${fmt(value)}`)
  }
}

function oneOf(
  errors: string[],
  where: string,
  value: unknown,
  allowed: readonly string[],
): void {
  if (typeof value === 'string' && !allowed.includes(value)) {
    errors.push(`${where}: unknown value ${fmt(value)} (${allowed.join(', ')})`)
  }
}

function color(errors: string[], where: string, value: unknown): void {
  if (typeof value !== 'string') return
  if (!COLOR_RE.test(value)) {
    errors.push(`${where}: expected #RRGGBB[AA] color, got ${fmt(value)}`)
  }
}

function unknownKeys(
  errors: string[],
  where: string,
  value: unknown,
  allowed: Set<string>,
): void {
  if (!isObject(value)) return
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) errors.push(`${where}: unknown key "${key}"`)
  }
}

function checkEffect(errors: string[], where: string, effect: unknown): void {
  if (!isObject(effect)) {
    errors.push(`${where}: must be a mapping`)
    return
  }
  const type = effect['type']
  if (typeof type !== 'string' || !(type in EFFECT_KEYS)) {
    errors.push(
      `${where}: unknown effect type ${fmt(type)} (${Object.keys(EFFECT_KEYS).join(', ')})`,
    )
    return
  }
  unknownKeys(errors, where, effect, EFFECT_KEYS[type]!)
  const w = `${where}.${type}`
  if (type === 'fill') {
    color(errors, `${w}.color`, effect['color'])
  } else if (type === 'gradient') {
    const stops = effect['stops']
    if (stops !== undefined) {
      if (!Array.isArray(stops) || stops.length < 2) {
        errors.push(`${w}.stops: must be a list of at least 2 stops`)
      } else {
        stops.forEach((stop, i) => {
          if (!isObject(stop)) {
            errors.push(`${w}.stops[${i}]: must be a mapping`)
            return
          }
          num(errors, `${w}.stops[${i}].pos`, stop['pos'], 0, 1)
          color(errors, `${w}.stops[${i}].color`, stop['color'])
        })
      }
    }
    int(errors, `${w}.scale`, effect['scale'], 2, 1024)
    oneOf(errors, `${w}.mode`, effect['mode'], ['static', 'scroll', 'pingpong'])
    num(errors, `${w}.speed`, effect['speed'], -20, 20)
  } else if (type === 'rainbow') {
    num(errors, `${w}.speed`, effect['speed'], 0, 20)
    int(errors, `${w}.scale`, effect['scale'], 2, 1024)
    if (effect['direction'] !== undefined && effect['direction'] !== 1 && effect['direction'] !== -1) {
      errors.push(`${w}.direction: must be 1 or -1`)
    }
    num(errors, `${w}.saturation`, effect['saturation'], 0, 1)
    num(errors, `${w}.value`, effect['value'], 0, 1)
  } else if (type === 'breathing') {
    const colors = effect['colors']
    if (colors !== undefined) {
      if (!Array.isArray(colors) || colors.length < 1) {
        errors.push(`${w}.colors: must be a non-empty list`)
      } else {
        colors.forEach((c, i) => color(errors, `${w}.colors[${i}]`, c))
      }
    }
    gt(errors, `${w}.period`, effect['period'], 0, 60)
    num(errors, `${w}.min_level`, effect['min_level'], 0, 1)
  } else if (type === 'comet') {
    color(errors, `${w}.color`, effect['color'])
    int(errors, `${w}.tail`, effect['tail'], 0, 512)
    num(errors, `${w}.speed`, effect['speed'], 0, 500)
    if (effect['direction'] !== undefined && effect['direction'] !== 1 && effect['direction'] !== -1) {
      errors.push(`${w}.direction: must be 1 or -1`)
    }
    oneOf(errors, `${w}.mode`, effect['mode'], ['loop', 'bounce'])
  } else if (type === 'scanner') {
    color(errors, `${w}.color`, effect['color'])
    int(errors, `${w}.width`, effect['width'], 1, 512)
    gt(errors, `${w}.period`, effect['period'], 0, 60)
  } else if (type === 'meter') {
    const source = effect['source']
    if (typeof source === 'string' && source.trim() === '') {
      errors.push(`${w}.source: must not be empty`)
    }
    color(errors, `${w}.color_low`, effect['color_low'])
    color(errors, `${w}.color_high`, effect['color_high'])
    gt(errors, `${w}.max_value`, effect['max_value'], 0, null)
    oneOf(errors, `${w}.mode`, effect['mode'], ['fill', 'bar'])
  }
}

function checkMask(errors: string[], where: string, mask: unknown): void {
  if (mask === undefined) return
  if (!isObject(mask)) {
    errors.push(`${where}: must be a mapping`)
    return
  }
  unknownKeys(errors, where, mask, MASK_KEYS)
  if (mask['all'] !== undefined && typeof mask['all'] !== 'boolean') {
    errors.push(`${where}.all: must be a boolean`)
  }
  const runs = mask['runs']
  if (runs === undefined) return
  if (!isObject(runs)) {
    errors.push(`${where}.runs: must be a mapping`)
    return
  }
  for (const [deviceId, ranges] of Object.entries(runs)) {
    if (!Array.isArray(ranges)) {
      errors.push(`${where}.runs.${deviceId}: must be a list of [start, end] pairs`)
      continue
    }
    ranges.forEach((range, i) => {
      if (
        !Array.isArray(range) ||
        range.length !== 2 ||
        !range.every((n) => isNum(n) && Number.isInteger(n) && n >= 0)
      ) {
        errors.push(`${where}.runs.${deviceId}[${i}]: must be [start, end] LED indexes`)
      } else if (range[0] > range[1]) {
        errors.push(`${where}.runs.${deviceId}[${i}]: start must be <= end`)
      }
    })
  }
}

/**
 * Validate one parsed ``argb`` section value; returns human-readable
 * problems (empty list = OK).
 */
export function validateArgbSection(section: unknown): string[] {
  const errors: string[] = []
  if (!isObject(section)) {
    errors.push('argb: section must be a mapping')
    return errors
  }
  unknownKeys(errors, 'argb', section, LAYOUT_KEYS)
  int(errors, 'argb.fps', section['fps'], 1, 60)
  int(errors, 'argb.brightness', section['brightness'], 0, 200)

  const headers = section['headers']
  if (headers !== undefined) {
    if (!Array.isArray(headers)) {
      errors.push('argb.headers: must be a list')
    } else {
      headers.forEach((header, i) => {
        const w = `argb.headers[${i}]`
        if (!isObject(header)) {
          errors.push(`${w}: must be a mapping`)
          return
        }
        unknownKeys(errors, w, header, HEADER_KEYS)
        if (typeof header['id'] !== 'string' || header['id'] === '') {
          errors.push(`${w}.id: is required`)
        }
        int(errors, `${w}.zone_index`, header['zone_index'], 0, 65535)
        const size = header['size']
        if (size !== null && size !== undefined) {
          int(errors, `${w}.size`, size, 1, 1024)
        }
        const devices = header['devices']
        if (devices !== undefined && !Array.isArray(devices)) {
          errors.push(`${w}.devices: must be a list of device ids`)
        }
      })
    }
  }

  const devices = section['devices']
  if (devices !== undefined) {
    if (!Array.isArray(devices)) {
      errors.push('argb.devices: must be a list')
    } else {
      devices.forEach((device, i) => {
        const w = `argb.devices[${i}]`
        if (!isObject(device)) {
          errors.push(`${w}: must be a mapping`)
          return
        }
        unknownKeys(errors, w, device, DEVICE_KEYS)
        if (typeof device['id'] !== 'string' || device['id'] === '') {
          errors.push(`${w}.id: is required`)
        }
        if (typeof device['device'] !== 'string' || device['device'] === '') {
          errors.push(`${w}.device: is required (library definition id)`)
        }
        if (typeof device['header_id'] !== 'string' || device['header_id'] === '') {
          errors.push(`${w}.header_id: is required`)
        }
        num(errors, `${w}.rotation`, device['rotation'], -360, 360)
        gt(errors, `${w}.scale`, device['scale'], 0, 10)
      })
    }
  }

  const layers = section['layers']
  if (layers !== undefined) {
    if (!Array.isArray(layers)) {
      errors.push('argb.layers: must be a list')
    } else {
      layers.forEach((layer, i) => {
        const w = `argb.layers[${i}]`
        if (!isObject(layer)) {
          errors.push(`${w}: must be a mapping`)
          return
        }
        unknownKeys(errors, w, layer, LAYER_KEYS)
        if (typeof layer['id'] !== 'string' || layer['id'] === '') {
          errors.push(`${w}.id: is required`)
        }
        num(errors, `${w}.opacity`, layer['opacity'], 0, 1)
        checkMask(errors, `${w}.mask`, layer['mask'])
        if (layer['effect'] === undefined) {
          errors.push(`${w}.effect: is required`)
        } else {
          checkEffect(errors, `${w}.effect`, layer['effect'])
        }
      })
    }
  }

  checkReferences(errors, section)
  return errors
}

function checkReferences(errors: string[], section: Record<string, unknown>): void {
  const headers = Array.isArray(section['headers']) ? section['headers'] : []
  const devices = Array.isArray(section['devices']) ? section['devices'] : []
  const layers = Array.isArray(section['layers']) ? section['layers'] : []

  const deviceIds = devices
    .map((d) => (isObject(d) ? d['id'] : null))
    .filter((id): id is string => typeof id === 'string')
  const headerIds = headers
    .map((h) => (isObject(h) ? h['id'] : null))
    .filter((id): id is string => typeof id === 'string')
  const layerIds = layers
    .map((l) => (isObject(l) ? l['id'] : null))
    .filter((id): id is string => typeof id === 'string')

  for (const [label, ids] of [
    ['device', deviceIds],
    ['header', headerIds],
    ['layer', layerIds],
  ] as const) {
    const dup = ids.find((id, i) => ids.indexOf(id) !== i)
    if (dup !== undefined) errors.push(`argb: duplicate ${label} id ${fmt(dup)}`)
  }

  const known = new Set(deviceIds)
  const chained = new Set<string>()
  for (const header of headers) {
    if (!isObject(header)) continue
    const hid = header['id']
    const list = Array.isArray(header['devices']) ? header['devices'] : []
    for (const deviceId of list) {
      if (!known.has(deviceId as string)) {
        errors.push(`argb: header ${fmt(hid)} references unknown device ${fmt(deviceId)}`)
        continue
      }
      if (chained.has(deviceId as string)) {
        errors.push(
          `argb: device ${fmt(deviceId)} is chained on more than one header`,
        )
      }
      chained.add(deviceId as string)
    }
  }
  for (const device of devices) {
    if (!isObject(device)) continue
    const id = device['id'] as string
    const headerId = device['header_id']
    if (!chained.has(id)) {
      errors.push(`argb: device ${fmt(id)} is not chained on any header devices list`)
    } else {
      const host = headers.find((h) =>
        isObject(h) && Array.isArray(h['devices']) && h['devices'].includes(id),
      )
      if (host !== undefined && isObject(host) && host['id'] !== headerId) {
        errors.push(
          `argb: device ${fmt(id)} declares header ${fmt(headerId)} but is chained on ${fmt(host['id'])}`,
        )
      }
    }
  }
  for (const layer of layers) {
    if (!isObject(layer) || !isObject(layer['mask'])) continue
    const runs = layer['mask']['runs']
    if (!isObject(runs)) continue
    for (const deviceId of Object.keys(runs)) {
      if (!known.has(deviceId)) {
        errors.push(`argb: layer ${fmt(layer['id'])} mask references unknown device ${fmt(deviceId)}`)
      }
    }
  }
}
