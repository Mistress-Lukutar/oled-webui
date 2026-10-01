<script setup lang="ts">
/**
 * Shared modal shell: a fixed overlay with a centered card. The card
 * header row comes through the `header` slot, everything else through
 * the default slot. Backdrop click (and optionally Escape) request a
 * close; a dirty-guard text turns those requests into a confirm dialog.
 * Parents keep their own toolbar/body/footer styles — this component
 * only owns the overlay, the card chrome and the close plumbing.
 */
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { isTypingTarget } from '../../canvas/shortcuts'

const props = withDefaults(
  defineProps<{
    /** Card width, e.g. 'min(640px, 90vw)'. */
    width?: string
    /** Fixed card height, e.g. 'min(640px, 88vh)'. */
    height?: string
    /** Height cap without fixing the height. */
    maxHeight?: string
    /** Pin the card to the overlay edges (e.g. '2vh 2vw') instead of sizing it. */
    inset?: string
    /** Overlay z-index; nested modals stack by increasing it. */
    zIndex?: number
    /** Close when the backdrop is clicked (set false for editors with a canvas). */
    backdropClose?: boolean
    /** Close on Escape (disable when the content handles Escape itself). */
    escape?: boolean
    /** Ask before backdrop/Esc close (unsaved changes). */
    confirmClose?: string
  }>(),
  {
    width: undefined,
    height: undefined,
    maxHeight: undefined,
    inset: undefined,
    zIndex: 50,
    backdropClose: true,
    escape: false,
    confirmClose: '',
  },
)

const emit = defineEmits<{ close: [] }>()

function requestClose(): void {
  if (props.confirmClose !== '' && !window.confirm(props.confirmClose)) return
  emit('close')
}

function onBackdropClick(): void {
  if (props.backdropClose) requestClose()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || isTypingTarget(event.target)) return
  requestClose()
}

onMounted(() => {
  if (props.escape) window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  if (props.escape) window.removeEventListener('keydown', onKeydown)
})

const cardStyle = computed(() =>
  props.inset !== undefined
    ? { position: 'absolute' as const, inset: props.inset }
    : {
        width: props.width,
        height: props.height,
        maxHeight: props.maxHeight ?? (props.height === undefined ? '82vh' : undefined),
      },
)
</script>

<template>
  <Teleport to="body">
    <div class="app-modal-overlay" :style="{ zIndex }" @click.self="onBackdropClick">
      <div class="app-modal" :style="cardStyle">
        <slot name="header" />
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.app-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
}

.app-modal {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-modal);
}
</style>

<style>
/* Shared card header row for modal shells. */
.app-modal-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex: none;
  flex-wrap: wrap;
}
</style>
