/**
 * Central SVG icon registry for AppIcon. Every glyph lives here so the
 * editors and dashboard share one set of stroke icons (24×24 grid,
 * stroke=currentColor, width 1.8) instead of scattered emoji and
 * text symbols. Bodies may override fill/stroke per element (e.g. solid
 * dots and play triangles use fill).
 */

export type IconName =
  | 'close'
  | 'plus'
  | 'chevron-up'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'check'
  | 'play'
  | 'pause'
  | 'undo'
  | 'redo'
  | 'eye'
  | 'eye-off'
  | 'lock'
  | 'unlock'
  | 'trash'
  | 'grip'
  | 'pencil'
  | 'gear'
  | 'dot-on'
  | 'dot-off'
  | 'text'
  | 'bar'
  | 'ring'
  | 'graph'
  | 'image'
  | 'rect'
  | 'ellipse'
  | 'line'
  | 'video'
  | 'drop-image'
  | 'drop-video'

export const ICONS: Record<IconName, string> = {
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  'chevron-up': '<path d="M7 14l5-5 5 5"/>',
  'chevron-down': '<path d="M7 10l5 5 5-5"/>',
  'chevron-left': '<path d="M14 7l-5 5 5 5"/>',
  'chevron-right': '<path d="M10 7l5 5-5 5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M8 5h3v14H8zM13 5h3v14h-3z" fill="currentColor" stroke="none"/>',
  undo: '<path d="M9 13 4 8l5-5"/><path d="M4 8h9a7 7 0 0 1 7 7 7 7 0 0 1-7 7h-2"/>',
  redo: '<path d="M15 13l5-5-5-5"/><path d="M20 8h-9a7 7 0 0 0-7 7 7 7 0 0 0 7 7h2"/>',
  eye: '<path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/>',
  'eye-off':
    '<path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/><line x1="4" y1="3" x2="20" y2="21"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  unlock:
    '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
  trash:
    '<path d="M4 7h16M10 11v6M14 11v6M6.5 7l1 13h9l1-13M9.5 7V4h5v3"/>',
  grip: '<g fill="currentColor" stroke="none"><circle cx="9" cy="6" r="1.7"/><circle cx="15" cy="6" r="1.7"/><circle cx="9" cy="12" r="1.7"/><circle cx="15" cy="12" r="1.7"/><circle cx="9" cy="18" r="1.7"/><circle cx="15" cy="18" r="1.7"/></g>',
  pencil:
    '<path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1z"/><path d="M13.5 7.5l3 3"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v3M12 18.2v3M2.8 12h3M18.2 12h3M5.5 5.5l2.1 2.1M16.4 16.4l2.1 2.1M18.5 5.5l-2.1 2.1M7.6 16.4l-2.1 2.1"/>',
  'dot-on':
    '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none"/>',
  'dot-off': '<circle cx="12" cy="12" r="7"/>',
  text: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
  bar: '<rect x="3" y="9" width="18" height="6" rx="1"/><rect x="5" y="11" width="7" height="2" fill="currentColor" stroke="none"/>',
  ring: '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
  graph: '<path d="M3 17c3 0 3-8 6-8s3 6 6 6 3-4 6-4"/>',
  image:
    '<rect x="3" y="5" width="18" height="14" rx="1.5"/><circle cx="9" cy="10" r="1.6"/><path d="M4.5 17l5-5 3.5 3.5 3-3 3.5 3.5"/>',
  rect: '<rect x="4" y="7" width="16" height="10" rx="1"/>',
  ellipse: '<circle cx="12" cy="12" r="8"/>',
  line: '<path d="M5 19L19 5"/>',
  video:
    '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M10 9.5v5l4.5-2.5z" fill="currentColor" stroke="none"/>',
  'drop-image':
    '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>',
  'drop-video': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5l5 2.5-5 2.5z"/>',
}
