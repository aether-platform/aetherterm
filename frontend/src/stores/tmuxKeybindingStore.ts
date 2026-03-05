/**
 * Keybinding store for tmux-style prefix key state machine.
 *
 * State machine:
 *   IDLE → (Ctrl+B) → PREFIX_ACTIVE → (next key) → action → IDLE
 *                                    → (:) → COMMAND_LINE → (Enter) → IDLE
 *                                    → (2s timeout) → IDLE
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

type KeyState = 'idle' | 'prefix'

export interface KeyAction {
  type: string
  index?: number
}

export const useTmuxKeybindingStore = defineStore('tmuxKeybinding', () => {
  const state = ref<KeyState>('idle')
  const isPrefixActive = ref(false)
  const showPaneNumbers = ref(false)
  const showCommandLine = ref(false)

  let prefixTimeout: ReturnType<typeof setTimeout> | null = null

  function resetState() {
    state.value = 'idle'
    isPrefixActive.value = false
    if (prefixTimeout) {
      clearTimeout(prefixTimeout)
      prefixTimeout = null
    }
  }

  function handleKey(e: KeyboardEvent): KeyAction | null {
    // Global shortcut: Ctrl+Shift+M toggles interaction mode (any state)
    if (e.ctrlKey && e.shiftKey && e.key === 'M') {
      return { type: 'toggle_mode' }
    }

    // Ctrl+B: enter prefix mode
    if (state.value === 'idle') {
      if (e.ctrlKey && e.key === 'b') {
        state.value = 'prefix'
        isPrefixActive.value = true

        // Auto-timeout after 2 seconds
        prefixTimeout = setTimeout(resetState, 2000)
        return null // Consume the event but no action yet
      }
      return null // Not in prefix mode, let the event pass through
    }

    // In prefix mode: interpret the next key
    if (state.value === 'prefix') {
      resetState()

      // Ctrl+B Ctrl+B: send literal Ctrl+B
      if (e.ctrlKey && e.key === 'b') {
        return { type: 'literal_ctrlb' }
      }

      // Pane splits
      if (e.key === '%') return { type: 'split_v' }
      if (e.key === '"') return { type: 'split_h' }

      // Pane operations
      if (e.key === 'x') return { type: 'close_pane' }
      if (e.key === 'o') return { type: 'next_pane' }
      if (e.key === 'z') return { type: 'zoom' }
      if (e.key === 'q') return { type: 'show_pane_numbers' }

      // Arrow keys: pane focus
      if (e.key === 'ArrowUp') {
        if (e.ctrlKey) return { type: 'resize_up' }
        return { type: 'focus_up' }
      }
      if (e.key === 'ArrowDown') {
        if (e.ctrlKey) return { type: 'resize_down' }
        return { type: 'focus_down' }
      }
      if (e.key === 'ArrowLeft') {
        if (e.ctrlKey) return { type: 'resize_left' }
        return { type: 'focus_left' }
      }
      if (e.key === 'ArrowRight') {
        if (e.ctrlKey) return { type: 'resize_right' }
        return { type: 'focus_right' }
      }

      // Window operations
      if (e.key === 'c') return { type: 'new_window' }
      if (e.key === 'n') return { type: 'next_window' }
      if (e.key === 'p') return { type: 'prev_window' }
      if (e.key === ',') return { type: 'rename_window' }
      if (e.key === '$') return { type: 'rename_session' }

      // Window number selection (0-9)
      if (e.key >= '0' && e.key <= '9') {
        return { type: 'select_window', index: parseInt(e.key) }
      }

      // Session operations
      if (e.key === 'd') return { type: 'detach' }
      if (e.key === 's') return { type: 'session_list' }
      if (e.key === 'w') return { type: 'window_list' }

      // Sidebar / mode
      if (e.key === '\\') return { type: 'toggle_sidebar' }
      if (e.key === 'a') return { type: 'show_agents' }
      if (e.key === 't') return { type: 'show_tasks' }

      // Copy mode
      if (e.key === '[') return { type: 'copy_mode' }

      // Command line
      if (e.key === ':') {
        showCommandLine.value = true
        return { type: 'command_line' }
      }

      // Unknown key in prefix mode — ignore
      return null
    }

    return null
  }

  return {
    state,
    isPrefixActive,
    showPaneNumbers,
    showCommandLine,
    handleKey,
    resetState,
  }
})
