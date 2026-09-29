/**
 * Custom CSS cursors for the canvas. SVG data URIs are generated at
 * runtime so one glyph can be re-oriented per corner; the black arrow
 * sits on a white outline to stay visible on any background.
 */

import type { CornerId } from './geometry'

/** Curved double-headed arrow: arc bulging up + V wings at both ends. */
const ROTATE_GLYPH = [
  'M 5.07 8 A 8 8 0 0 1 18.93 8',
  'M 19.17 4.39 L 18.93 8 L 15.69 6.39',
  'M 4.83 4.39 L 5.07 8 L 8.31 6.39',
].join(' ')

function rotateSvg(deg: number): string {
  return (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">' +
    `<g fill="none" stroke-linecap="round" stroke-linejoin="round" transform="rotate(${deg} 12 12)">` +
    `<path d="${ROTATE_GLYPH}" stroke="#ffffff" stroke-width="4.5"/>` +
    `<path d="${ROTATE_GLYPH}" stroke="#000000" stroke-width="2"/>` +
    '</g></svg>'
  )
}

function svgCursor(svg: string): string {
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") 12 12, auto`
}

/** Rotation cursors: the arc bulges away from the box center. */
const ROTATE_CURSORS: Record<CornerId, string> = {
  nw: svgCursor(rotateSvg(45)),
  ne: svgCursor(rotateSvg(315)),
  se: svgCursor(rotateSvg(225)),
  sw: svgCursor(rotateSvg(135)),
}

/** CSS cursor for dragging just outside a corner to rotate. */
export function rotateCursor(corner: CornerId): string {
  return ROTATE_CURSORS[corner]
}
