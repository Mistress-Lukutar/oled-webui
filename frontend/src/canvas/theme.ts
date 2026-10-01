/**
 * Canvas paint colors shared across editors and thumbnails. Canvas 2D
 * contexts cannot read CSS variables, so the theme hexes live here next
 * to their style.css counterparts.
 */

/** Matches --bg-screen in style.css; the panel backdrop is black. */
export const CANVAS_BG = '#101210'

/** Matches --accent in style.css; selection/anchor chrome on canvases. */
export const ACCENT = '#35c98e'

/** Selection outline in the device designer (blue, distinct from accent). */
export const DESIGNER_SELECTION = '#4aa3ff'
