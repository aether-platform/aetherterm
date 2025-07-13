import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAetherTerminalStore } from './aetherTerminalStore'
import { WorkspaceSessionManager } from './workspace/sessionManager'
import { WorkspacePersistenceManager } from './workspace/persistenceManager'
import type { WorkspaceState, TerminalTabWithPanes, TerminalPane } from './workspace/workspaceTypes'

// Re-export types for other modules
export type { WorkspaceState, TerminalTabWithPanes, TerminalPane }

export const useWorkspaceStore = defineStore('workspace', () => {
  // State - 最小限
  const currentWorkspace = ref<WorkspaceState | null>(null)
  const isResuming = ref(false)
  const resumeError = ref<string | null>(null)

  // Store references
  const terminalService = useAetherTerminalStore()

  // Getters
  const hasCurrentWorkspace = computed(() => !!currentWorkspace.value)

  // Server communication helpers
  const getSocket = () => {
    const socket = terminalService.getSocket()
    if (!socket || !socket.connected) {
      throw new Error('No server connection')
    }
    return socket
  }

  // Simplified direct socket operations
  const socketRequest = async (emitEvent: string, successEvent: string, data: Record<string, unknown>) => {
    try {
      const socket = getSocket()
      // console.log(`📨 SOCKET_REQUEST: Emitting ${emitEvent} with data:`, data)
      return new Promise<WorkspaceState | TerminalTabWithPanes | null>((resolve) => {
        const cleanup = () => {
          socket.off(successEvent, handleSuccess)
          socket.off('workspace_error', handleError)
        }
        
        const handleSuccess = (response: { success?: boolean; [key: string]: unknown }) => {
          // console.log(`✅ SOCKET_REQUEST: Received ${successEvent}:`, response)
          cleanup()
          resolve(response.success ? (response as any) : null)
        }
        
        const handleError = (error: any) => {
          console.error(`❌ SOCKET_REQUEST: Error on ${emitEvent}:`, error)
          cleanup()
          resolve(null)
        }
        
        socket.on(successEvent, handleSuccess)
        socket.on('workspace_error', handleError)
        socket.emit(emitEvent, data)
        
        setTimeout(() => {
          // console.warn(`⏱️ SOCKET_REQUEST: Timeout waiting for ${successEvent}`)
          cleanup()
          resolve(null)
        }, 5000)
      })
    } catch (error) {
      console.error(`❌ SOCKET_REQUEST: Exception:`, error)
      return null
    }
  }

  const createTabOnServer = async (
    workspaceId: string, 
    title: string, 
    type: 'terminal' | 'ai-agent' | 'log-monitor' = 'terminal',
    subType?: string
  ): Promise<TerminalTabWithPanes | null> => {
    const result = await socketRequest('tab_create', 'tab_created', {
      title, type, subType  // Remove workspaceId - global workspace doesn't need it
    }) as any
    
    if (result?.tab) {
      return {
        ...result.tab,
        lastActivity: new Date(result.tab.lastActivity),
        panes: result.tab.panes || []
      }
    }
    return null
  }

  const loadGlobalWorkspace = async (): Promise<WorkspaceState | null> => {
    // console.log('📋 WORKSPACE: Requesting global workspace from server...')
    const result = await socketRequest('workspace_get', 'workspace_data', {}) as any
    
    // console.log('📋 WORKSPACE: Server response:', result)
    
    if (result?.workspace) {
      const workspace = {
        ...result.workspace,
        lastAccessed: new Date(result.workspace.lastAccessed),
        tabs: result.workspace.tabs.map((tab: any) => ({
          ...tab,
          lastActivity: new Date(tab.lastActivity)
        })),
        isActive: true
      }
      console.log('📋 WORKSPACE: Loaded workspace:', workspace)
      
      // Debug: Log session IDs from server
      workspace.tabs.forEach((tab: any) => {
        console.log(`📋 WORKSPACE: Tab ${tab.id} has ${tab.panes?.length || 0} panes`)
        tab.panes?.forEach((pane: any) => {
          console.log(`📋 WORKSPACE: Pane ${pane.id} has sessionId: ${pane.sessionId}`)
        })
      })
      return workspace
    }
    
    console.log('📋 WORKSPACE: No workspace returned from server')
    return null
  }

  // Actions
  const loadGlobalWorkspaceAsDefault = async (): Promise<WorkspaceState | null> => {
    console.log('📋 WORKSPACE: Loading global shared workspace')
    
    const workspace = await loadGlobalWorkspace()
    if (workspace) {
      // Set current workspace to the loaded global workspace
      currentWorkspace.value = workspace
      console.log('📋 WORKSPACE: Set global workspace as current:', workspace)
      return workspace
    }
    return null
  }


  const resumeWorkspace = async (workspaceId?: string): Promise<boolean> => {
    try {
      isResuming.value = true
      resumeError.value = null

      let targetWorkspace: WorkspaceState | null = null

      // Load the global workspace directly
      targetWorkspace = await loadGlobalWorkspace()

      if (!targetWorkspace) {
        await initializeGlobalWorkspace()
        return true
      }

      // Update current workspace
      console.log('📋 WORKSPACE: Setting current workspace:', targetWorkspace)
      console.log('📋 WORKSPACE: Target workspace tabs:', targetWorkspace.tabs)
      currentWorkspace.value = targetWorkspace
      targetWorkspace.isActive = true
      
      // CRITICAL: Populate pane store with workspace data BEFORE resuming sessions
      const { useTerminalPaneStore } = await import('./terminalPaneStore')
      const paneStore = useTerminalPaneStore()
      
      // Clear existing panes and replace with server panes
      paneStore.panes.splice(0, paneStore.panes.length)
      
      targetWorkspace.tabs.forEach(tab => {
        tab.panes?.forEach(pane => {
          console.log(`📋 WORKSPACE: Adding server pane ${pane.id} to store with sessionId: ${pane.sessionId}`)
          paneStore.panes.push({
            id: pane.id, // Use server pane ID
            title: pane.title || 'Terminal',
            type: pane.type || 'terminal',
            subType: pane.subType,
            sessionId: pane.sessionId,
            isActive: pane.isActive || false,
            lastActivity: new Date(),
            status: pane.sessionId ? 'connecting' : 'disconnected',
            position: pane.position || { x: 0, y: 0, width: 100, height: 100 },
            tabId: tab.id
          })
        })
      })
      
      // Resume sessions
      const socket = terminalService.getSocket()
      if (socket && socket.connected) {
        const result = await WorkspaceSessionManager.resumeWorkspace(targetWorkspace, socket as any)
        if (result.success) {
          console.log('📋 WORKSPACE: Resumed workspace successfully')
          console.log('📋 WORKSPACE: Current workspace after resume:', currentWorkspace.value)
          console.log('📋 WORKSPACE: Current workspace tabs after resume:', currentWorkspace.value?.tabs)
          
          // Persist terminal sessions after successful resume
          if (currentWorkspace.value) {
            WorkspacePersistenceManager.persistTerminalSessions(currentWorkspace.value)
          }
          
          isResuming.value = false
          return true
        } else {
          resumeError.value = result.error || 'Failed to resume workspace sessions'
        }
      }

      isResuming.value = false
      return true
    } catch (error) {
      console.error('📋 WORKSPACE: Failed to resume workspace:', error)
      resumeError.value = error instanceof Error ? error.message : 'Unknown error'
      isResuming.value = false
      return false
    }
  }

  const initializeGlobalWorkspace = async () => {
    console.log('📋 WORKSPACE: Initializing global workspace...')
    
    // Create a default workspace structure locally
    const defaultWorkspace: WorkspaceState = {
      id: 'global_workspace',
      name: 'Shared Workspace',
      lastAccessed: new Date(),
      tabs: [],
      activeTabId: undefined,
      isActive: true,
      layout: {
        type: 'default',
        configuration: {}
      }
    }
    
    // Set as current workspace immediately
    currentWorkspace.value = defaultWorkspace
    console.log('📋 WORKSPACE: Set default workspace as current')

    // Try to load from server
    const serverWorkspace = await loadGlobalWorkspace()
    if (serverWorkspace) {
      currentWorkspace.value = serverWorkspace
      console.log('📋 WORKSPACE: Updated with server workspace')
    }

    // If no tabs exist, create default terminal tab
    if (currentWorkspace.value.tabs.length === 0) {
      const tab = await createTabOnServer(currentWorkspace.value.id, 'Terminal 1', 'terminal', 'pure')
      if (tab) {
        currentWorkspace.value.tabs.push(tab)
        console.log('📋 WORKSPACE: Created default terminal tab')
      }
    }
  }

  // Track initialization state to prevent duplicate calls
  let isInitializing = false
  let initializationPromise: Promise<void> | null = null

  const initializeWorkspace = async () => {
    // If already initializing, return the existing promise
    if (isInitializing && initializationPromise) {
      console.log('📋 WORKSPACE: Already initializing, returning existing promise')
      return initializationPromise
    }
    
    // If already initialized and has workspace, just return
    if (currentWorkspace.value) {
      console.log('📋 WORKSPACE: Already initialized with workspace')
      return
    }
    
    isInitializing = true
    initializationPromise = doInitializeWorkspace()
    
    try {
      await initializationPromise
    } finally {
      isInitializing = false
      initializationPromise = null
    }
  }
  
  const doInitializeWorkspace = async () => {
    console.log('📋 WORKSPACE: Initializing workspace system (server-only)...')
    
    // Wait for connection if needed
    let retries = 0
    while (retries < 10) {
      const socket = terminalService.getSocket()
      if (socket && socket.connected) {
        break
      }
      console.log(`📋 WORKSPACE: Waiting for connection... (retry ${retries + 1}/10)`)
      await new Promise(resolve => setTimeout(resolve, 500))
      retries++
    }
    
    const socket = terminalService.getSocket()
    if (!socket || !socket.connected) {
      console.log('📋 WORKSPACE: Failed to establish connection after retries')
      return
    }
    
    // Load global workspace from server
    try {
      const globalWorkspace = await loadGlobalWorkspace()
      console.log('📋 WORKSPACE: Loaded global workspace from server:', globalWorkspace)
      
      if (globalWorkspace) {
        // Set current workspace to the loaded global workspace
        
        console.log('📋 WORKSPACE: Global workspace tabs:', globalWorkspace.tabs)
        
        const resumed = await resumeWorkspace(globalWorkspace.id)
        if (!resumed) {
          // If resume failed, initialize global workspace
          await initializeGlobalWorkspace()
        }
      } else {
        // No global workspace found, initialize it
        console.log('📋 WORKSPACE: No global workspace found, initializing')
        await initializeGlobalWorkspace()
      }
    } catch (error) {
      console.error('📋 WORKSPACE: Failed to load global workspace:', error)
      await initializeGlobalWorkspace()
    }
    
    // Cross-tab sync removed - server handles all sync
    
    console.log('📋 WORKSPACE: Workspace system initialized (server-only)')
  }

  // Public tab/pane creation methods that use server
  const createTab = async (
    type: 'terminal' | 'ai-agent' | 'log-monitor' = 'terminal',
    options?: { name?: string; terminalId?: string; subType?: string }
  ): Promise<TerminalTabWithPanes | null> => {
    if (!currentWorkspace.value) {
      console.error('📋 WORKSPACE: No active workspace to add tab')
      return null
    }

    const title = options?.name || `${type === 'terminal' ? 'Terminal' : type} ${currentWorkspace.value.tabs.length + 1}`
    const tab = await createTabOnServer(
      currentWorkspace.value.id,
      title,
      type,
      options?.subType
    )

    if (tab) {
      currentWorkspace.value.tabs.push(tab)
      
      // Deactivate other tabs
      currentWorkspace.value.tabs.forEach(t => {
        t.isActive = t.id === tab.id
      })
      
      currentWorkspace.value.activeTabId = tab.id
      
      // Persist terminal sessions for recovery
      WorkspacePersistenceManager.persistTerminalSessions(currentWorkspace.value)
      
      
      console.log('📋 WORKSPACE: Created tab:', tab)
    }

    return tab
  }

  const createPane = async (
    tabId: string,
    type: 'terminal' | 'ai-agent' | 'log-monitor' = 'terminal',
    options?: { terminalId?: string; subType?: string }
  ): Promise<TerminalPane | null> => {
    console.warn('📋 WORKSPACE: createPane not yet implemented for server-side architecture')
    // TODO: Implement server-side pane creation
    return null
  }

  return {
    // State - 最小限
    currentWorkspace,
    isResuming,
    resumeError,

    // Getters
    hasCurrentWorkspace,

    // Actions - 最小限
    initializeWorkspace,
    createTab,
    
    // Backward compatibility (will be removed)
    createTabWithPane: createTab,
    createSpecialTab: createTab,
  }
})