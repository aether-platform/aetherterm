import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useAetherTerminalServiceStore } from './aetherTerminalServiceStore'

function generateId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `id_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

export interface Pane {
  id: string
  sessionId: string
  title: string
  type: 'terminal' | 'agent' | 'log'
  mode: 'terminal' | 'code-server' | 'tmux' | 'pilot-chat'
  isFocused: boolean
  size: { rows: number; cols: number }
}

export interface PaneLayout {
  type: 'leaf' | 'hsplit' | 'vsplit'
  paneId?: string
  children?: PaneLayout[]
  ratio: number
}

const LAYOUT_STORAGE_KEY = 'aetherterm-pane-layout'
const PANES_STORAGE_KEY = 'aetherterm-panes'

export const usePaneStore = defineStore('paneStore', () => {
  const panes = ref<Map<string, Pane>>(new Map())
  const layout = ref<PaneLayout>({ type: 'leaf', ratio: 1 })
  const focusedPaneId = ref<string>('')
  const nextPaneNumber = ref(1)

  const terminalStore = useAetherTerminalServiceStore()

  // Getters
  const paneList = computed(() => Array.from(panes.value.values()))
  const focusedPane = computed(() => panes.value.get(focusedPaneId.value))
  const paneCount = computed(() => panes.value.size)

  // Generate unique pane id
  function generatePaneId(): string {
    return `pane_${generateId().slice(0, 8)}`
  }

  // Add a new pane
  function addPane(direction?: 'horizontal' | 'vertical', mode: Pane['mode'] = 'terminal'): Pane {
    const id = generatePaneId()
    const sessionId = `session_${generateId().slice(0, 8)}`
    const num = nextPaneNumber.value++

    const pane: Pane = {
      id,
      sessionId,
      title: mode === 'terminal' ? `Terminal ${num}` : `${mode} ${num}`,
      type: 'terminal',
      mode,
      isFocused: false,
      size: { rows: 24, cols: 80 },
    }

    panes.value.set(id, pane)

    // Update layout
    if (paneCount.value === 1) {
      // First pane: simple leaf
      layout.value = { type: 'leaf', paneId: id, ratio: 1 }
    } else if (direction) {
      // Split the currently focused pane
      const splitType = direction === 'horizontal' ? 'hsplit' : 'vsplit'
      const currentFocused = focusedPaneId.value

      if (currentFocused) {
        insertSplit(layout.value, currentFocused, id, splitType)
      } else {
        // Wrap entire layout in a split
        const oldLayout = { ...layout.value }
        layout.value = {
          type: splitType,
          children: [oldLayout, { type: 'leaf', paneId: id, ratio: 0.5 }],
          ratio: 1,
        }
        if (oldLayout.ratio) oldLayout.ratio = 0.5
      }
    } else {
      // Default: vertical split at root
      if (layout.value.type === 'leaf') {
        const oldPaneId = layout.value.paneId
        layout.value = {
          type: 'vsplit',
          children: [
            { type: 'leaf', paneId: oldPaneId, ratio: 0.5 },
            { type: 'leaf', paneId: id, ratio: 0.5 },
          ],
          ratio: 1,
        }
      } else {
        layout.value.children = layout.value.children || []
        // Rebalance ratios
        const count = layout.value.children.length + 1
        layout.value.children.forEach((c) => (c.ratio = 1 / count))
        layout.value.children.push({ type: 'leaf', paneId: id, ratio: 1 / count })
      }
    }

    focusPane(id)

    // Emit pane_create to backend
    if (terminalStore.socket) {
      terminalStore.socket.emit('pane_create', {
        session_id: sessionId,
        pane_type: pane.type,
        mode: pane.mode,
        title: pane.title,
        size: pane.size,
      })
    }

    saveToLocalStorage()
    return pane
  }

  // Insert a split into the layout tree at the target pane
  function insertSplit(
    node: PaneLayout,
    targetPaneId: string,
    newPaneId: string,
    splitType: 'hsplit' | 'vsplit'
  ): boolean {
    if (node.type === 'leaf' && node.paneId === targetPaneId) {
      // Replace this leaf with a split
      const oldPaneId = node.paneId
      node.type = splitType
      node.paneId = undefined
      node.children = [
        { type: 'leaf', paneId: oldPaneId, ratio: 0.5 },
        { type: 'leaf', paneId: newPaneId, ratio: 0.5 },
      ]
      return true
    }

    if (node.children) {
      for (const child of node.children) {
        if (insertSplit(child, targetPaneId, newPaneId, splitType)) {
          return true
        }
      }
    }

    return false
  }

  // Remove a pane
  function removePane(id: string) {
    const pane = panes.value.get(id)
    if (!pane) return

    panes.value.delete(id)

    // Remove from layout and simplify
    removePaneFromLayout(layout.value, id)
    simplifyLayout(layout.value)

    // If we removed the focused pane, focus the first remaining pane
    if (focusedPaneId.value === id) {
      const remaining = paneList.value
      if (remaining.length > 0) {
        focusPane(remaining[0].id)
      } else {
        focusedPaneId.value = ''
      }
    }

    // Emit pane_destroy to backend
    if (terminalStore.socket) {
      terminalStore.socket.emit('pane_destroy', { pane_id: id })
    }

    saveToLocalStorage()
  }

  function removePaneFromLayout(node: PaneLayout, paneId: string): boolean {
    if (!node.children) return false

    const idx = node.children.findIndex((c) => c.type === 'leaf' && c.paneId === paneId)
    if (idx !== -1) {
      node.children.splice(idx, 1)
      // Rebalance
      if (node.children.length > 0) {
        const ratio = 1 / node.children.length
        node.children.forEach((c) => (c.ratio = ratio))
      }
      return true
    }

    for (const child of node.children) {
      if (removePaneFromLayout(child, paneId)) return true
    }
    return false
  }

  function simplifyLayout(node: PaneLayout) {
    if (node.children) {
      // Recursively simplify children first
      node.children.forEach(simplifyLayout)

      // If only one child, replace this node with that child
      if (node.children.length === 1) {
        const only = node.children[0]
        node.type = only.type
        node.paneId = only.paneId
        node.children = only.children
        node.ratio = node.ratio // Keep current ratio
      }
    }
  }

  // Focus a pane
  function focusPane(id: string) {
    // Unfocus all
    panes.value.forEach((p) => (p.isFocused = false))
    const pane = panes.value.get(id)
    if (pane) {
      pane.isFocused = true
      focusedPaneId.value = id

      if (terminalStore.socket) {
        terminalStore.socket.emit('pane_focus', { pane_id: id })
      }
    }
  }

  // Focus next pane (for Ctrl+Tab)
  function focusNextPane() {
    const list = paneList.value
    if (list.length <= 1) return

    const currentIdx = list.findIndex((p) => p.id === focusedPaneId.value)
    const nextIdx = (currentIdx + 1) % list.length
    focusPane(list[nextIdx].id)
  }

  // Update layout ratio (for divider drag)
  function updateLayoutRatio(path: number[], ratio: number) {
    let node = layout.value
    for (let i = 0; i < path.length - 1; i++) {
      if (node.children) {
        node = node.children[path[i]]
      }
    }
    if (node.children && path.length > 0) {
      const idx = path[path.length - 1]
      if (idx < node.children.length) {
        node.children[idx].ratio = ratio
        // Adjust sibling
        if (idx + 1 < node.children.length) {
          node.children[idx + 1].ratio = 1 - ratio
        }
      }
    }
    saveToLocalStorage()
  }

  // Persistence
  function saveToLocalStorage() {
    try {
      const panesArray = Array.from(panes.value.entries())
      localStorage.setItem(PANES_STORAGE_KEY, JSON.stringify(panesArray))
      localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout.value))
    } catch {
      // Silently fail
    }
  }

  function loadFromLocalStorage(): boolean {
    try {
      const panesData = localStorage.getItem(PANES_STORAGE_KEY)
      const layoutData = localStorage.getItem(LAYOUT_STORAGE_KEY)

      if (panesData && layoutData) {
        const panesArray: [string, Pane][] = JSON.parse(panesData)
        panes.value = new Map(panesArray)
        layout.value = JSON.parse(layoutData)

        // Find focused pane
        const focused = paneList.value.find((p) => p.isFocused)
        if (focused) {
          focusedPaneId.value = focused.id
        }

        // Update nextPaneNumber
        const maxNum = paneList.value.reduce((max, p) => {
          const match = p.title.match(/Terminal (\d+)/)
          return match ? Math.max(max, parseInt(match[1])) : max
        }, 0)
        nextPaneNumber.value = maxNum + 1

        return panes.value.size > 0
      }
    } catch {
      // Silently fail
    }
    return false
  }

  // Re-register all panes on backend after reconnection
  function reconnectPanes() {
    if (!terminalStore.socket) return

    paneList.value.forEach((pane) => {
      terminalStore.socket!.emit('pane_create', {
        session_id: pane.sessionId,
        pane_type: pane.type,
        title: pane.title,
        size: pane.size,
      })
    })

    // Re-focus current pane
    if (focusedPaneId.value) {
      terminalStore.socket.emit('pane_focus', { pane_id: focusedPaneId.value })
    }
  }

  // Initialize with default pane if empty
  function initialize() {
    if (!loadFromLocalStorage() || panes.value.size === 0) {
      addPane()
    }

    // Watch for reconnection to re-register panes
    const checkReconnect = setInterval(() => {
      if (terminalStore.connectionState.isConnected && terminalStore.socket) {
        reconnectPanes()
        clearInterval(checkReconnect)
      }
    }, 1000)
  }

  return {
    // State
    panes,
    layout,
    focusedPaneId,

    // Getters
    paneList,
    focusedPane,
    paneCount,

    // Actions
    addPane,
    removePane,
    focusPane,
    focusNextPane,
    updateLayoutRatio,
    initialize,
    reconnectPanes,
    saveToLocalStorage,
  }
})
