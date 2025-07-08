/**
 * Workspace Types
 * 
 * Shared type definitions to avoid circular dependencies
 */

export interface WorkspaceState {
  id: string
  name: string
  lastAccessed: Date
  tabs: TerminalTabWithPanes[]
  activeTabId?: string
  isActive: boolean
  layout: {
    type: string
    configuration: any
  }
}

export interface TerminalPane {
  id: string
  type: 'terminal' | 'ai-chat' | 'log-viewer'
  sessionId?: string
  title: string
  isActive: boolean
}

export interface TerminalTabWithPanes {
  id: string
  title: string
  type: 'terminal' | 'ai-agent' | 'log-monitor'
  subType?: 'pure' | 'inventory' | 'agent' | 'main-agent'
  isActive: boolean
  panes: TerminalPane[]
  layout: 'single' | 'vertical' | 'horizontal' | 'grid'
  lastActivity: Date
}

export interface WorkspaceEvents {
  tabCreated: (tab: TerminalTabWithPanes) => void
  tabClosed: (tabId: string) => void
  tabActivated: (tabId: string) => void
  paneCreated: (pane: TerminalPane) => void
  paneClosed: (paneId: string) => void
}