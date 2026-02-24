import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface AIChatMessage {
  id: string
  username: string
  content: string
  timestamp: Date
  type: 'user' | 'system' | 'ai'
  streaming?: boolean
  messageId?: string
}

export interface ChatMessage {
  id: string
  content: string
  senderId: string
  username: string
  avatar?: string
  timestamp: Date
  roomId: string
  type: 'text' | 'system' | 'command' | 'file'
  status: 'sending' | 'sent' | 'delivered' | 'read' | 'failed'
  metadata?: {
    commandId?: string
    fileUrl?: string
    fileName?: string
    fileSize?: number
  }
}

export interface ChatRoom {
  id: string
  name: string
  type: 'general' | 'admin' | 'terminal-control' | 'ai-assistance'
  participants: ChatUser[]
  unreadCount: number
  lastMessage?: ChatMessage
  isActive: boolean
  permissions: {
    canSendMessages: boolean
    canControlTerminal: boolean
    canViewHistory: boolean
  }
}

export interface ChatUser {
  id: string
  username: string
  avatar?: string
  role: 'user' | 'admin' | 'ai' | 'system'
  status: 'online' | 'offline' | 'away' | 'busy'
  permissions: {
    canControlTerminal: boolean
    canApproveCommands: boolean
    canViewLogs: boolean
  }
  lastSeen: Date
}

