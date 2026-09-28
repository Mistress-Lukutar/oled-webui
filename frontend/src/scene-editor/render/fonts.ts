/**
 * Font loading for the editor canvas: scene asset fonts are fetched via
 * the asset endpoint and registered through the FontFace API, keyed by
 * the asset base name so `style.family: "assets/foo.ttf"` resolves.
 */

import { API } from '../../api'

const pending = new Map<string, Promise<string | null>>()
const loaded = new Set<string>()

function familyName(basename: string): string {
  // Dots are invalid in unquoted CSS identifiers, so the canvas font
  // shorthand `48px scene-font-X.ttf` would silently fail to parse.
  // Keep the family a safe identifier and hash the original name to
  // stay unique across extensions ("A.ttf" vs "A.otf").
  let hash = 0
  for (let i = 0; i < basename.length; i += 1) {
    hash = (hash * 31 + basename.charCodeAt(i)) | 0
  }
  const clean = basename.replace(/[^a-zA-Z0-9_-]/g, '_')
  return `scene-font-${clean}-${(hash >>> 0).toString(36)}`
}

/**
 * Ensure a font asset is registered for canvas use.
 *
 * `fonts/<name>` families resolve against the shared font library
 * endpoint; everything else is fetched as a scene asset.
 *
 * @param sceneId Scene id for the asset endpoint.
 * @param family  Font path as written in the YAML (relative to scene dir).
 * @returns CSS font-family to use in canvas, or null when unavailable.
 */
export function ensureFont(sceneId: string, family: string): Promise<string | null> {
  const basename = family.replaceAll('\\', '/').split('/').pop() ?? ''
  if (basename === '') return Promise.resolve(null)
  const key = `${sceneId}:${basename}`
  if (loaded.has(key)) return Promise.resolve(familyName(basename))
  const cached = pending.get(key)
  if (cached) return cached
  const promise = (async () => {
    try {
      const url = family.startsWith('fonts/')
        ? API.libraryFontUrl(basename)
        : API.sceneAssetUrl(sceneId, basename)
      const response = await fetch(url)
      if (!response.ok) return null
      const buffer = await response.arrayBuffer()
      const face = new FontFace(familyName(basename), buffer)
      await face.load()
      document.fonts.add(face)
      loaded.add(key)
      return familyName(basename)
    } catch {
      return null
    }
  })()
  pending.set(key, promise)
  return promise
}

/** Synchronously return the registered family, if the font is loaded. */
export function loadedFontFamily(sceneId: string, family: string): string | null {
  const basename = family.replaceAll('\\', '/').split('/').pop() ?? ''
  if (basename === '') return null
  return loaded.has(`${sceneId}:${basename}`) ? familyName(basename) : null
}
