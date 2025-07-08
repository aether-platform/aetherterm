/**
 * Cross-tab workspace synchronization
 * 
 * Uses BroadcastChannel API to sync workspace changes across browser tabs
 */

import type { WorkspaceState } from '../workspaceStore'

export interface WorkspaceSyncMessage {
  type: 'workspace_update' | 'workspace_switch' | 'workspace_delete' | 'tab_close'
  workspace?: WorkspaceState
  workspaceId?: string
  tabId?: string
  timestamp: number
}

export class WorkspaceCrossTabSync {
  private channel: BroadcastChannel | null = null
  private listeners: Map<string, (message: WorkspaceSyncMessage) => void> = new Map()
  
  constructor(private channelName: string = 'aetherterm_workspace_sync') {
    this.initialize()
  }
  
  private initialize() {
    if (typeof BroadcastChannel === 'undefined') {
      console.warn('BroadcastChannel API not supported')
      return
    }
    
    try {
      this.channel = new BroadcastChannel(this.channelName)
      
      this.channel.onmessage = (event) => {
        const message = event.data as WorkspaceSyncMessage
        console.log('📡 CROSS-TAB: Received sync message:', message.type)
        
        // Notify all listeners
        this.listeners.forEach(listener => {
          try {
            listener(message)
          } catch (error) {
            console.error('📡 CROSS-TAB: Error in listener:', error)
          }
        })
      }
      
      console.log('📡 CROSS-TAB: BroadcastChannel initialized')
    } catch (error) {
      console.error('📡 CROSS-TAB: Failed to initialize BroadcastChannel:', error)
    }
  }
  
  /**
   * Broadcast a workspace update to other tabs
   */
  broadcastUpdate(workspace: WorkspaceState) {
    if (!this.channel) return
    
    try {
      // Convert workspace to a serializable format
      const serializableWorkspace = this.toSerializable(workspace)
      
      const message: WorkspaceSyncMessage = {
        type: 'workspace_update',
        workspace: serializableWorkspace,
        timestamp: Date.now()
      }
      
      this.channel.postMessage(message)
      console.log('📡 CROSS-TAB: Broadcasted workspace update')
    } catch (error) {
      console.error('📡 CROSS-TAB: Failed to broadcast workspace update:', error)
    }
  }
  
  /**
   * Convert workspace to a serializable format
   */
  private toSerializable(workspace: WorkspaceState): any {
    return JSON.parse(JSON.stringify(workspace, (key, value) => {
      // Convert Date objects to ISO strings
      if (value instanceof Date) {
        return value.toISOString()
      }
      // Remove functions and undefined values
      if (typeof value === 'function' || value === undefined) {
        return null
      }
      return value
    }))
  }
  
  /**
   * Broadcast a workspace switch event
   */
  broadcastSwitch(workspaceId: string) {
    if (!this.channel) return
    
    const message: WorkspaceSyncMessage = {
      type: 'workspace_switch',
      workspaceId,
      timestamp: Date.now()
    }
    
    this.channel.postMessage(message)
    console.log('📡 CROSS-TAB: Broadcasted workspace switch')
  }
  
  /**
   * Broadcast a workspace delete event
   */
  broadcastDelete(workspaceId: string) {
    if (!this.channel) return
    
    const message: WorkspaceSyncMessage = {
      type: 'workspace_delete',
      workspaceId,
      timestamp: Date.now()
    }
    
    this.channel.postMessage(message)
    console.log('📡 CROSS-TAB: Broadcasted workspace delete')
  }
  
  /**
   * Broadcast a tab close event
   */
  broadcastTabClose(workspaceId: string, tabId: string) {
    if (!this.channel) return
    
    const message: WorkspaceSyncMessage = {
      type: 'tab_close',
      workspaceId,
      tabId,
      timestamp: Date.now()
    }
    
    this.channel.postMessage(message)
    console.log('📡 CROSS-TAB: Broadcasted tab close')
  }
  
  /**
   * Add a listener for sync messages
   */
  addListener(id: string, listener: (message: WorkspaceSyncMessage) => void) {
    this.listeners.set(id, listener)
  }
  
  /**
   * Remove a listener
   */
  removeListener(id: string) {
    this.listeners.delete(id)
  }
  
  /**
   * Close the broadcast channel
   */
  close() {
    if (this.channel) {
      this.channel.close()
      this.channel = null
      this.listeners.clear()
      console.log('📡 CROSS-TAB: BroadcastChannel closed')
    }
  }
}

// Singleton instance
let instance: WorkspaceCrossTabSync | null = null

export function getWorkspaceCrossTabSync(): WorkspaceCrossTabSync {
  if (!instance) {
    instance = new WorkspaceCrossTabSync()
  }
  return instance
}