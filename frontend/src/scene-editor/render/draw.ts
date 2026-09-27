/**
 * Canvas 2D rendering of scene widgets, approximating the Pillow
 * renderers in src/oled_webui/scene/widgets.py. The server render stays
 * the pixel-exact reference (Check frame); this mirror exists for
 * interactive editing.
 */

import { API } from '../../api'
import type { EvalEntry } from '../runtime'
import { loadedFontFamily } from './fonts'

export interface ImageCache {
  /** Resolve a sprite; returns the element, or null while/when missing. */
  get(sceneId: string, path: string): HTMLImageElement | null
}

/** Shared image cache keyed by scene id + path. */
export function createImageCache(onChange?: () => void): ImageCache {
  const cache = new Map<string, HTMLImageElement | null>()
  return {
    get(sceneId: string, path: string): HTMLImageElement | null {
      const basename = path.replaceAll('\\', '/').split('/').pop() ?? ''
      if (basename === '') return null
      const key = `${sceneId}:${basename}`
      if (cache.has(key)) return cache.get(key) ?? null
      const image = new Image()
      cache.set(key, null)
      image.onload = () => {
        cache.set(key, image)
        onChange?.()
      }
      image.onerror = () => onChange?.()
      image.src = API.sceneAssetUrl(sceneId, basename)
      return null
    },
  }
}

/** #RGB/#RRGGBB/#RRGGBBAA to canvas color; invalid specs fall back. */
function cssColor(spec: string | null | undefined, fallback = '#ffffff'): string {
  if (spec === null || spec === undefined) return fallback
  const text = spec.trim().toLowerCase()
  if (text === 'white') return '#ffffff'
  if (text === 'black') return '#000000'
  if (/^#[0-9a-f]{3}$/.test(text)) return text
  if (/^#[0-9a-f]{6}([0-9a-f]{2})?$/.test(text)) return text
  return fallback
}

function rgba(spec: string, alpha: number): string {
  const text = cssColor(spec).slice(1)
  const r = parseInt(text.slice(0, 2), 16)
  const g = parseInt(text.slice(2, 4), 16)
  const b = parseInt(text.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2))
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, radius)
}

function drawBar(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  value01: number,
  widget: Record<string, unknown>,
): void {
  const style = (widget['style'] ?? {}) as Record<string, unknown>
  const fg = cssColor(style['fg'] as string, '#7CFC00')
  const bg = cssColor(style['bg'] as string, '#222222')
  const border = typeof style['border'] === 'number' ? style['border'] : 0
  const borderColor = cssColor(style['border_color'] as string, '#888888')
  const radius = typeof style['radius'] === 'number' ? style['radius'] : 0
  const horizontal = (style['orientation'] ?? 'horizontal') !== 'vertical'
  const fill01 = Math.max(0, Math.min(1, value01))

  if (border > 0) {
    ctx.lineWidth = border
    ctx.strokeStyle = borderColor
    roundedRect(ctx, border / 2, border / 2, w - border, h - border, radius)
    ctx.stroke()
  }
  ctx.fillStyle = bg
  roundedRect(ctx, 0, 0, w, h, radius)
  ctx.fill()

  const inset = border > 0 ? border + 1 : 0
  if (horizontal) {
    const trackW = w - 2 * inset
    const filled = Math.trunc(trackW * fill01)
    if (filled > 0) {
      ctx.fillStyle = fg
      roundedRect(ctx, inset, inset, filled, h - 2 * inset, Math.min(radius, h / 2))
      ctx.fill()
    }
  } else {
    const trackH = h - 2 * inset
    const filled = Math.trunc(trackH * fill01)
    if (filled > 0) {
      ctx.fillStyle = fg
      roundedRect(
        ctx,
        inset,
        h - inset - filled,
        w - 2 * inset,
        filled,
        Math.min(radius, w / 2),
      )
      ctx.fill()
    }
  }
}

function drawRing(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  value01: number,
  widget: Record<string, unknown>,
): void {
  const style = (widget['style'] ?? {}) as Record<string, unknown>
  const fg = cssColor(style['fg'] as string, '#7CFC00')
  const bg = cssColor(style['bg'] as string, '#222222')
  const width = typeof style['width'] === 'number' ? style['width'] : 8
  const startAngle = typeof style['start_angle'] === 'number' ? style['start_angle'] : -90
  const sweep = typeof style['sweep'] === 'number' ? style['sweep'] : 360
  const size = Math.min(w, h) - 1
  const cx = w / 2
  const cy = h / 2
  // PIL draws arc strokes inward from the ellipse; match by centering the
  // canvas stroke inside that boundary.
  const radius = size / 2 - width / 2
  if (radius <= 0) return
  const fill01 = Math.max(0, Math.min(1, value01))

  ctx.lineCap = 'butt'
  ctx.lineWidth = width
  ctx.strokeStyle = bg
  ctx.beginPath()
  ctx.arc(cx, cy, radius, (startAngle * Math.PI) / 180, ((startAngle + sweep) * Math.PI) / 180)
  ctx.stroke()
  if (fill01 > 0) {
    ctx.strokeStyle = fg
    ctx.beginPath()
    ctx.arc(
      cx,
      cy,
      radius,
      (startAngle * Math.PI) / 180,
      ((startAngle + sweep * fill01) * Math.PI) / 180,
    )
    ctx.stroke()
  }
}

