/**
 * Shared launcher for the unified scene editor from the dashboard quick
 * settings panels: owns the modal open/id refs and guards against a
 * missing active scene with an error toast. `section` selects the
 * editor tab opened first and is also used in the guard message.
 */
import { ref, type Ref } from 'vue'
import { useDisplayStore } from './useDisplayStore'

export interface SceneEditorLauncher {
  editorOpen: Ref<boolean>
  editSceneId: Ref<string | null>
  openDesigner: () => void
}

export function useSceneEditorLauncher(section: 'screen' | 'argb'): SceneEditorLauncher {
  const { state, showError } = useDisplayStore()
  const editorOpen = ref(false)
  const editSceneId = ref<string | null>(null)

  function openDesigner(): void {
    const sceneId = state.scene.scene_id
    if (sceneId === null) {
      showError(
        `No active scene — apply or create one in the Scenes panel first; the ${section} layout lives in a scene file`,
      )
      return
    }
    editSceneId.value = sceneId
    editorOpen.value = true
  }

  return { editorOpen, editSceneId, openDesigner }
}
