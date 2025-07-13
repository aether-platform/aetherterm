/**
 * Workspace Persistence Manager
 * 
 * Handles saving and loading workspace data to/from localStorage
 */

import type { WorkspaceState } from '../workspaceStore'

// LocalStorage keys
export const WORKSPACE_STORAGE_KEY = 'aetherterm_workspaces'
export const CURRENT_WORKSPACE_KEY = 'aetherterm_current_workspace'
export const TERMINAL_SESSIONS_KEY = 'aetherterm_terminal_sessions'

interface TerminalSessionState {
  sessionId: string
  tabId: string
  paneId: string
  type: string
  subType?: string
  lastActive: string
}

export class WorkspacePersistenceManager {
  /**
   * Persist workspace to localStorage
   */
  static persist(workspace: WorkspaceState, allWorkspaceIds: string[]): void {
    try {
      // Save workspace with session IDs
      const workspaceData = {
        ...workspace,
        tabs: workspace.tabs.map(tab => ({
          ...tab,
          panes: tab.panes.map(pane => ({
            ...pane,
            sessionId: pane.sessionId, // Preserve session ID
            lastActivity: pane.lastActivity?.toISOString()
          })),
          lastActivity: tab.lastActivity?.toISOString()
        })),
        lastAccessed: workspace.lastAccessed.toISOString()
      }
      
      // Save to localStorage
      localStorage.setItem(`${WORKSPACE_STORAGE_KEY}_${workspace.id}`, JSON.stringify(workspaceData))
      
      // Update workspace list
      localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(allWorkspaceIds))
      
      console.log('💾 WORKSPACE: Persisted workspace to localStorage:', workspace.id)
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to persist workspace:', error)
    }
  }

  /**
   * Save current workspace ID
   */
  static saveCurrentWorkspaceId(workspaceId: string): void {
    try {
      localStorage.setItem(CURRENT_WORKSPACE_KEY, workspaceId)
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to save current workspace ID:', error)
    }
  }

  /**
   * Load all workspaces from localStorage
   */
  static loadAll(): WorkspaceState[] {
    try {
      const workspaceIds = JSON.parse(localStorage.getItem(WORKSPACE_STORAGE_KEY) || '[]')
      const loadedWorkspaces: WorkspaceState[] = []
      
      for (const id of workspaceIds) {
        const workspaceData = localStorage.getItem(`${WORKSPACE_STORAGE_KEY}_${id}`)
        if (workspaceData) {
          const parsed = JSON.parse(workspaceData)
          // Reconstruct workspace with proper date objects
          const workspace: WorkspaceState = {
            ...parsed,
            lastAccessed: new Date(parsed.lastAccessed),
            tabs: parsed.tabs.map((tab: any) => ({
              ...tab,
              panes: tab.panes.map((pane: any) => ({
                ...pane,
                lastActivity: pane.lastActivity ? new Date(pane.lastActivity) : new Date()
              })),
              lastActivity: tab.lastActivity ? new Date(tab.lastActivity) : new Date()
            }))
          }
          loadedWorkspaces.push(workspace)
        }
      }
      
      console.log('💾 WORKSPACE: Loaded', loadedWorkspaces.length, 'workspaces from localStorage')
      return loadedWorkspaces
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to load workspaces:', error)
      return []
    }
  }

  /**
   * Get last active workspace ID
   */
  static getLastWorkspaceId(): string | null {
    try {
      return localStorage.getItem(CURRENT_WORKSPACE_KEY)
    } catch {
      return null
    }
  }

  /**
   * Persist terminal sessions for recovery after page refresh
   */
  static persistTerminalSessions(workspace: WorkspaceState): void {
    try {
      const sessions: TerminalSessionState[] = []
      
      workspace.tabs.forEach(tab => {
        tab.panes.forEach(pane => {
          if (pane.sessionId) {
            sessions.push({
              sessionId: pane.sessionId,
              tabId: tab.id,
              paneId: pane.id,
              type: pane.type,
              subType: pane.subType,
              lastActive: new Date().toISOString()
            })
          }
        })
      })
      
      localStorage.setItem(TERMINAL_SESSIONS_KEY, JSON.stringify(sessions))
      console.log('💾 WORKSPACE: Persisted', sessions.length, 'terminal sessions')
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to persist terminal sessions:', error)
    }
  }

  /**
   * Load terminal sessions from localStorage
   */
  static loadTerminalSessions(): TerminalSessionState[] {
    try {
      const data = localStorage.getItem(TERMINAL_SESSIONS_KEY)
      if (!data) return []
      
      const sessions = JSON.parse(data) as TerminalSessionState[]
      console.log('💾 WORKSPACE: Loaded', sessions.length, 'terminal sessions from storage')
      return sessions
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to load terminal sessions:', error)
      return []
    }
  }

  /**
   * Clear all workspace data from localStorage
   */
  static clearAll(): void {
    try {
      const workspaceIds = JSON.parse(localStorage.getItem(WORKSPACE_STORAGE_KEY) || '[]')
      
      // Remove all workspace data
      for (const id of workspaceIds) {
        localStorage.removeItem(`${WORKSPACE_STORAGE_KEY}_${id}`)
      }
      
      // Clear workspace list and current workspace
      localStorage.removeItem(WORKSPACE_STORAGE_KEY)
      localStorage.removeItem(CURRENT_WORKSPACE_KEY)
      localStorage.removeItem(TERMINAL_SESSIONS_KEY)
      
      console.log('🗑️ WORKSPACE: Cleared all workspace data from localStorage')
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to clear workspace data:', error)
    }
  }

  /**
   * Remove a specific workspace from localStorage
   */
  static remove(workspaceId: string): void {
    try {
      localStorage.removeItem(`${WORKSPACE_STORAGE_KEY}_${workspaceId}`)
      
      // Update workspace list
      const workspaceIds = JSON.parse(localStorage.getItem(WORKSPACE_STORAGE_KEY) || '[]')
      const filteredIds = workspaceIds.filter((id: string) => id !== workspaceId)
      localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(filteredIds))
      
      console.log('🗑️ WORKSPACE: Removed workspace from localStorage:', workspaceId)
    } catch (error) {
      console.error('❌ WORKSPACE: Failed to remove workspace:', error)
    }
  }
}