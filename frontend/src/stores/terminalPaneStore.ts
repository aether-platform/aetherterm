import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface TerminalPane {
  id: string
  title: string
  type: 'terminal' | 'ai-agent' | 'log-monitor'
  subType?: 'pure' | 'inventory' | 'agent' | 'main-agent'
  sessionId?: string
  isActive: boolean
  lastActivity: Date
  status: 'active' | 'connecting' | 'disconnected' | 'error'
  position: {
    x: number
    y: number
    width: number
    height: number
  }
  tabId: string // 所属するタブのID
}

export interface TerminalTabWithPanes {
  id: string
  title: string
  type?: 'terminal' | 'ai-agent' | 'log-monitor' // タブタイプを追加
  subType?: 'pure' | 'inventory' | 'agent' | 'main-agent'
  isActive: boolean
  panes: TerminalPane[]
  layout: 'single' | 'horizontal' | 'vertical' | 'grid'
  lastActivity: Date
}

export const useTerminalPaneStore = defineStore('terminalPane', () => {
  // State
  const panes = ref<TerminalPane[]>([])
  const tabsWithPanes = ref<TerminalTabWithPanes[]>([])
  const activePaneId = ref<string | null>(null)

  // Getters
  const activePanes = computed(() => panes.value.filter(pane => pane.isActive))
  const activePane = computed(() => 
    panes.value.find(pane => pane.id === activePaneId.value) || null
  )
  
  const getPanesByTab = (tabId: string) => 
    panes.value.filter(pane => pane.tabId === tabId)

  // Actions
  const createPane = (
    tabId: string,
    type: 'terminal' | 'ai-agent' | 'log-monitor',
    title?: string,
    subType?: 'pure' | 'inventory' | 'agent' | 'main-agent',
    position?: TerminalPane['position']
  ): TerminalPane => {
    const paneId = `pane-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    
    const newPane: TerminalPane = {
      id: paneId,
      title: title || `${type} ${panes.value.length + 1}`,
      type,
      subType,
      tabId,
      isActive: true,
      lastActivity: new Date(),
      status: 'connecting',
      position: position || {
        x: 0,
        y: 0,
        width: 100,
        height: 100
      }
    }

    panes.value.push(newPane)
    activePaneId.value = paneId

    // Update or create tab with panes
    let tabWithPanes = tabsWithPanes.value.find(tab => tab.id === tabId)
    if (!tabWithPanes) {
      tabWithPanes = {
        id: tabId,
        title: `Tab ${tabsWithPanes.value.length + 1}`,
        isActive: true,
        panes: [],
        layout: 'single',
        lastActivity: new Date()
      }
      tabsWithPanes.value.push(tabWithPanes)
    }
    
    tabWithPanes.panes.push(newPane)
    
    console.log('📋 PANE: Created pane:', newPane)
    return newPane
  }

  const setPaneSession = (paneId: string, sessionId: string) => {
    const pane = panes.value.find(p => p.id === paneId)
    if (pane) {
      pane.sessionId = sessionId
      console.log('📋 PANE: Set session for pane:', paneId, '-> session:', sessionId)
    }
  }

  const getPaneSession = (paneId: string): string | undefined => {
    const pane = panes.value.find(p => p.id === paneId)
    return pane?.sessionId
  }
  
  // Simply return existing session if available, don't create new ones
  const getExistingSession = (paneId: string): string | undefined => {
    return getPaneSession(paneId)
  }

  const splitPane = (
    paneId: string, 
    direction: 'horizontal' | 'vertical'
  ): TerminalPane | null => {
    const existingPane = panes.value.find(p => p.id === paneId)
    if (!existingPane) return null

    const tab = tabsWithPanes.value.find(t => t.id === existingPane.tabId)
    if (!tab) return null

    // Adjust existing pane size
    if (direction === 'horizontal') {
      existingPane.position.width = 50
      // Create new pane on the right
      return createPane(
        existingPane.tabId,
        'terminal',
        undefined,
        'pure',
        {
          x: 50,
          y: existingPane.position.y,
          width: 50,
          height: existingPane.position.height
        }
      )
    } else {
      existingPane.position.height = 50
      // Create new pane below
      return createPane(
        existingPane.tabId,
        'terminal',
        undefined,
        'pure',
        {
          x: existingPane.position.x,
          y: 50,
          width: existingPane.position.width,
          height: 50
        }
      )
    }
  }

  const closePane = (paneId: string) => {
    const paneIndex = panes.value.findIndex(p => p.id === paneId)
    if (paneIndex === -1) return

    const pane = panes.value[paneIndex]
    pane.isActive = false

    // Update tab
    const tab = tabsWithPanes.value.find(t => t.id === pane.tabId)
    if (tab) {
      tab.panes = tab.panes.filter(p => p.id !== paneId)
      
      // If this was the active pane, switch to another
      if (activePaneId.value === paneId) {
        const remainingPanes = tab.panes.filter(p => p.isActive)
        activePaneId.value = remainingPanes.length > 0 ? remainingPanes[0].id : null
      }
    }

    // Remove pane after delay
    setTimeout(() => {
      const index = panes.value.findIndex(p => p.id === paneId)
      if (index !== -1) {
        panes.value.splice(index, 1)
      }
    }, 100)
  }

  const switchToPane = (paneId: string) => {
    const pane = panes.value.find(p => p.id === paneId)
    if (pane && pane.isActive) {
      activePaneId.value = paneId
      pane.lastActivity = new Date()
    }
  }

  const updatePaneLayout = (tabId: string, layout: TerminalTabWithPanes['layout']) => {
    const tab = tabsWithPanes.value.find(t => t.id === tabId)
    if (tab) {
      tab.layout = layout
      console.log('📋 PANE: Updated layout for tab:', tabId, 'to:', layout)
    }
  }

  return {
    // State
    panes,
    tabsWithPanes,
    activePaneId,

    // Getters
    activePanes,
    activePane,
    getPanesByTab,

    // Actions
    createPane,
    setPaneSession,
    getPaneSession,
    getExistingSession,
    splitPane,
    closePane,
    switchToPane,
    updatePaneLayout
  }
})