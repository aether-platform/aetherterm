/**
 * AetherTerminal統一ストア
 * 
 * WebSocket通信とセッション管理を単純化
 * レガシーコードを削除し、クリーンなアーキテクチャで再構築
 */

import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { io, type Socket } from 'socket.io-client'
import { useTerminalTabStore } from './terminalTabStore'
import { useTerminalPaneStore } from './terminalPaneStore'

// 型定義
interface ConnectionState {
  isConnected: boolean
  isConnecting: boolean
  error?: string
  lastConnected?: Date
}

interface TerminalSession {
  id: string
  type: 'tab' | 'pane'
  terminalId: string
  isActive: boolean
  createdAt: Date
}

interface OutputCallback {
  sessionId: string
  callback: (data: string) => void
}

export const useAetherTerminalStore = defineStore('aetherTerminal', () => {
  // 接続状態
  const connectionState = reactive<ConnectionState>({
    isConnected: false,
    isConnecting: false
  })

  // WebSocket
  const socket = ref<Socket | null>(null)

  // セッション管理
  const sessions = ref<Map<string, TerminalSession>>(new Map())

  // 出力コールバック管理（シンプルな1対1マッピング）
  const outputCallbacks = ref<Map<string, (data: string) => void>>(new Map())
  
  // Terminal closed callbacks
  const terminalClosedCallbacks = ref<Array<() => void>>([])

  // 接続管理
  const connect = async (): Promise<boolean> => {
    if (connectionState.isConnected || connectionState.isConnecting) {
      return connectionState.isConnected
    }

    connectionState.isConnecting = true
    connectionState.error = undefined

    try {
      // Socket.IO接続を作成 - Connection optimized
      socket.value = io('http://localhost:57575', {
        transports: ['polling', 'websocket'], // Allow both transports for reliability
        timeout: 10000, // Increased timeout for better compatibility
        forceNew: true,
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
      })

      // 接続イベントのセットアップ
      setupSocketEvents()

      // 接続完了を待機
      return new Promise((resolve) => {
        const timeout = setTimeout(() => {
          connectionState.isConnecting = false
          connectionState.error = 'Connection timeout'
          resolve(false)
        }, 10000) // Increased connection timeout

        socket.value?.on('connect', () => {
          clearTimeout(timeout)
          connectionState.isConnected = true
          connectionState.isConnecting = false
          connectionState.lastConnected = new Date()
          console.log('✅ AETHER_TERMINAL: Connected successfully')
          
          // Connect to global workspace
          socket.value?.emit('workspace_connect', { role: 'User' })
          console.log('📋 AETHER_TERMINAL: Connected to global workspace')
          
          resolve(true)
        })

        socket.value?.on('connect_error', (error) => {
          clearTimeout(timeout)
          connectionState.isConnecting = false
          connectionState.error = error.message
          console.error('❌ AETHER_TERMINAL: Connection error:', error)
          resolve(false)
        })
      })
    } catch (error) {
      connectionState.isConnecting = false
      connectionState.error = error instanceof Error ? error.message : 'Unknown error'
      console.error('❌ AETHER_TERMINAL: Failed to connect:', error)
      return false
    }
  }

  // WebSocketイベントセットアップ（最小限）
  const setupSocketEvents = () => {
    if (!socket.value) return

    // セッション再接続の応答
    socket.value.on('session_reconnected', (data) => {
      const { sessionId, historyLines } = data
      console.log(`✅ AETHER_TERMINAL: Session reconnected: ${sessionId} (${historyLines} history lines)`)
    })
    
    socket.value.on('session_reconnect_error', (data) => {
      const { error } = data
      console.error(`❌ AETHER_TERMINAL: Session reconnect error: ${error}`)
    })

    // 切断イベント
    socket.value.on('disconnect', (reason) => {
      connectionState.isConnected = false
      connectionState.error = reason
      console.log('🔌 AETHER_TERMINAL: Disconnected:', reason)
    })

    // ターミナル出力イベント（統一）- Performance optimized
    socket.value.on('terminal_output', (data: { session?: string; data?: string }) => {
      if (data?.session && data?.data) {
        const callback = outputCallbacks.value.get(data.session)
        if (callback) {
          callback(data.data)
        } else {
          console.warn(`⚠️ AETHER_STORE: No callback registered for session ${data.session}`)
        }
      }
    })

    // セッション作成イベント (backend emits 'terminal_ready' not 'session_created')
    socket.value.on('terminal_ready', (data: { session?: string; status?: string; tabId?: string }) => {
      if (data?.session) {
        console.log('✅ AETHER_TERMINAL: Terminal ready:', data.session, 'tabId:', data.tabId, 'status:', data.status)
        // Update tab status from 'connecting' to 'active'
        const terminalTabStore = useTerminalTabStore()
        
        // Debug: Log all tabs and their sessionIds
        console.log('📋 AETHER_TERMINAL: Current tabs:', terminalTabStore.tabs.map(t => ({ 
          id: t.id, 
          sessionId: t.sessionId, 
          status: t.status 
        })))
        
        // First try to find tab by sessionId
        let tab = terminalTabStore.tabs.find(t => t.sessionId === data.session)
        
        // If not found and we have tabId, find by tabId
        if (!tab && data.tabId) {
          tab = terminalTabStore.tabs.find(t => t.id === data.tabId)
          // Update the sessionId if found
          if (tab) {
            terminalTabStore.setTabSession(tab.id, data.session)
          }
        }
        
        // If still not found, check if any tab's panes have this sessionId
        if (!tab) {
          const terminalPaneStore = useTerminalPaneStore()
          const pane = terminalPaneStore.panes.find(p => p.sessionId === data.session)
          if (pane && pane.tabId) {
            tab = terminalTabStore.tabs.find(t => t.id === pane.tabId)
            // Update the tab's sessionId to match its first pane
            if (tab && !tab.sessionId) {
              terminalTabStore.setTabSession(tab.id, data.session)
            }
          }
        }
        
        if (tab) {
          terminalTabStore.updateTabStatus(tab.id, 'active')
          console.log('✅ AETHER_TERMINAL: Updated tab status to active for session:', data.session)
        } else {
          console.warn('⚠️ AETHER_TERMINAL: No tab found for session:', data.session)
        }
        
        // Also update pane status if applicable
        const terminalPaneStore = useTerminalPaneStore()
        const pane = terminalPaneStore.panes.find(p => p.sessionId === data.session)
        if (pane) {
          pane.status = 'active'
          console.log('✅ AETHER_TERMINAL: Updated pane status to active for session:', data.session)
        }
      }
    })
    
    // Terminal closed event
    socket.value.on('terminal_closed', (data: { session?: string }) => {
      if (data?.session) {
        console.log('🔴 AETHER_TERMINAL: Terminal closed:', data.session)
        
        // Mark session as inactive
        const session = sessions.value.get(data.session)
        if (session) {
          session.isActive = false
        }
        
        // Notify all terminal closed callbacks
        terminalClosedCallbacks.value.forEach(callback => {
          try {
            callback()
          } catch (error) {
            console.error('❌ AETHER_TERMINAL: Error in terminal closed callback:', error)
          }
        })
        
        // Update tab status if applicable
        const terminalTabStore = useTerminalTabStore()
        const tab = terminalTabStore.tabs.find(t => t.sessionId === data.session)
        if (tab) {
          terminalTabStore.updateTabStatus(tab.id, 'closed')
        }
        
        // Update pane status if applicable
        const terminalPaneStore = useTerminalPaneStore()
        const pane = terminalPaneStore.panes.find(p => p.sessionId === data.session)
        if (pane) {
          pane.status = 'closed'
        }
      }
    })
  }

  // Session reconnection attempt - 最適化された再接続
  const attemptSessionReconnection = async (sessionId: string): Promise<boolean> => {
    if (!socket.value?.connected) {
      return false
    }

    return new Promise((resolve) => {
      const handleTerminalReady = (data: any) => {
        if (data.session === sessionId) {
          socket.value?.off('terminal_ready', handleTerminalReady)
          socket.value?.off('terminal_error', handleError)
          
          // Register the reconnected session
          sessions.value.set(sessionId, {
            id: sessionId,
            type: data.type || 'pane',
            terminalId: data.terminalId || sessionId,
            isActive: true,
            createdAt: new Date()
          })
          
          // Update tab status to active
          const terminalTabStore = useTerminalTabStore()
          const tab = terminalTabStore.tabs.find(t => t.sessionId === sessionId)
          if (tab) {
            terminalTabStore.updateTabStatus(tab.id, 'active')
          }
          
          resolve(true)
        }
      }

      const handleError = (data: any) => {
        if (data.session === sessionId) {
          socket.value?.off('terminal_ready', handleTerminalReady)
          socket.value?.off('terminal_error', handleError)
          
          // Update tab status to error
          const terminalTabStore = useTerminalTabStore()
          const tab = terminalTabStore.tabs.find(t => t.sessionId === sessionId)
          if (tab) {
            terminalTabStore.updateTabStatus(tab.id, 'error')
          }
          
          resolve(false)
        }
      }

      socket.value?.on('terminal_ready', handleTerminalReady)
      socket.value?.on('terminal_error', handleError)
      
      // Use resume_terminal instead of reconnect_session for better history support
      socket.value?.emit('resume_terminal', { 
        sessionId: sessionId,
        cols: 80,
        rows: 24
      })

      // Reduced timeout for faster UX
      setTimeout(() => {
        socket.value?.off('terminal_ready', handleTerminalReady)
        socket.value?.off('terminal_error', handleError)
        resolve(false)
      }, 2000)
    })
  }

  // セッション管理
  const requestSession = async (
    terminalId: string, 
    mode: 'tab' | 'pane', 
    subType: string = 'pure'
  ): Promise<string | null> => {
    // Check both connection state and socket connection
    if (!connectionState.isConnected || !socket.value?.connected) {
      console.error('❌ AETHER_TERMINAL: Cannot request session - no connection', {
        connectionState: connectionState.isConnected,
        socketConnected: socket.value?.connected,
        socketExists: !!socket.value
      })
      return null
    }

    const sessionId = `aether_${mode}_${terminalId}`
    
    // Check if session already exists and is active
    const existingSession = sessions.value.get(sessionId)
    if (existingSession && existingSession.isActive) {
      console.log('🔄 AETHER_TERMINAL: Using existing session:', sessionId)
      return sessionId
    }
    
    // Check if this session exists on the server (reconnection scenario)
    const reconnectAttempt = await attemptSessionReconnection(sessionId)
    if (reconnectAttempt) {
      console.log('✅ AETHER_TERMINAL: Successfully reconnected to existing session:', sessionId)
      return sessionId
    }
    
    console.log('🔄 AETHER_TERMINAL: Requesting new session:', sessionId)

    return new Promise((resolve) => {
      const handleTerminalReady = (data: any) => {
        if (data.session && data.session === sessionId) {
          // セッション登録
          sessions.value.set(data.session, {
            id: data.session,
            type: mode,
            terminalId,
            isActive: true,
            createdAt: new Date()
          })

          socket.value?.off('terminal_ready', handleTerminalReady)
          
          // Update tab status to active
          const terminalTabStore = useTerminalTabStore()
          const tab = terminalTabStore.tabs.find(t => t.sessionId === data.session)
          if (tab) {
            terminalTabStore.updateTabStatus(tab.id, 'active')
          }
          
          resolve(data.session)
        }
      }

      socket.value?.on('terminal_ready', handleTerminalReady)
      socket.value?.emit('create_terminal', {
        session: sessionId,
        user: '',
        path: '',
        cols: 80,
        rows: 24,
        [mode === 'pane' ? 'paneId' : 'tabId']: terminalId,
        subType: subType,
        reconnect: existingSession ? true : false // Indicate if this is a reconnection attempt
      })

      // タイムアウト処理
      setTimeout(() => {
        socket.value?.off('terminal_ready', handleTerminalReady)
        resolve(null)
      }, 5000)
    })
  }

  // 入力送信（統一）
  const sendInput = (sessionId: string, data: string) => {
    if (!socket.value?.connected) {
      console.warn('⚠️ AETHER_TERMINAL: Cannot send input - no connection')
      return
    }

    socket.value.emit('terminal_input', {
      session: sessionId,
      data
    })
  }

  // 出力コールバック管理（シンプル）
  const registerOutputCallback = (sessionId: string, callback: (data: string) => void) => {
    outputCallbacks.value.set(sessionId, callback)
    console.log('📺 AETHER_TERMINAL: Registered output callback for session:', sessionId)
  }

  const unregisterOutputCallback = (sessionId: string) => {
    outputCallbacks.value.delete(sessionId)
    console.log('🗑️ AETHER_TERMINAL: Unregistered output callback for session:', sessionId)
  }
  
  // Terminal closed callback management
  const onTerminalClosed = (callback: () => void) => {
    terminalClosedCallbacks.value.push(callback)
  }
  
  const offTerminalClosed = (callback: () => void) => {
    const index = terminalClosedCallbacks.value.indexOf(callback)
    if (index !== -1) {
      terminalClosedCallbacks.value.splice(index, 1)
    }
  }

  // セッション終了
  const closeSession = (sessionId: string) => {
    sessions.value.delete(sessionId)
    unregisterOutputCallback(sessionId)
    console.log('🗑️ AETHER_TERMINAL: Closed session:', sessionId)
  }

  // 切断
  const disconnect = () => {
    if (socket.value) {
      socket.value.disconnect()
      socket.value = null
    }
    connectionState.isConnected = false
    sessions.value.clear()
    outputCallbacks.value.clear()
    console.log('🔌 AETHER_TERMINAL: Disconnected and cleaned up')
  }

  // セッション再接続
  const reconnectSession = (sessionId: string): Promise<boolean> => {
    return new Promise((resolve) => {
      if (!socket.value?.connected) {
        console.warn('⚠️ AETHER_TERMINAL: Cannot reconnect - no connection')
        resolve(false)
        return
      }

      console.log('🔄 AETHER_TERMINAL: Attempting to reconnect to session:', sessionId)
      console.log('📍 AETHER_TERMINAL: Socket connected:', socket.value?.connected)
      console.log('📍 AETHER_TERMINAL: Socket ID:', socket.value?.id)
      
      const handleReady = (data: any) => {
        if (data.session === sessionId) {
          socket.value?.off('terminal_ready', handleReady)
          socket.value?.off('terminal_error', handleError)
          console.log('✅ AETHER_TERMINAL: Reconnected to session:', sessionId)
          
          // Update tab status to active
          const terminalTabStore = useTerminalTabStore()
          const tab = terminalTabStore.tabs.find(t => t.sessionId === sessionId)
          if (tab) {
            terminalTabStore.updateTabStatus(tab.id, 'active')
          }
          
          resolve(true)
        }
      }

      const handleError = (data: any) => {
        socket.value?.off('terminal_ready', handleReady)
        socket.value?.off('terminal_error', handleError)
        console.error('❌ AETHER_TERMINAL: Failed to reconnect:', data.error)
        
        // Update tab status to error
        const terminalTabStore = useTerminalTabStore()
        const tab = terminalTabStore.tabs.find(t => t.sessionId === sessionId)
        if (tab) {
          terminalTabStore.updateTabStatus(tab.id, 'error')
        }
        
        resolve(false)
      }

      socket.value.on('terminal_ready', handleReady)
      socket.value.on('terminal_error', handleError)
      
      // Send reconnect_session event
      console.log('📤 AETHER_TERMINAL: Emitting reconnect_session with sessionId:', sessionId)
      console.log('📤 AETHER_TERMINAL: Full event data:', { session: sessionId })
      socket.value.emit('reconnect_session', { session: sessionId })

      // Timeout after 5 seconds
      setTimeout(() => {
        socket.value?.off('terminal_ready', handleReady)
        socket.value?.off('terminal_error', handleError)
        resolve(false)
      }, 5000)
    })
  }

  // セッション情報取得（デバッグ用）
  const getSessionInfo = (sessionId: string): Promise<any> => {
    return new Promise((resolve) => {
      if (!socket.value?.connected) {
        resolve({ error: 'Not connected' })
        return
      }

      const handleInfo = (data: any) => {
        socket.value?.off('session_info', handleInfo)
        resolve(data)
      }

      socket.value.on('session_info', handleInfo)
      socket.value.emit('get_session_info', { session: sessionId })

      setTimeout(() => {
        socket.value?.off('session_info', handleInfo)
        resolve({ error: 'Timeout' })
      }, 2000)
    })
  }

  // Getter for socket
  const getSocket = () => socket.value

  return {
    // 状態
    connectionState,
    socket: computed(() => socket.value),
    sessions,

    // 接続管理
    connect,
    disconnect,

    // セッション管理
    requestSession,
    closeSession,
    reconnectSession,

    // 通信
    sendInput,
    registerOutputCallback,
    unregisterOutputCallback,
    
    // Terminal closed events
    onTerminalClosed,
    offTerminalClosed,

    // Helper
    getSocket,
    getSessionInfo
  }
})