function drawGraph(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  history: number[],
  widget: Record<string, unknown>,
): void {
  const style = (widget['style'] ?? {}) as Record<string, unknown>
  const fg = cssColor(style['fg'] as string, '#7CFC00')
  const bg = style['bg'] === undefined || style['bg'] === null ? null : String(style['bg'])
  const fill = style['fill'] !== false
  const lineWidth = typeof style['line_width'] === 'number' ? style['line_width'] : 2
  const scaleMax = typeof style['scale_max'] === 'number' ? style['scale_max'] : null

  if (bg !== null) {
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, w, h)
  }
  if (history.length < 2) return

  const peak = Math.max(scaleMax ?? Math.max(...history), 1e-6)
  const count = history.length
  const points: Array<[number, number]> = history.map((sample, index) => {
    const px = (w * index) / (count - 1)
    const norm = Math.max(0, Math.min(1, sample / peak))
    const py = h - 1 - (h - 1) * norm
    return [px, py]
  })

  if (fill) {
    ctx.fillStyle = rgba(fg, 96 / 255)
    ctx.beginPath()
    ctx.moveTo(0, h - 1)
    for (const [px, py] of points) ctx.lineTo(px, py)
    ctx.lineTo(w - 1, h - 1)
    ctx.closePath()
    ctx.fill()
  }
  ctx.strokeStyle = fg
  ctx.lineWidth = lineWidth
  ctx.lineJoin = 'round'
  ctx.beginPath()
  for (let i = 0; i < points.length; i += 1) {
    const [px, py] = points[i]!
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.stroke()
}

function drawText(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  text: string,
  widget: Record<string, unknown>,
  sceneId: string,
): void {
  const style = (widget['style'] ?? {}) as Record<string, unknown>
  const size = typeof style['size'] === 'number' ? Math.trunc(style['size']) : 24
  const color = cssColor(style['color'] as string, '#FFFFFF')
  const align = (widget['align'] ?? 'left') as 'left' | 'center' | 'right'
  const familyValue = style['family']
  const custom =
    typeof familyValue === 'string' ? loadedFontFamily(sceneId, familyValue) : null
  ctx.font = `${size}px ${custom ?? "'Segoe UI', system-ui, sans-serif"}`
  ctx.fillStyle = color
  ctx.textBaseline = 'alphabetic'

  const metrics = ctx.measureText(text)
  const textW = metrics.width
  const ascent = metrics.actualBoundingBoxAscent
  const descent = metrics.actualBoundingBoxDescent
  const textH = ascent + descent
  let tx = 0
  if (align === 'center') tx = (w - textW) / 2
  else if (align === 'right') tx = w - textW
  const ty = Math.max(0, (h - textH) / 2) + ascent
  ctx.fillText(text, tx, ty)
}

function drawImage(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  widget: Record<string, unknown>,
  sceneId: string,
  images: ImageCache,
  opacity: number,
  rotation: number,
): boolean {
  const path = widget['path']
  if (typeof path !== 'string') return false
  const sprite = images.get(sceneId, path)
  if (sprite === null || !sprite.complete || sprite.naturalWidth === 0) return false
  const fit = typeof widget['fit'] === 'string' ? widget['fit'] : 'scale'
  let sizeW: number
  let sizeH: number
  if (fit === 'stretch') {
    sizeW = Math.max(1, w)
    sizeH = Math.max(1, h)
  } else if (fit === 'contain' || fit === 'cover') {
    const ratioW = w / sprite.naturalWidth
    const ratioH = h / sprite.naturalHeight
    const factor =
      fit === 'contain' ? Math.min(ratioW, ratioH) : Math.max(ratioW, ratioH)
    sizeW = Math.max(1, Math.trunc(sprite.naturalWidth * factor))
    sizeH = Math.max(1, Math.trunc(sprite.naturalHeight * factor))
  } else {
    const scale = typeof widget['scale'] === 'number' ? widget['scale'] : 1
    sizeW = Math.max(1, Math.trunc(sprite.naturalWidth * scale))
    sizeH = Math.max(1, Math.trunc(sprite.naturalHeight * scale))
  }

  ctx.save()
  ctx.globalAlpha = Math.max(0, Math.min(1, opacity))
  // Pillow rotates counter-clockwise; canvas is clockwise.
  if (rotation % 360 !== 0) {
    ctx.translate(x + w / 2, y + h / 2)
    ctx.rotate((-rotation * Math.PI) / 180)
    ctx.translate(-sizeW / 2, -sizeH / 2)
  } else {
    ctx.translate(x + (w - sizeW) / 2, y + (h - sizeH) / 2)
  }
  ctx.drawImage(sprite, 0, 0, sizeW, sizeH)
  ctx.restore()
  return true
}