export const useChatStore = defineStore('chat', () => {
  // State
  const currentUser = ref<ChatUser>({
    id: '1',
    username: 'User',
    role: 'user',
    status: 'online',
    permissions: {
      canControlTerminal: false,
      canApproveCommands: false,
      canViewLogs: true,
    },
    lastSeen: new Date(),
  })

  const rooms = ref<ChatRoom[]>([
    {
      id: 'general',
      name: 'General Chat',
      type: 'general',
      participants: [],
      unreadCount: 0,
      isActive: true,
      permissions: {
        canSendMessages: true,
        canControlTerminal: false,
        canViewHistory: true,
      },
    },
    {
      id: 'terminal-control',
      name: 'Terminal Control',
      type: 'terminal-control',
      participants: [],
      unreadCount: 0,
      isActive: true,
      permissions: {
        canSendMessages: true,
        canControlTerminal: true,
        canViewHistory: true,
      },
    },
    {
      id: 'ai-assistance',
      name: 'AI Assistant',
      type: 'ai-assistance',
      participants: [],
      unreadCount: 0,
      isActive: true,
      permissions: {
        canSendMessages: true,
        canControlTerminal: false,
        canViewHistory: true,
      },
    },
  ])

  const messages = ref<Map<string, ChatMessage[]>>(new Map())
  const activeRoomId = ref('general')
  const isConnected = ref(false)
  const isReconnecting = ref(false)
  const typingUsers = ref<Map<string, string[]>>(new Map())

  // Initialize messages for each room
  rooms.value.forEach((room) => {
    messages.value.set(room.id, [])
  })

  // Getters
  const activeRoom = computed(() => rooms.value.find((room) => room.id === activeRoomId.value))

  const activeMessages = computed(() => messages.value.get(activeRoomId.value) || [])

  const totalUnreadCount = computed(() =>
    rooms.value.reduce((total, room) => total + room.unreadCount, 0)
  )

  const onlineUsers = computed(() =>
    rooms.value.flatMap((room) => room.participants).filter((user) => user.status === 'online')
  )

  const adminUsers = computed(() =>
    rooms.value.flatMap((room) => room.participants).filter((user) => user.role === 'admin')
  )

  // Actions
  const setCurrentUser = (user: Partial<ChatUser>) => {
    Object.assign(currentUser.value, user)
  }

  const setConnectionStatus = (connected: boolean) => {
    isConnected.value = connected
    if (connected) {
      isReconnecting.value = false
    }
  }

  const setReconnecting = (reconnecting: boolean) => {
    isReconnecting.value = reconnecting
  }

  const switchRoom = (roomId: string) => {
    const room = rooms.value.find((r) => r.id === roomId)
    if (room) {
      activeRoomId.value = roomId
      room.unreadCount = 0
    }
  }

  const addMessage = (roomId: string, message: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const newMessage: ChatMessage = {
      ...message,
      id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
      timestamp: new Date(),
    }

    const roomMessages = messages.value.get(roomId) || []
    roomMessages.push(newMessage)
    messages.value.set(roomId, roomMessages)

    // Update room's last message and unread count
    const room = rooms.value.find((r) => r.id === roomId)
    if (room) {
      room.lastMessage = newMessage
      if (roomId !== activeRoomId.value && message.senderId !== currentUser.value.id) {
        room.unreadCount++
      }
    }

    return newMessage
  }

  const sendMessage = (content: string, type: 'text' | 'command' = 'text', metadata?: any) => {
    const message = addMessage(activeRoomId.value, {
      content,
      senderId: currentUser.value.id,
      username: currentUser.value.username,
      avatar: currentUser.value.avatar,
      roomId: activeRoomId.value,
      type,
      status: 'sending',
      metadata,
    })

    return message
  }

  const updateMessageStatus = (messageId: string, status: ChatMessage['status']) => {
    for (const [roomId, roomMessages] of messages.value.entries()) {
      const message = roomMessages.find((m) => m.id === messageId)
      if (message) {
        message.status = status
        break
      }
    }
  }

  const addSystemMessage = (roomId: string, content: string, metadata?: any) => {
    return addMessage(roomId, {
      content,
      senderId: 'system',
      username: 'System',
      roomId,
      type: 'system',
      status: 'sent',
      metadata,
    })
  }

  const addCommandMessage = (roomId: string, command: string, commandId: string) => {
    return addMessage(roomId, {
      content: `Command: ${command}`,
      senderId: currentUser.value.id,
      username: currentUser.value.username,
      roomId,
      type: 'command',
      status: 'sent',
      metadata: { commandId },
    })
  }

  const addUserToRoom = (roomId: string, user: ChatUser) => {
    const room = rooms.value.find((r) => r.id === roomId)
    if (room) {
      const existingUser = room.participants.find((p) => p.id === user.id)
      if (!existingUser) {
        room.participants.push(user)
        addSystemMessage(roomId, `${user.username} joined the room`)
      } else {
        Object.assign(existingUser, user)
      }
    }
  }

  const removeUserFromRoom = (roomId: string, userId: string) => {
    const room = rooms.value.find((r) => r.id === roomId)
    if (room) {
      const userIndex = room.participants.findIndex((p) => p.id === userId)
      if (userIndex !== -1) {
        const user = room.participants[userIndex]
        room.participants.splice(userIndex, 1)
        addSystemMessage(roomId, `${user.username} left the room`)
      }
    }
  }

  const updateUserStatus = (userId: string, status: ChatUser['status']) => {
    rooms.value.forEach((room) => {
      const user = room.participants.find((p) => p.id === userId)
      if (user) {
        user.status = status
        user.lastSeen = new Date()
      }
    })
  }

  const setUserTyping = (roomId: string, userId: string, isTyping: boolean) => {
    const roomTypingUsers = typingUsers.value.get(roomId) || []

    if (isTyping) {
      if (!roomTypingUsers.includes(userId)) {
        roomTypingUsers.push(userId)
      }
    } else {
      const index = roomTypingUsers.indexOf(userId)
      if (index !== -1) {
        roomTypingUsers.splice(index, 1)
      }
    }

    typingUsers.value.set(roomId, roomTypingUsers)
  }

  const getTypingUsers = (roomId: string) => {
    const userIds = typingUsers.value.get(roomId) || []
    const room = rooms.value.find((r) => r.id === roomId)
    if (!room) return []

    return userIds
      .map((id) => room.participants.find((p) => p.id === id))
      .filter((user) => user && user.id !== currentUser.value.id)
  }

  const clearMessages = (roomId: string) => {
    messages.value.set(roomId, [])
  }

  const markAllAsRead = (roomId: string) => {
    const room = rooms.value.find((r) => r.id === roomId)
    if (room) {
      room.unreadCount = 0
    }
  }

  // AI Chat Messages (persisted across component mount/unmount)
  const aiMessages = ref<AIChatMessage[]>([])
  const isAITyping = ref(false)
  const currentAIMessageId = ref('')

  const addAIMessage = (
    username: string,
    content: string,
    type: 'user' | 'system' | 'ai' = 'user',
    messageId?: string,
  ): AIChatMessage => {
    const message: AIChatMessage = {
      id: Date.now().toString() + Math.random().toString(36).substr(2, 5),
      username,
      content,
      timestamp: new Date(),
      type,
      streaming: false,
      messageId,
    }
    aiMessages.value.push(message)
    return message
  }

  const addStreamingAIMessage = (messageId: string): AIChatMessage => {
    const message: AIChatMessage = {
      id: Date.now().toString() + Math.random().toString(36).substr(2, 5),
      username: 'Aether AI',
      content: '',
      timestamp: new Date(),
      type: 'ai',
      streaming: true,
      messageId,
    }
    aiMessages.value.push(message)
    currentAIMessageId.value = messageId
    isAITyping.value = true
    return message
  }

  const updateStreamingMessage = (messageId: string, chunk: string) => {
    const msg = aiMessages.value.find((m) => m.messageId === messageId)
    if (msg) {
      msg.content += chunk
    }
  }

  const completeStreamingMessage = (messageId: string, fullResponse: string) => {
    const msg = aiMessages.value.find((m) => m.messageId === messageId)
    if (msg) {
      msg.content = fullResponse
      msg.streaming = false
    }
    isAITyping.value = false
    currentAIMessageId.value = ''
  }

  const failStreamingMessage = (messageId: string, error: string) => {
    const msg = aiMessages.value.find((m) => m.messageId === messageId)
    if (msg) {
      msg.content = `Sorry, I encountered an error: ${error}`
      msg.streaming = false
      msg.type = 'system'
    }
    isAITyping.value = false
    currentAIMessageId.value = ''
  }

  return {
    // State
    currentUser,
    rooms,
    messages,
    activeRoomId,
    isConnected,
    isReconnecting,
    typingUsers,

    // Getters
    activeRoom,
    activeMessages,
    totalUnreadCount,
    onlineUsers,
    adminUsers,

    // Actions
    setCurrentUser,
    setConnectionStatus,
    setReconnecting,
    switchRoom,
    addMessage,
    sendMessage,
    updateMessageStatus,
    addSystemMessage,
    addCommandMessage,
    addUserToRoom,
    removeUserFromRoom,
    updateUserStatus,
    setUserTyping,
    getTypingUsers,
    clearMessages,
    markAllAsRead,

    // AI Chat Messages
    aiMessages,
    isAITyping,
    currentAIMessageId,
    addAIMessage,
    addStreamingAIMessage,
    updateStreamingMessage,
    completeStreamingMessage,
    failStreamingMessage,
  }
})
