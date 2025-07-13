import { defineStore } from 'pinia'
import { Socket } from 'socket.io-client'
import { computed, ref } from 'vue'

export interface TerminalCommand {
  id: string
  command: string
  timestamp: Date
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  riskLevel: 'low' | 'medium' | 'high' | 'critical'
  aiSuggestion?: string
  rejectionReason?: string
  source: 'user' | 'admin' | 'ai'
}

export interface TerminalSession {
  id: string
  isActive: boolean
  isPaused: boolean
  isReconnecting: boolean
  lastActivity: Date
  supervisorControlled: boolean
  aiMonitoring: boolean
}

export interface ConnectionState {
  isConnected: boolean
  isConnecting: boolean
  isReconnecting: boolean
  reconnectAttempts: number
  maxReconnectAttempts: number
  lastConnected?: Date
  lastDisconnected?: Date
  connectionError?: string
  latency: number
}

export interface AIMonitoringState {
  isActive: boolean
  monitoringRules: string[]
  currentProcedure?: string
  procedureStep: number
  totalSteps: number
  lastAnalysis?: Date
  riskAssessment: 'low' | 'medium' | 'high' | 'critical'
  suggestedActions: string[]
}

export const useAetherTerminalServiceStore = defineStore('aetherTerminalService', () => {
  // Connection State
  const connectionState = ref<ConnectionState>({
    isConnected: false,
    isConnecting: false,
    isReconnecting: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    latency: 0,
  })

  const socket = ref<Socket | null>(null)

  // Terminal State - Empty initial session, will be set by terminal tabs
  const session = ref<TerminalSession>({
    id: '',  // Will be set by individual terminal tabs
    isActive: false,
    isPaused: false,
    isReconnecting: false,
    lastActivity: new Date(),
    supervisorControlled: false,
    aiMonitoring: true,
  })

  const pendingCommands = ref<TerminalCommand[]>([])
  const commandHistory = ref<TerminalCommand[]>([])
  const outputBuffer = ref<string[]>([])
  const isSupervisorLocked = ref(false)

  // AI Monitoring State
  const aiMonitoring = ref<AIMonitoringState>({
    isActive: true,
    monitoringRules: [
      'System file modification detection',
      'Privilege escalation monitoring',
      'Network configuration changes',
      'Service management operations',
      'Data destruction prevention',
    ],
    currentProcedure: 'System maintenance checklist',
    procedureStep: 1,
    totalSteps: 5,
    lastAnalysis: new Date(),
    riskAssessment: 'low',
    suggestedActions: [],
  })

  // Dynamic dangerous commands (managed by AI)
  const dangerousCommands = ref<string[]>([])

  // Event Callbacks
  const eventCallbacks = ref<{
    onShellOutput: ((data: string) => void)[]
    onChatMessage: ((data: any) => void)[]
    onAskAI: ((text: string) => void)[]
  }>({
    onShellOutput: [],
    onChatMessage: [],
    onAskAI: [],
  })

  // Getters
  const hasPendingCommands = computed(() => pendingCommands.value.length > 0)
  const isTerminalBlocked = computed(
    () =>
      session.value.isPaused ||
      session.value.isReconnecting ||
      hasPendingCommands.value ||
      !connectionState.value.isConnected
  )
  const criticalCommandsPending = computed(() =>
    pendingCommands.value.filter((cmd) => cmd.riskLevel === 'critical')
  )
  const connectionStatus = computed(() => {
    if (connectionState.value.isConnected) return 'connected'
    if (connectionState.value.isConnecting) return 'connecting'
    if (connectionState.value.isReconnecting) return 'reconnecting'
    return 'disconnected'
  })

  // Connection Actions
  const setSocket = (socketInstance: Socket) => {
    socket.value = socketInstance
  }

  const setupSocketListeners = () => {
    if (!socket.value) return

    const socketInstance = socket.value as Socket

    // Connection events
    socketInstance.on('connect', () => {
      console.log('🟢 STORE: Socket connected with ID:', socketInstance.id)
      connectionState.value.isConnected = true
      connectionState.value.isConnecting = false
      connectionState.value.isReconnecting = false
      connectionState.value.reconnectAttempts = 0
      connectionState.value.lastConnected = new Date()
      connectionState.value.connectionError = undefined

      addToOutput('[SYSTEM] Connected to AetherTerm service')

      // Terminal creation is now handled by workspace system
      // No need to create a default terminal here
    })

    socketInstance.on('disconnect', (reason: string) => {
      connectionState.value.isConnected = false
      connectionState.value.lastDisconnected = new Date()
      connectionState.value.connectionError = reason

      addToOutput(`[SYSTEM] Disconnected from AetherTerm service: ${reason}`)

      // Start reconnection if not intentional
      if (reason !== 'io client disconnect') {
        startReconnection()
      }
    })

    socketInstance.on('reconnect', (attemptNumber: number) => {
      connectionState.value.isReconnecting = false
      connectionState.value.reconnectAttempts = attemptNumber
      addToOutput(`[SYSTEM] Reconnected after ${attemptNumber} attempts`)
    })

    socketInstance.on('reconnect_attempt', (attemptNumber: number) => {
      connectionState.value.reconnectAttempts = attemptNumber
      addToOutput(`[SYSTEM] Reconnection attempt ${attemptNumber}`)
    })

    socketInstance.on('reconnect_failed', () => {
      connectionState.value.isReconnecting = false
      connectionState.value.connectionError = 'Max reconnection attempts reached'
      addToOutput('[SYSTEM] Failed to reconnect after maximum attempts')
    })

    socketInstance.on('connect_error', (error: Error) => {
      connectionState.value.connectionError = error.message
      addToOutput(`[SYSTEM] Connection error: ${error.message}`)
    })

    // Terminal events - using the correct event names from server
    socketInstance.on('terminal_output', (data: any) => {
      if (data && data.data) {
        // Pass directly to xterm callbacks without adding to buffer
        eventCallbacks.value.onShellOutput.forEach((callback) => callback(data.data))
      }
    })

    socketInstance.on('terminal_ready', (data: any) => {
      session.value.id = data.session || ''
      session.value.isActive = true
      console.log('✅ STORE: Terminal ready - session:', session.value.id)
    })

    socketInstance.on('terminal_error', (data: any) => {
      console.log('Terminal error:', data)
      addToOutput(`[ERROR] ${data.error || 'Unknown terminal error'}`)
    })

    // terminal_closed event is now handled by aetherTerminalStore.ts

    // Legacy events for compatibility
    socketInstance.on('shell_output', (data: string) => {
      eventCallbacks.value.onShellOutput.forEach((callback) => callback(data))
    })

    // Admin control events
    socketInstance.on('admin_pause_terminal', (data: any) => {
      console.log('Received admin_pause_terminal event', data)
      pauseTerminal(data.reason)
    })

    socketInstance.on('admin_resume_terminal', () => {
      console.log('Received admin_resume_terminal event')
      resumeTerminal()
    })

    socketInstance.on('command_approval', (data: any) => {
      if (data.approved) {
        approveCommand(data.commandId)
      } else {
        rejectCommand(data.commandId, data.reason || 'Rejected by admin')
      }
    })

    // Chat events
    socketInstance.on('chat_message', (data: any) => {
      eventCallbacks.value.onChatMessage.forEach((callback) => callback(data))
    })
  }

  const startReconnection = () => {
    if (connectionState.value.reconnectAttempts >= connectionState.value.maxReconnectAttempts) {
      return
    }

    connectionState.value.isReconnecting = true
    session.value.isReconnecting = true
    addToOutput('[SYSTEM] Starting reconnection process...')
  }

  const connect = (): Promise<boolean> => {
    
    return new Promise((resolve) => {
      if (connectionState.value.isConnected) {
        resolve(true)
        return
      }
      
      if (connectionState.value.isConnecting) {
        // Already connecting, wait for result
        return new Promise((resolve) => {
          const checkConnection = () => {
            if (connectionState.value.isConnected) {
              resolve(true)
            } else if (!connectionState.value.isConnecting) {
              resolve(false)
            } else {
              // Check again in next tick
              setTimeout(checkConnection, 50)
            }
          }
          checkConnection()
        })
        return
      }

      connectionState.value.isConnecting = true
      addToOutput('[SYSTEM] Connecting to AetherTerm service...')

      // Setup socket listeners and initiate connection if socket exists
      if (socket.value) {
        
        // Set up one-time connection handler
        const handleConnect = () => {
          socket.value?.off('connect', handleConnect)
          socket.value?.off('connect_error', handleError)
          resolve(true)
        }
        
        const handleError = (error: Error) => {
          console.error('❌ STORE: Connection error:', error)
          socket.value?.off('connect', handleConnect)
          socket.value?.off('connect_error', handleError)
          connectionState.value.isConnecting = false
          resolve(false)
        }
        
        // Listen for connection events
        socket.value.once('connect', handleConnect)
        socket.value.once('connect_error', handleError)
        
        setupSocketListeners()
        // Explicitly connect if not already connected
        if (!socket.value.connected) {
          socket.value.connect()
        } else {
          resolve(true)
        }
        
        // Timeout after 10 seconds
        setTimeout(() => {
          socket.value?.off('connect', handleConnect)
          socket.value?.off('connect_error', handleError)
          if (!connectionState.value.isConnected) {
            connectionState.value.isConnecting = false
            resolve(false)
          }
        }, 10000)
      } else {
        console.error('❌ STORE: No socket available!')
        connectionState.value.isConnecting = false
        resolve(false)
      }
    })
  }

  // Event Registration
  const onShellOutput = (callback: (data: string) => void) => {
    eventCallbacks.value.onShellOutput.push(callback)
  }

  const onChatMessage = (callback: (data: any) => void) => {
    eventCallbacks.value.onChatMessage.push(callback)
  }

  // Event Cleanup
  const offShellOutput = (callback?: (data: string) => void) => {
    if (callback) {
      const index = eventCallbacks.value.onShellOutput.indexOf(callback)
      if (index !== -1) {
        eventCallbacks.value.onShellOutput.splice(index, 1)
      }
    } else {
      eventCallbacks.value.onShellOutput = []
    }
  }

  const offChatMessage = (callback?: (data: any) => void) => {
    if (callback) {
      const index = eventCallbacks.value.onChatMessage.indexOf(callback)
      if (index !== -1) {
        eventCallbacks.value.onChatMessage.splice(index, 1)
      }
    } else {
      eventCallbacks.value.onChatMessage = []
    }
  }

  // Terminal output callback management
  const terminalOutputCallbacks = ref<Map<string, Array<(data: string) => void>>>(new Map())

  const addTerminalOutputCallback = (sessionId: string, callback: (data: string) => void) => {
    if (!terminalOutputCallbacks.value.has(sessionId)) {
      terminalOutputCallbacks.value.set(sessionId, [])
    }
    terminalOutputCallbacks.value.get(sessionId)?.push(callback)
  }

  const removeTerminalOutputCallback = (sessionId: string, callback: (data: string) => void) => {
    const callbacks = terminalOutputCallbacks.value.get(sessionId)
    if (callbacks) {
      const index = callbacks.indexOf(callback)
      if (index !== -1) {
        callbacks.splice(index, 1)
      }
      if (callbacks.length === 0) {
        terminalOutputCallbacks.value.delete(sessionId)
      }
    }
  }

  // Ask AI Event Handling
  const onAskAI = (callback: (text: string) => void) => {
    eventCallbacks.value.onAskAI.push(callback)
  }

  const offAskAI = (callback?: (text: string) => void) => {
    if (callback) {
      const index = eventCallbacks.value.onAskAI.indexOf(callback)
      if (index !== -1) {
        eventCallbacks.value.onAskAI.splice(index, 1)
      }
    } else {
      eventCallbacks.value.onAskAI = []
    }
  }

  const triggerAskAI = (selectedText: string) => {
    eventCallbacks.value.onAskAI.forEach(callback => callback(selectedText))
  }

  // Terminal Actions
  const initializeSession = (sessionId: string) => {
    session.value.id = sessionId
    session.value.isActive = true
    session.value.lastActivity = new Date()
    addToOutput(`[SYSTEM] Terminal session initialized: ${sessionId}`)
  }

  const pauseTerminal = (reason: string) => {
    session.value.isPaused = true
    isSupervisorLocked.value = true
    addToOutput(`[SYSTEM] Terminal paused: ${reason}`)
  }

  const resumeTerminal = () => {
    session.value.isPaused = false
    isSupervisorLocked.value = false
    addToOutput('[SYSTEM] Terminal resumed')
  }

  const analyzeCommand = (command: string): TerminalCommand => {
    const commandId = Date.now().toString()
    let riskLevel: 'low' | 'medium' | 'high' | 'critical' = 'low'
    let aiSuggestion = ''

    // Check for dangerous commands
    const isDangerous = dangerousCommands.value.some((dangerous) =>
      command.toLowerCase().includes(dangerous.toLowerCase())
    )

    if (isDangerous) {
      riskLevel = 'critical'
      aiSuggestion =
        'This command may cause system damage or data loss. Consider using safer alternatives.'
    } else if (command.includes('sudo')) {
      riskLevel = 'high'
      aiSuggestion =
        'This command requires elevated privileges. Ensure you understand its implications.'
    } else if (command.includes('chmod') || command.includes('chown')) {
      riskLevel = 'medium'
      aiSuggestion =
        'This command modifies file permissions. Verify the target files and permissions.'
    }

    return {
      id: commandId,
      command,
      timestamp: new Date(),
      status: riskLevel === 'critical' ? 'pending' : 'approved',
      riskLevel,
      aiSuggestion,
      source: 'user',
    }
  }

  const submitCommand = (command: string): boolean => {
    const analyzedCommand = analyzeCommand(command)

    if (analyzedCommand.status === 'pending') {
      pendingCommands.value.push(analyzedCommand)
      addToOutput(`[AI] Command blocked for review: ${command}`)
      addToOutput(`[AI] Reason: ${analyzedCommand.aiSuggestion}`)

      // Notify admin via socket
      if (socket.value) {
        socket.value.emit('command_review_required', {
          commandId: analyzedCommand.id,
          command: analyzedCommand.command,
          riskLevel: analyzedCommand.riskLevel,
          aiSuggestion: analyzedCommand.aiSuggestion,
        })
      }

      return false
    }

    commandHistory.value.push(analyzedCommand)
    session.value.lastActivity = new Date()

    // Send command to server
    if (socket.value) {
      socket.value.emit('terminal_command', {
        command: analyzedCommand.command,
        commandId: analyzedCommand.id,
      })
    }

    return true
  }

  // Send raw input to terminal
  const sendInput = (input: string) => {
    session.value.lastActivity = new Date()

    if (socket.value) {
      socket.value.emit('terminal_input', {
        session: session.value.id,
        data: input,
      })
    }
  }

  const approveCommand = (commandId: string) => {
    const commandIndex = pendingCommands.value.findIndex((cmd) => cmd.id === commandId)
    if (commandIndex !== -1) {
      const command = pendingCommands.value[commandIndex]
      command.status = 'approved'
      commandHistory.value.push(command)
      pendingCommands.value.splice(commandIndex, 1)
      addToOutput(`[ADMIN] Command approved: ${command.command}`)

      // Execute the approved command
      if (socket.value) {
        socket.value.emit('terminal_command', {
          command: command.command,
          commandId: command.id,
        })
      }

      return command
    }
    return null
  }

  const rejectCommand = (commandId: string, reason: string) => {
    const commandIndex = pendingCommands.value.findIndex((cmd) => cmd.id === commandId)
    if (commandIndex !== -1) {
      const command = pendingCommands.value[commandIndex]
      command.status = 'rejected'
      command.rejectionReason = reason
      commandHistory.value.push(command)
      pendingCommands.value.splice(commandIndex, 1)
      addToOutput(`[ADMIN] Command rejected: ${command.command}`)
      addToOutput(`[ADMIN] Reason: ${reason}`)
    }
  }

  const sendChatMessage = (message: any) => {
    if (socket.value) {
      socket.value.emit('chat_message', message)
    }
  }

  const sendResize = (cols: number, rows: number) => {
    if (socket.value && session.value.id) {
      console.log(`Sending terminal resize: ${cols}x${rows} for session ${session.value.id}`)
      socket.value.emit('terminal_resize', {
        session: session.value.id,
        cols: cols,
        rows: rows,
      })
    }
  }

  const addToOutput = (text: string) => {
    console.log('addToOutput called with:', text)
    outputBuffer.value.push(`[${new Date().toLocaleTimeString()}] ${text}`)
    // Keep only last 1000 lines
    if (outputBuffer.value.length > 1000) {
      outputBuffer.value = outputBuffer.value.slice(-1000)
    }
  }

  return {
    // State
    connectionState,
    socket,
    session,
    pendingCommands,
    commandHistory,
    outputBuffer,
    isSupervisorLocked,
    dangerousCommands,
    aiMonitoring,

    // Getters
    hasPendingCommands,
    isTerminalBlocked,
    criticalCommandsPending,
    connectionStatus,

    // Connection Actions
    connect,
    startReconnection,

    // Event Registration
    onShellOutput,
    onChatMessage,
    onAskAI,

    // Event Cleanup
    offShellOutput,
    offChatMessage,
    offAskAI,

    // Ask AI Actions
    triggerAskAI,

    // Terminal Actions
    initializeSession,
    pauseTerminal,
    resumeTerminal,
    analyzeCommand,
    submitCommand,
    sendInput,
    approveCommand,
    rejectCommand,
    sendChatMessage,
    sendResize,
    addToOutput,
    setSocket,
    addTerminalOutputCallback,
    removeTerminalOutputCallback,
  }
})
