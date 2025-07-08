/**
 * Workspace Event Bus
 * 
 * Centralized event system to avoid circular dependencies between stores
 */

import { reactive } from 'vue'
import type { WorkspaceEvents, TerminalTabWithPanes, TerminalPane } from './workspaceTypes'

class WorkspaceEventBus {
  private listeners: Map<keyof WorkspaceEvents, Set<Function>> = new Map()

  on<K extends keyof WorkspaceEvents>(event: K, callback: WorkspaceEvents[K]) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback as Function)
  }

  off<K extends keyof WorkspaceEvents>(event: K, callback: WorkspaceEvents[K]) {
    const callbacks = this.listeners.get(event)
    if (callbacks) {
      callbacks.delete(callback as Function)
    }
  }

  emit<K extends keyof WorkspaceEvents>(event: K, ...args: Parameters<WorkspaceEvents[K]>) {
    const callbacks = this.listeners.get(event)
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(...args)
        } catch (error) {
          console.error(`Error in event handler for ${event}:`, error)
        }
      })
    }
  }

  // Convenience methods
  emitTabCreated(tab: TerminalTabWithPanes) {
    this.emit('tabCreated', tab)
  }

  emitTabClosed(tabId: string) {
    this.emit('tabClosed', tabId)
  }

  emitTabActivated(tabId: string) {
    this.emit('tabActivated', tabId)
  }

  emitPaneCreated(pane: TerminalPane) {
    this.emit('paneCreated', pane)
  }

  emitPaneClosed(paneId: string) {
    this.emit('paneClosed', paneId)
  }
}

// Singleton instance
export const workspaceEventBus = new WorkspaceEventBus()