export interface DrawSceneOptions {
  ctx: CanvasRenderingContext2D
  background: readonly Record<string, unknown>[]
  entries: readonly EvalEntry[]
  width: number
  height: number
  sceneId: string
  images: ImageCache
  showGrid?: boolean
  /** Grid cell size in panel pixels. */
  gridPixelSize?: number
}

/** Draw the full scene (background layers, widgets, optional grid). */
export function drawScene(opts: DrawSceneOptions): void {
  const { ctx, entries, background, width, height, sceneId, images } = opts
  ctx.save()
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, width, height)

  // Background layers: no pos stretches to the canvas, otherwise the
  // sprite draws at pos/scale/opacity (mirrors _render_static).
  for (const layer of background) {
    const sprite = images.get(sceneId, String(layer['path'] ?? ''))
    if (sprite === null || !sprite.complete || sprite.naturalWidth === 0) continue
    const scale = typeof layer['scale'] === 'number' ? layer['scale'] : 1
    const opacity = typeof layer['opacity'] === 'number' ? layer['opacity'] : 1
    const pos = layer['pos']
    ctx.save()
    ctx.globalAlpha = Math.max(0, Math.min(1, opacity))
    if (pos === undefined || pos === null) {
      ctx.drawImage(sprite, 0, 0, width, height)
    } else if (Array.isArray(pos) && pos.length === 2) {
      ctx.drawImage(
        sprite,
        Math.trunc(Number(pos[0])),
        Math.trunc(Number(pos[1])),
        Math.trunc(sprite.naturalWidth * scale),
        Math.trunc(sprite.naturalHeight * scale),
      )
    }
    ctx.restore()
  }

  for (const entry of entries) {
    if (!entry.visible) continue
    const widget = entry.expanded.widget
    const rect = entry.expanded.widget['rect']
    if (!Array.isArray(rect) || rect.length !== 4) continue
    const x = Math.trunc(Number(rect[0])) + entry.offsetX
    const y = Math.trunc(Number(rect[1])) + entry.offsetY
    const w = Math.max(1, Math.trunc(Number(rect[2])))
    const h = Math.max(1, Math.trunc(Number(rect[3])))
    const type = widget['type']

    const drawn = drawImage(
      ctx,
      x,
      y,
      w,
      h,
      widget as Record<string, unknown>,
      sceneId,
      images,
      entry.opacity,
      entry.rotation,
    )
    if (drawn) continue

    // Non-image widgets render into their clipped box, like the Pillow
    // scratch layer.
    ctx.save()
    ctx.beginPath()
    ctx.rect(x, y, w, h)
    ctx.clip()
    ctx.globalAlpha = Math.max(0, Math.min(1, entry.opacity))
    ctx.translate(x, y)
    const widgetRecord = widget as Record<string, unknown>
    if (type === 'bar') drawBar(ctx, w, h, entry.value01, widgetRecord)
    else if (type === 'ring') drawRing(ctx, w, h, entry.value01, widgetRecord)
    else if (type === 'graph') drawGraph(ctx, w, h, entry.history, widgetRecord)
    else if (type === 'text') drawText(ctx, w, h, entry.text, widgetRecord, sceneId)
    ctx.restore()
  }

  if (opts.showGrid === true && opts.gridPixelSize !== undefined) {
    drawGrid(ctx, width, height, opts.gridPixelSize)
  }
  ctx.restore()
}

function drawGrid(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  size: number,
): void {
  ctx.save()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)'
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let x = size; x < width; x += size) {
    ctx.moveTo(x + 0.5, 0)
    ctx.lineTo(x + 0.5, height)
  }
  for (let y = size; y < height; y += size) {
    ctx.moveTo(0, y + 0.5)
    ctx.lineTo(width, y + 0.5)
  }
  ctx.stroke()
  ctx.restore()
}
