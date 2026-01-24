/**
 * Terminal session management composable
 */

import { ref, computed, onBeforeUnmount } from 'vue'
import type { Terminal } from '@xterm/xterm'
import { useAetherTerminalStore } from '../../../stores/aetherTerminalStore'
import { useTerminalTabStore } from '../../../stores/terminalTabStore'
import { useTerminalPaneStore } from '../../../stores/terminalPaneStore'
import { hasRole, isAnonymousUser, canAnonymousAccess } from '@/utils/auth'
import { useTerminalPermissionsStore } from '../../../stores/terminalPermissionsStore'

export function useTerminalSession(props: { id: string; mode: 'tab' | 'pane'; subType?: string }) {
  // Store references
  const aetherStore = useAetherTerminalStore()
  const tabStore = useTerminalTabStore()
  const paneStore = useTerminalPaneStore()
  const permissionsStore = useTerminalPermissionsStore()

  // State
  const isConnecting = ref(false)
  const isTerminalClosed = ref(false)
  const currentSessionId = ref<string | null>(null)

  // Computed properties
  const terminalElementId = computed(() => {
    return props.mode === 'tab' 
      ? `terminal-tab-${props.id}` 
      : `terminal-pane-${props.id}`
  })

  const currentTab = computed(() => {
    return props.mode === 'tab' 
      ? tabStore.getTabById(props.id)
      : paneStore.getPaneById(props.id)?.tab
  })

  const currentPane = computed(() => {
    return props.mode === 'pane' 
      ? paneStore.getPaneById(props.id)
      : null
  })

  const sessionId = computed(() => {
    if (props.mode === 'tab') {
      return tabStore.getTabById(props.id)?.sessionId
    } else {
      return paneStore.getPaneById(props.id)?.sessionId
    }
  })

  const isAccessDenied = computed(() => {
    if (canAnonymousAccess()) return false
    if (isAnonymousUser() && !hasRole(['Viewer', 'User'])) {
      return true
    }
    return false
  })

  // Session management methods
  const initializeSession = async (terminal: Terminal) => {
    if (isAccessDenied.value) {
      console.warn('Access denied for anonymous user outside debug mode')
      return
    }

    if (!aetherStore.socket?.connected) {
      console.warn('Socket not connected, retrying...')
      await new Promise(resolve => setTimeout(resolve, 1000))
      if (!aetherStore.socket?.connected) {
        console.error('Failed to connect to socket')
        return
      }
    }

    isConnecting.value = true

    try {
      const sessionData = {
        sessionId: sessionId.value,
        tabId: props.mode === 'tab' ? props.id : currentPane.value?.tab?.id,
        subType: props.subType || 'pure',
        cols: terminal.cols,
        rows: terminal.rows,
        user: '',
        path: ''
      }

      if (sessionId.value && sessionId.value in aetherStore.activeSessions) {
        console.log(`Resuming existing session: ${sessionId.value}`)
        aetherStore.socket.emit('resume_terminal', sessionData)
      } else {
        console.log(`Creating new terminal session`)
        aetherStore.socket.emit('create_terminal', sessionData)
      }

      currentSessionId.value = sessionId.value
    } catch (error) {
      console.error('Error initializing terminal session:', error)
      isConnecting.value = false
    }
  }

  const closeSession = async () => {
    if (currentSessionId.value) {
      try {
        aetherStore.socket?.emit('session_cleanup', {
          sessionId: currentSessionId.value
        })
        
        if (props.mode === 'tab') {
          tabStore.clearSessionId(props.id)
        } else if (props.mode === 'pane') {
          paneStore.clearSessionId(props.id)
        }
        
        currentSessionId.value = null
      } catch (error) {
        console.error('Error closing session:', error)
      }
    }
  }

  const restartSession = async (terminal: Terminal) => {
    await closeSession()
    isTerminalClosed.value = false
    await initializeSession(terminal)
  }

  // Event handlers
  const handleTerminalReady = (data: any) => {
    isConnecting.value = false
    console.log('Terminal ready:', data)
    
    if (data.session) {
      currentSessionId.value = data.session
      
      if (props.mode === 'tab') {
        tabStore.updateSessionId(props.id, data.session)
      } else if (props.mode === 'pane') {
        paneStore.updateSessionId(props.id, data.session)
      }
    }
  }

  const handleTerminalClosed = () => {
    isTerminalClosed.value = true
    console.log('Terminal session closed')
  }

  const handleTerminalError = (error: any) => {
    console.error('Terminal error:', error)
    isConnecting.value = false
  }

  // Cleanup
  onBeforeUnmount(() => {
    // Note: Don't automatically close session on unmount
    // as the terminal might be resuming in another component
  })

  return {
    // State
    isConnecting,
    isTerminalClosed,
    isAccessDenied,
    currentSessionId,
    
    // Computed
    terminalElementId,
    currentTab,
    currentPane,
    sessionId,
    
    // Methods
    initializeSession,
    closeSession,
    restartSession,
    handleTerminalReady,
    handleTerminalClosed,
    handleTerminalError,
  }
}