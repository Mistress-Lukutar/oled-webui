/**
 * Viewport composable: zoom/pan for a logical canvas of fixed size.
 * Owns the container/canvas element refs, wheel zoom around the cursor,
 * Space-pan, fit-on-resize and the CSS transform for the canvas holder.
 */

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import { isFormTarget } from './shortcuts'

export interface Viewport {
  container: Ref<HTMLDivElement | null>
  zoom: Ref<number>
  panX: Ref<number>
  panY: Ref<number>
  spaceHeld: Ref<boolean>
  transformStyle: ComputedRef<{ width: string; height: string; transform: string }>
  fit: () => void
  onWheel: (event: WheelEvent) => void
  /** True when the event happened inside this viewport (not in a form). */
  containsTarget: (event: Event) => boolean
  detach: () => void
}

export function useViewport(
  logicalWidth: () => number,
  logicalHeight: () => number,
): Viewport {
  const container = ref<HTMLDivElement | null>(null)
  const zoom = ref(1)
  const panX = ref(0)
  const panY = ref(0)
  const spaceHeld = ref(false)

  function onWheel(event: WheelEvent): void {
    event.preventDefault()
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
    const next = Math.max(0.05, Math.min(12, zoom.value * factor))
    const canvas = container.value?.querySelector('canvas')
    const rect = canvas?.getBoundingClientRect()
    if (rect) {
      const cx = event.clientX - (rect.left + rect.width / 2)
      const cy = event.clientY - (rect.top + rect.height / 2)
      const scale = next / zoom.value
      panX.value = cx - (cx - panX.value) * scale
      panY.value = cy - (cy - panY.value) * scale
    }
    zoom.value = next
  }

  function fit(): void {
    const box = container.value
    if (box === null) return
    const margin = 32
    const zw = (box.clientWidth - margin) / logicalWidth()
    const zh = (box.clientHeight - margin) / logicalHeight()
    zoom.value = Math.max(0.05, Math.min(zw, zh))
    panX.value = 0
    panY.value = 0
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.code === 'Space' && containsTarget(event)) {
      spaceHeld.value = true
      event.preventDefault()
    }
  }

  function onKeyup(event: KeyboardEvent): void {
    if (event.code === 'Space') spaceHeld.value = false
  }

  function containsTarget(event: Event): boolean {
    return (
      container.value !== null &&
      container.value.contains(event.target as Node) &&
      !isFormTarget(event.target)
    )
  }

  let observer: ResizeObserver | null = null

  onMounted(() => {
    fit()
    requestAnimationFrame(() => fit())
    observer = new ResizeObserver(() => fit())
    if (container.value !== null) observer.observe(container.value)
    window.addEventListener('keydown', onKeydown)
    window.addEventListener('keyup', onKeyup)
  })

  const detach = (): void => {
    observer?.disconnect()
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('keyup', onKeyup)
  }
  onBeforeUnmount(detach)

  watch([logicalWidth, logicalHeight], () => fit())

  const transformStyle = computed(() => ({
    width: `${logicalWidth() * zoom.value}px`,
    height: `${logicalHeight() * zoom.value}px`,
    transform: `translate(${panX.value}px, ${panY.value}px)`,
  }))

  return {
    container,
    zoom,
    panX,
    panY,
    spaceHeld,
    transformStyle,
    fit,
    onWheel,
    containsTarget,
    detach,
  }
}
