/**
 * Workspace Session Manager
 * 
 * Handles session reconnection and workspace resumption
 */

import type { Socket } from 'socket.io-client'
import type { WorkspaceState } from '../workspaceStore'
import { useTerminalTabStore } from '../terminalTabStore'
import { useTerminalPaneStore } from '../terminalPaneStore'

export interface ResumeResult {
  success: boolean
  message?: string
  error?: string
}

export class WorkspaceSessionManager {
  /**
   * Resume a workspace with server-side session reconnection
   */
  static async resumeWorkspace(
    workspace: WorkspaceState, 
    socket: Socket | null
  ): Promise<ResumeResult> {
    if (!socket) {
      return { success: false, error: 'No socket connection' }
    }

    console.log('📋 SESSION_MANAGER: Resuming workspace:', workspace.name, 'with', workspace.tabs.length, 'tabs')

    return new Promise((resolve) => {
      const resumeData = {
        workspaceId: workspace.id,
        tabs: workspace.tabs.map(tab => ({
          id: tab.id,
          title: tab.title,
          type: tab.type || 'terminal', // タブタイプを含める
          subType: tab.subType,
          layout: tab.layout,
          panes: tab.panes.map(pane => ({
            id: pane.id,
            sessionId: pane.sessionId,
            type: pane.type,
            subType: pane.subType,
            title: pane.title,
            position: pane.position
          }))
        }))
      }

      console.log('📋 SESSION_MANAGER: Sending resume_workspace event:', resumeData)

      const handleWorkspaceResumed = (data: any) => {
        console.log('📋 SESSION_MANAGER: Received workspace_resumed:', data)
        
        socket.off('workspace_resumed', handleWorkspaceResumed)
        socket.off('workspace_error', handleWorkspaceError)

        if (data.workspaceId === workspace.id) {
          // Update sessions for resumed and created panes
          const terminalPaneStore = useTerminalPaneStore()
          const terminalTabStore = useTerminalTabStore()
          
          console.log('📋 SESSION_MANAGER: workspace.tabs before mapping:', workspace.tabs)
          
          const allTabResults = (data.resumedTabs || []).concat(data.createdTabs || [])
          allTabResults.forEach((tabResult: any) => {
            // Handle pane-level session mapping
            if (tabResult.panes) {
              tabResult.panes.forEach((paneResult: any, index: number) => {
                console.log(`📋 SESSION_MANAGER: Setting pane session - paneId: ${paneResult.paneId}, sessionId: ${paneResult.sessionId}`)
                
                // Find the corresponding pane by index in the current tab
                const currentTab = workspace.tabs.find(t => t.id === tabResult.tabId)
                if (currentTab && currentTab.panes[index]) {
                  const currentPaneId = currentTab.panes[index].id
                  console.log(`📋 SESSION_MANAGER: Mapping server session to current pane - currentPaneId: ${currentPaneId}`)
                  terminalPaneStore.setPaneSession(currentPaneId, paneResult.sessionId)
                } else {
                  console.warn(`📋 SESSION_MANAGER: Could not find currentTab or pane for tabId: ${tabResult.tabId}, index: ${index}`)
                }
              })
            }
            // Backward compatibility: direct tab session
            if (tabResult.sessionId) {
              terminalTabStore.setTabSession(tabResult.tabId, tabResult.sessionId)
            }
            
            // Also update sessionId based on first pane if not set
            const tab = terminalTabStore.tabs.find(t => t.id === tabResult.tabId)
            if (tab && !tab.sessionId && tabResult.panes?.[0]?.sessionId) {
              terminalTabStore.setTabSession(tabResult.tabId, tabResult.panes[0].sessionId)
            }
          })

          console.log('📋 SESSION_MANAGER: Workspace resumed successfully')
          resolve({ success: true, message: data.message })
        }
      }

      const handleWorkspaceError = (data: any) => {
        console.error('📋 SESSION_MANAGER: Workspace resume error:', data)
        
        socket.off('workspace_resumed', handleWorkspaceResumed)
        socket.off('workspace_error', handleWorkspaceError)
        
        resolve({ success: false, error: data.error || 'Failed to resume workspace' })
      }

      socket.on('workspace_resumed', handleWorkspaceResumed)
      socket.on('workspace_error', handleWorkspaceError)

      // Send the resume request
      socket.emit('resume_workspace', resumeData)

      // Timeout after 10 seconds
      setTimeout(() => {
        socket.off('workspace_resumed', handleWorkspaceResumed)
        socket.off('workspace_error', handleWorkspaceError)
        resolve({ success: false, error: 'Workspace resume timeout' })
      }, 10000)
    })
  }

  /**
   * Reconnect to stored sessions without server communication
   */
  static async reconnectStoredSessions(workspace: WorkspaceState, socket?: Socket): Promise<void> {
    console.log('📋 SESSION_MANAGER: Reconnecting stored sessions for workspace:', workspace.name)
    
    const terminalTabStore = useTerminalTabStore()
    const terminalPaneStore = useTerminalPaneStore()
    
    // Reconstruct the workspace in the stores
    workspace.tabs.forEach(tab => {
      // Register tab in store
      // Get sessionId from first pane if available (for terminal tabs)
      const firstPaneSessionId = tab.panes?.[0]?.sessionId
      
      terminalTabStore.tabs.push({
        id: tab.id,
        title: tab.title,
        type: tab.type || 'terminal', // タブタイプを保持
        subType: tab.subType || 'pure',
        isActive: tab.isActive,
        sessionId: firstPaneSessionId || undefined, // Use pane's sessionId for tab
        serverContext: undefined,
        lastActivity: new Date(),
        status: firstPaneSessionId ? 'connecting' : 'disconnected' // Set to connecting if session exists
      })
      
      // Register panes with their stored session IDs
      tab.panes.forEach(async (pane) => {
        // Set the session ID in the pane store
        if (pane.sessionId) {
          terminalPaneStore.setPaneSession(pane.id, pane.sessionId)
          
          // Attempt to reconnect to existing session for screen buffer restoration
          console.log(`📋 SESSION_MANAGER: Attempting to reconnect to session ${pane.sessionId}`)
          // Use resume_terminal for better support of tabId
          if (socket) {
            socket.emit('resume_terminal', { 
              sessionId: pane.sessionId,
              tabId: tab.id,
              subType: tab.subType || 'pure',
              cols: 80,
              rows: 24
            })
          }
        }
        
        // Register the pane - ensure lastActivity is set
        const paneWithActivity = {
          ...pane,
          lastActivity: pane.lastActivity || new Date()
        }
        const existingIndex = terminalPaneStore.panes.findIndex(p => p.id === pane.id)
        if (existingIndex >= 0) {
          terminalPaneStore.panes[existingIndex] = paneWithActivity
        } else {
          terminalPaneStore.panes.push(paneWithActivity)
        }
      })
    })
    
    console.log('📋 SESSION_MANAGER: Reconstructed workspace structure with stored sessions')
  }
}