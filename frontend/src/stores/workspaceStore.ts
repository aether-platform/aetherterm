import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAetherTerminalStore } from './aetherTerminalStore'
import { WorkspaceSessionManager } from './workspace/sessionManager'
import { getWorkspaceCrossTabSync, type WorkspaceSyncMessage } from './workspace/crossTabSync'
import { workspaceEventBus } from './workspace/workspaceEventBus'
import type { WorkspaceState, TerminalTabWithPanes, TerminalPane } from './workspace/workspaceTypes'

// Re-export types for other modules
export type { WorkspaceState, TerminalTabWithPanes, TerminalPane }

export const useWorkspaceStore = defineStore('workspace', () => {
  // State
  const currentWorkspace = ref<WorkspaceState | null>(null)
  const workspaces = ref<WorkspaceState[]>([])
  const isResuming = ref(false)
  const resumeError = ref<string | null>(null)
  const serverSyncEnabled = ref(true) // Always true for server-only
  const lastServerSync = ref<Date | null>(null)

  // Store references
  const terminalService = useAetherTerminalStore()
  
  // Cross-tab sync
  const crossTabSync = getWorkspaceCrossTabSync()

  // Getters
  const hasCurrentWorkspace = computed(() => !!currentWorkspace.value)
  const workspaceCount = computed(() => workspaces.value.length)

  // Server communication helpers
  const getSocket = () => {
    const socket = terminalService.getSocket()
    if (!socket || !socket.connected) {
      throw new Error('No server connection')
    }
    return socket
  }

  // Generic socket operation factory to reduce code duplication
  const createSocketOperation = <T>(
    emitEvent: string,
    successEvent: string,
    errorEvent: string = 'workspace_error',
    timeout: number = 5000,
    logPrefix: string = 'WORKSPACE'
  ) => {
    return async (data: any): Promise<T | null> => {
      try {
        const socket = getSocket()
        
        return new Promise((resolve) => {
          let timeoutHandle: number
          
          const cleanup = () => {
            socket.off(successEvent, handleSuccess)
            socket.off(errorEvent, handleError)
            if (timeoutHandle) clearTimeout(timeoutHandle)
          }
          
          const handleSuccess = (response: any) => {
            cleanup()
            if (response.success) {
              console.log(`📋 ${logPrefix}: ${successEvent} success`)
              resolve(response as T)
            } else {
              resolve(null)
            }
          }
          
          const handleError = (error: any) => {
            cleanup()
            console.error(`📋 ${logPrefix}: ${emitEvent} error:`, error.error || error)
            resolve(null)
          }
          
          socket.on(successEvent, handleSuccess)
          socket.on(errorEvent, handleError)
          socket.emit(emitEvent, data)
          
          timeoutHandle = setTimeout(() => {
            cleanup()
            console.warn(`📋 ${logPrefix}: ${emitEvent} timeout`)
            resolve(null)
          }, timeout) as unknown as number
        })
      } catch (error) {
        console.error(`📋 ${logPrefix}: Error in ${emitEvent}:`, error)
        return null
      }
    }
  }

  // Server-side workspace operations using the factory pattern
  const workspaceCreateOp = createSocketOperation<{ success: boolean; workspace: any }>(
    'workspace_create',
    'workspace_created'
  )
  
  
  const getGlobalWorkspaceOp = createSocketOperation<{ success: boolean; workspace: any }>(
    'workspace_get',
    'workspace_data'
  )
  
  const tabCreateOp = createSocketOperation<{ success: boolean; tab: any }>(
    'tab_create',
    'tab_created'
  )
  
  const workspaceUpdateOp = createSocketOperation<{ success: boolean; workspace: any }>(
    'workspace_update',
    'workspace_updated'
  )

  const createWorkspaceOnServer = async (name?: string): Promise<WorkspaceState | null> => {
    const result = await workspaceCreateOp({
      name: name || `Workspace ${workspaces.value.length + 1}`
    })
    
    if (result?.workspace) {
      const workspace: WorkspaceState = {
        ...result.workspace,
        lastAccessed: new Date(result.workspace.lastAccessed),
        tabs: []
      }
      console.log('📋 WORKSPACE: Created on server:', workspace.id)
      return workspace
    }
    return null
  }

  const createTabOnServer = async (
    workspaceId: string, 
    title: string, 
    type: 'terminal' | 'ai-agent' | 'log-monitor' = 'terminal',
    subType?: string
  ): Promise<TerminalTabWithPanes | null> => {
    const result = await tabCreateOp({
      workspaceId,
      title,
      type,
      subType
    })
    
    if (result?.tab) {
      const tab: TerminalTabWithPanes = {
        ...result.tab,
        lastActivity: new Date(result.tab.lastActivity),
        panes: result.tab.panes || []
      }
      console.log('📋 WORKSPACE: Created tab on server:', tab.id)
      return tab
    }
    return null
  }

  
  const loadGlobalWorkspace = async (): Promise<WorkspaceState | null> => {
    const result = await getGlobalWorkspaceOp({})
    
    if (result?.workspace) {
      const workspace: WorkspaceState = {
        ...result.workspace,
        lastAccessed: new Date(result.workspace.lastAccessed),
        tabs: result.workspace.tabs.map((tab: any) => ({
          ...tab,
          lastActivity: new Date(tab.lastActivity)
        }))
      }
      console.log('📋 WORKSPACE: Loaded global workspace from server:', workspace)
      return workspace
    }
    return null
  }

  // Actions
  const loadGlobalWorkspaceAsDefault = async (): Promise<WorkspaceState | null> => {
    console.log('📋 WORKSPACE: Loading global shared workspace')
    
    const workspace = await loadGlobalWorkspace()
    if (workspace) {
      workspaces.value = [workspace]
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
      
      // Resume sessions
      const socket = terminalService.getSocket()
      if (socket && socket.connected) {
        const result = await WorkspaceSessionManager.resumeWorkspace(targetWorkspace, socket)
        if (result.success) {
          console.log('📋 WORKSPACE: Resumed workspace successfully')
          console.log('📋 WORKSPACE: Current workspace after resume:', currentWorkspace.value)
          console.log('📋 WORKSPACE: Current workspace tabs after resume:', currentWorkspace.value?.tabs)
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

  const saveCurrentWorkspace = async (): Promise<boolean> => {
    if (!currentWorkspace.value) return false
    
    try {
      const result = await workspaceUpdateOp({
        workspaceId: currentWorkspace.value.id,
        workspaceData: {
          name: currentWorkspace.value.name,
          tabs: currentWorkspace.value.tabs,
          activeTabId: currentWorkspace.value.activeTabId,
          layout: currentWorkspace.value.layout
        }
      })
      
      if (result?.success) {
        console.log('📋 WORKSPACE: Saved workspace successfully')
        return true
      }
      return false
    } catch (error) {
      console.error('📋 WORKSPACE: Error saving workspace:', error)
      return false
    }
  }

  const initializeGlobalWorkspace = async () => {
    console.log('📋 WORKSPACE: Initializing global workspace...')
    
    // Load the global workspace
    const workspace = await loadGlobalWorkspaceAsDefault()
    if (!workspace) {
      console.error('📋 WORKSPACE: Failed to load global workspace')
      return
    }

    // If no tabs exist, create default terminal tab
    if (workspace.tabs.length === 0) {
      const tab = await createTabOnServer(workspace.id, 'Terminal 1', 'terminal', 'pure')
      if (tab) {
        workspace.tabs.push(tab)
        console.log('📋 WORKSPACE: Created default terminal tab')
      }
    }
  }

  const initializeWorkspace = async () => {
    console.log('📋 WORKSPACE: Initializing workspace system (server-only)...')
    
    // Wait for connection if needed
    let retries = 0
    while (retries < 10) {
      const socket = terminalService.getSocket()
      if (socket && socket.connected) {
        console.log('📋 WORKSPACE: Socket connected, proceeding with initialization')
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
        workspaces.value = [globalWorkspace]
        
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
    
    // Set up cross-tab sync listener (for session coordination only)
    crossTabSync.addListener('workspace-store', handleCrossTabSync)
    
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
      
      // Save the updated workspace to server immediately
      try {
        const saved = await saveCurrentWorkspace()
        if (saved) {
          console.log('📋 WORKSPACE: Saved workspace after tab creation')
        } else {
          console.error('📋 WORKSPACE: Failed to save workspace after tab creation')
        }
      } catch (error) {
        console.error('📋 WORKSPACE: Error saving workspace:', error)
      }
      
      // Emit event for tab creation
      workspaceEventBus.emitTabCreated(tab)
      
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

  // Handle cross-tab sync messages
  const handleCrossTabSync = (message: WorkspaceSyncMessage) => {
    switch (message.type) {
      case 'workspace_update':
        // Refresh from server instead of trusting cross-tab data
        if (message.workspace && currentWorkspace.value?.id === message.workspace.id) {
          loadGlobalWorkspace().then(workspace => {
            if (workspace) {
              currentWorkspace.value = workspace
              console.log('📡 CROSS-TAB: Refreshed workspace from server')
            }
          })
        }
        break
        
      case 'workspace_switch':
        if (message.workspaceId && message.workspaceId !== currentWorkspace.value?.id) {
          console.log('📡 CROSS-TAB: Another tab switched to workspace:', message.workspaceId)
        }
        break
    }
  }

  return {
    // State
    currentWorkspace,
    workspaces,
    isResuming,
    resumeError,
    serverSyncEnabled,
    lastServerSync,

    // Getters
    hasCurrentWorkspace,
    workspaceCount,

    // Actions
    loadGlobalWorkspaceAsDefault,
    resumeWorkspace,
    initializeGlobalWorkspace,
    initializeWorkspace,
    createTab,
    createPane,
    saveCurrentWorkspace
  }
})