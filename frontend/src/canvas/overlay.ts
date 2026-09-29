/**
 * Interaction overlay rendering for canvas stages: marquee rectangle,
 * snap guides, selection frames and resize handles. Drawn in logical
 * canvas coordinates on top of the host's content.
 */

import { handlePositions } from './geometry'
import type { HandleId, SnapGuide, WidgetBox } from './geometry'
import type { MarqueeRect, StageBox } from './stage'

export const STAGE_ACCENT = '#35c98e'

const HANDLES: HandleId[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

export interface OverlayInput {
  boxes: StageBox[]
  selection: string[]
  marquee: MarqueeRect | null
  guides: SnapGuide[]
  zoom: number
  accent?: string
}

export function drawStageOverlay(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  input: OverlayInput,
): void {
  const accent = input.accent ?? STAGE_ACCENT
  const selection = input.boxes.filter((info) => input.selection.includes(info.id))
  const line = 1.5 / input.zoom
  const handleSize = 8 / input.zoom

  if (input.marquee !== null) {
    const m = input.marquee
    ctx.save()
    ctx.fillStyle = 'rgba(53, 201, 142, 0.12)'
    ctx.strokeStyle = accent
    ctx.lineWidth = line
    ctx.fillRect(
      Math.min(m.x1, m.x2),
      Math.min(m.y1, m.y2),
      Math.abs(m.x2 - m.x1),
      Math.abs(m.y2 - m.y1),
    )
    ctx.strokeRect(
      Math.min(m.x1, m.x2),
      Math.min(m.y1, m.y2),
      Math.abs(m.x2 - m.x1),
      Math.abs(m.y2 - m.y1),
    )
    ctx.restore()
  }

  for (const guide of input.guides) {
    ctx.save()
    ctx.strokeStyle = accent
    ctx.lineWidth = line
    ctx.setLineDash([6 / input.zoom, 4 / input.zoom])
    ctx.beginPath()
    if (guide.axis === 'x') {
      ctx.moveTo(guide.at, 0)
      ctx.lineTo(guide.at, height)
    } else {
      ctx.moveTo(0, guide.at)
      ctx.lineTo(width, guide.at)
    }
    ctx.stroke()
    ctx.restore()
  }

  for (const info of selection) {
    const { box } = info
    // Single plain boxes draw their frame rotated with the box.
    const rotateFrame = selection.length === 1 && !info.handleless && !info.locked
    const rotation = rotateFrame ? info.rotation : 0
    ctx.save()
    ctx.strokeStyle = info.locked ? '#8a8a8a' : accent
    ctx.lineWidth = line
    if (info.handleless || info.locked) ctx.setLineDash([5 / input.zoom, 3 / input.zoom])
    drawRotatedRect(ctx, box, rotation)
    if (!info.handleless && !info.locked) {
      // Handles: white squares with accent border, screen-constant size;
      // drawn in the (rotated) frame so they follow the box.
      const positions = handlePositions(box)
      for (const id of HANDLES) {
        const p = positions[id]
        ctx.save()
        ctx.fillStyle = '#ffffff'
        ctx.strokeStyle = accent
        ctx.lineWidth = line
        ctx.beginPath()
        ctx.rect(p.x - handleSize / 2, p.y - handleSize / 2, handleSize, handleSize)
        ctx.fill()
        ctx.stroke()
        ctx.restore()
      }
    }
    ctx.restore()
  }
}

function drawRotatedRect(
  ctx: CanvasRenderingContext2D,
  box: WidgetBox,
  rotation: number,
): void {
  if (rotation % 360 !== 0) {
    const cx = box.x + box.w / 2
    const cy = box.y + box.h / 2
    ctx.translate(cx, cy)
    ctx.rotate((-rotation * Math.PI) / 180)
    ctx.translate(-cx, -cy)
  }
  ctx.strokeRect(box.x, box.y, box.w, box.h)
}
