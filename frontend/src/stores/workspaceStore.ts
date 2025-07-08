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

  // Server-side workspace operations
  const createWorkspaceOnServer = async (name?: string): Promise<WorkspaceState | null> => {
    try {
      const socket = getSocket()
      
      return new Promise((resolve) => {
        const handleSuccess = (data: any) => {
          socket.off('workspace_created', handleSuccess)
          socket.off('workspace_error', handleError)
          if (data.success && data.workspace) {
            const workspace: WorkspaceState = {
              ...data.workspace,
              lastAccessed: new Date(data.workspace.lastAccessed),
              tabs: []
            }
            console.log('📋 WORKSPACE: Created on server:', workspace.id)
            resolve(workspace)
          } else {
            resolve(null)
          }
        }
        
        const handleError = (data: any) => {
          socket.off('workspace_created', handleSuccess)
          socket.off('workspace_error', handleError)
          console.error('📋 WORKSPACE: Server creation error:', data.error)
          resolve(null)
        }
        
        socket.on('workspace_created', handleSuccess)
        socket.on('workspace_error', handleError)
        
        socket.emit('workspace_create', {
          name: name || `Workspace ${workspaces.value.length + 1}`
        })
        
        setTimeout(() => {
          socket.off('workspace_created', handleSuccess)
          socket.off('workspace_error', handleError)
          resolve(null)
        }, 5000)
      })
    } catch (error) {
      console.error('📋 WORKSPACE: Error creating workspace on server:', error)
      return null
    }
  }

  const createTabOnServer = async (
    workspaceId: string, 
    title: string, 
    type: 'terminal' | 'ai-agent' | 'log-monitor' = 'terminal',
    subType?: string
  ): Promise<TerminalTabWithPanes | null> => {
    try {
      const socket = getSocket()
      
      return new Promise((resolve) => {
        const handleSuccess = (data: any) => {
          socket.off('tab_created', handleSuccess)
          socket.off('workspace_error', handleError)
          if (data.success && data.tab) {
            const tab: TerminalTabWithPanes = {
              ...data.tab,
              lastActivity: new Date(data.tab.lastActivity),
              panes: data.tab.panes || []
            }
            console.log('📋 WORKSPACE: Created tab on server:', tab.id)
            resolve(tab)
          } else {
            resolve(null)
          }
        }
        
        const handleError = (data: any) => {
          socket.off('tab_created', handleSuccess)
          socket.off('workspace_error', handleError)
          console.error('📋 WORKSPACE: Server tab creation error:', data.error)
          resolve(null)
        }
        
        socket.on('tab_created', handleSuccess)
        socket.on('workspace_error', handleError)
        
        socket.emit('tab_create', {
          workspaceId,
          title,
          type,
          subType
        })
        
        setTimeout(() => {
          socket.off('tab_created', handleSuccess)
          socket.off('workspace_error', handleError)
          resolve(null)
        }, 5000)
      })
    } catch (error) {
      console.error('📋 WORKSPACE: Error creating tab on server:', error)
      return null
    }
  }

  const getWorkspaceFromServer = async (workspaceId: string): Promise<WorkspaceState | null> => {
    try {
      const socket = getSocket()
      
      return new Promise((resolve) => {
        const handleSuccess = (data: any) => {
          socket.off('workspace_data', handleSuccess)
          socket.off('workspace_error', handleError)
          if (data.success && data.workspace) {
            const workspace: WorkspaceState = {
              ...data.workspace,
              lastAccessed: new Date(data.workspace.lastAccessed),
              tabs: data.workspace.tabs.map((tab: any) => ({
                ...tab,
                lastActivity: new Date(tab.lastActivity)
              }))
            }
            console.log('📋 WORKSPACE: Loaded from server:', workspace.id)
            resolve(workspace)
          } else {
            resolve(null)
          }
        }
        
        const handleError = (data: any) => {
          socket.off('workspace_data', handleSuccess)
          socket.off('workspace_error', handleError)
          console.error('📋 WORKSPACE: Server load error:', data.error)
          resolve(null)
        }
        
        socket.on('workspace_data', handleSuccess)
        socket.on('workspace_error', handleError)
        
        socket.emit('workspace_get', { workspaceId })
        
        setTimeout(() => {
          socket.off('workspace_data', handleSuccess)
          socket.off('workspace_error', handleError)
          resolve(null)
        }, 5000)
      })
    } catch (error) {
      console.error('📋 WORKSPACE: Error loading from server:', error)
      return null
    }
  }
  
  const listWorkspacesFromServer = async (): Promise<WorkspaceState[]> => {
    try {
      const socket = getSocket()
      
      return new Promise((resolve) => {
        const handleSuccess = (data: any) => {
          socket.off('workspace_list_data', handleSuccess)
          socket.off('workspace_error', handleError)
          if (data.success && data.workspaces) {
            const workspaces = data.workspaces.map((ws: any) => ({
              ...ws,
              lastAccessed: new Date(ws.lastAccessed),
              tabs: ws.tabs.map((tab: any) => ({
                ...tab,
                lastActivity: new Date(tab.lastActivity)
              }))
            }))
            console.log('📋 WORKSPACE: Listed from server:', workspaces.length, 'workspaces')
            resolve(workspaces)
          } else {
            resolve([])
          }
        }
        
        const handleError = (data: any) => {
          socket.off('workspace_list_data', handleSuccess)
          socket.off('workspace_error', handleError)
          console.error('📋 WORKSPACE: Server list error:', data.error)
          resolve([])
        }
        
        socket.on('workspace_list_data', handleSuccess)
        socket.on('workspace_error', handleError)
        
        socket.emit('workspace_list', {})
        
        setTimeout(() => {
          socket.off('workspace_list_data', handleSuccess)
          socket.off('workspace_error', handleError)
          resolve([])
        }, 5000)
      })
    } catch (error) {
      console.error('📋 WORKSPACE: Error listing from server:', error)
      return []
    }
  }

  // Actions
  const createWorkspace = async (name?: string): Promise<WorkspaceState | null> => {
    const workspace = await createWorkspaceOnServer(name)
    if (workspace) {
      workspaces.value.push(workspace)
      currentWorkspace.value = workspace
      console.log('📋 WORKSPACE: Created workspace:', workspace)
    }
    return workspace
  }

  const switchToWorkspace = async (workspaceId: string) => {
    // First, get the latest workspace state from server
    const workspace = await getWorkspaceFromServer(workspaceId)
    if (workspace) {
      if (currentWorkspace.value) {
        currentWorkspace.value.isActive = false
      }
      
      workspace.isActive = true
      currentWorkspace.value = workspace
      
      // Update local list
      const index = workspaces.value.findIndex(w => w.id === workspaceId)
      if (index >= 0) {
        workspaces.value[index] = workspace
      } else {
        workspaces.value.push(workspace)
      }
      
      // Broadcast switch to other tabs
      crossTabSync.broadcastSwitch(workspaceId)
      
      console.log('📋 WORKSPACE: Switched to workspace:', workspace.name)
    }
  }

  const resumeWorkspace = async (workspaceId?: string): Promise<boolean> => {
    try {
      isResuming.value = true
      resumeError.value = null

      let targetWorkspace: WorkspaceState | null = null

      if (workspaceId) {
        targetWorkspace = await getWorkspaceFromServer(workspaceId)
      } else {
        // Get list from server and find most recent
        const serverWorkspaces = await listWorkspacesFromServer()
        if (serverWorkspaces.length > 0) {
          targetWorkspace = serverWorkspaces
            .filter(w => w.tabs.length > 0)
            .sort((a, b) => b.lastAccessed.getTime() - a.lastAccessed.getTime())[0] || null
        }
      }

      if (!targetWorkspace) {
        await createDefaultWorkspace()
        return true
      }

      // Update current workspace
      currentWorkspace.value = targetWorkspace
      targetWorkspace.isActive = true
      
      // Resume sessions
      const socket = terminalService.getSocket()
      if (socket && socket.connected) {
        const result = await WorkspaceSessionManager.resumeWorkspace(targetWorkspace, socket)
        if (result.success) {
          console.log('📋 WORKSPACE: Resumed workspace successfully')
          workspaceEventBus.emitWorkspaceResumed(targetWorkspace)
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

  const createDefaultWorkspace = async () => {
    console.log('📋 WORKSPACE: Creating default workspace...')
    
    const workspace = await createWorkspace('Default Workspace')
    if (!workspace) {
      console.error('📋 WORKSPACE: Failed to create default workspace')
      return
    }

    // Create default terminal tab on server
    const tab = await createTabOnServer(workspace.id, 'Terminal 1', 'terminal', 'pure')
    if (tab) {
      workspace.tabs.push(tab)
      console.log('📋 WORKSPACE: Created default terminal tab')
    }
  }

  const initializeWorkspace = async () => {
    console.log('📋 WORKSPACE: Initializing workspace system (server-only)...')
    
    // Check connection
    const socket = terminalService.getSocket()
    if (!socket || !socket.connected) {
      console.log('📋 WORKSPACE: No connection - deferring initialization')
      return
    }
    
    // Load workspaces from server only
    try {
      const serverWorkspaces = await listWorkspacesFromServer()
      if (serverWorkspaces.length > 0) {
        workspaces.value = serverWorkspaces
        
        // Resume the most recent workspace
        const mostRecent = serverWorkspaces.sort((a: WorkspaceState, b: WorkspaceState) => 
          b.lastAccessed.getTime() - a.lastAccessed.getTime()
        )[0]
        
        const resumed = await resumeWorkspace(mostRecent.id)
        if (!resumed) {
          // If resume failed, create default workspace
          await createDefaultWorkspace()
        }
      } else {
        // No workspaces on server, create default
        await createDefaultWorkspace()
      }
    } catch (error) {
      console.error('📋 WORKSPACE: Failed to load from server:', error)
      await createDefaultWorkspace()
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
          getWorkspaceFromServer(message.workspace.id).then(workspace => {
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
    createWorkspace,
    switchToWorkspace,
    resumeWorkspace,
    createDefaultWorkspace,
    initializeWorkspace,
    createTab,
    createPane,
    
    // Backward compatibility (will be removed)
    createTabWithPane: createTab,
    createSpecialTab: createTab,
    saveCurrentWorkspace: () => Promise.resolve(), // No-op
    updateWorkspaceFromTabs: () => Promise.resolve(), // No-op
  }
})