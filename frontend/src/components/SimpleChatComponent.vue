<template>
  <div class="simple-chat-container">
    <div class="chat-header">
      <h3>Aether Assistant</h3>
      <div class="status-info">
        <div class="ai-info" v-if="aiInfo.provider && aiInfo.provider !== 'unknown'">
          <span class="provider">{{ aiInfo.provider }}</span>
          <span class="model" v-if="aiInfo.model && aiInfo.model !== 'unknown'">{{
            aiInfo.model
          }}</span>
        </div>
        <div
          class="connection-status"
          :class="{ connected: terminalStore.connectionState.isConnected && aiInfo.available }"
        >
          {{ getConnectionStatus() }}
        </div>
        
        <!-- Retry Status Display -->
        <div v-if="aiInfo.retry_status && aiInfo.retry_status.attempt > 0" class="retry-status">
          <div class="retry-info">
            <span class="retry-label">Retry:</span>
            <span class="retry-attempt">{{ aiInfo.retry_status.attempt }}/{{ aiInfo.retry_status.max_attempts }}</span>
            <span v-if="aiInfo.retry_status.next_delay > 0" class="retry-delay">
              Next: {{ aiInfo.retry_status.next_delay.toFixed(1) }}s
            </span>
          </div>
          <button 
            @click="resetAIRetry" 
            class="retry-reset-btn"
            title="Reset retry attempts"
          >
            Reset
          </button>
        </div>
      </div>
    </div>

    <div class="chat-messages" ref="messagesContainer">
      <div v-for="message in messages" :key="message.id" class="message" :class="message.type">
        <div class="message-header">
          <span class="username">{{ message.username }}</span>
          <span class="timestamp">{{ formatTime(message.timestamp) }}</span>
        </div>
        <div class="message-content">
          <span v-if="message.streaming" class="streaming-content"
            >{{ message.content }}<span class="cursor">|</span></span
          >
          <div v-else>
            {{ message.content }}
            
            <!-- Command suggestions for AI messages -->
            <div v-if="message.type === 'ai' && extractCommands(message.content).length > 0" class="command-suggestions">
              <div class="commands-header">
                <span>🤖 Suggested Commands:</span>
              </div>
              <div class="commands-list">
                <div 
                  v-for="(command, index) in extractCommands(message.content)" 
                  :key="index"
                  class="command-item"
                >
                  <code class="command-text">{{ command }}</code>
                  <button 
                    @click="sendCommandToTerminal(command)"
                    class="send-command-btn"
                    :title="`Send '${command}' to terminal`"
                  >
                    📤 Send
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI Typing Indicator -->
      <div v-if="isAITyping" class="ai-typing">
        <div class="typing-indicator">
          <span class="username">Aether AI</span>
          <div class="typing-dots"><span></span><span></span><span></span></div>
        </div>
      </div>

      <div v-if="messages.length === 0" class="no-messages">
        <p>No messages yet. Start a conversation with Aether AI!</p>
      </div>
    </div>

    <div class="chat-input">
      <textarea
        v-model="newMessage"
        @keydown.ctrl.enter="sendMessage"
        @keydown.meta.enter="sendMessage"
        :placeholder="placeholderText"
        :disabled="!isInputAvailable"
        class="message-input"
        rows="3"
        ref="messageTextarea"
      ></textarea>
      <div class="input-actions">
        <div class="input-help">
          <small>{{ helpText }}</small>
        </div>
        <button
          @click="sendMessage"
          :disabled="!newMessage.trim() || !isInputAvailable"
          class="send-button"
        >
          Send
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { nextTick, onMounted, onUnmounted, ref, computed } from 'vue'
  import { useAetherTerminalStore } from '../stores/aetherTerminalStore'
  import type { ChatMessageData, AIChatTypingData, AIChatChunkData, AIChatCompleteData, AIChatErrorData } from '@/types/common'

  interface ChatMessage {
    id: string
    username: string
    content: string
    timestamp: Date
    type: 'user' | 'system' | 'ai'
    streaming?: boolean
    messageId?: string
  }

  const terminalStore = useAetherTerminalStore()
  const messages = ref<ChatMessage[]>([])
  const newMessage = ref('')
  const messagesContainer = ref<HTMLElement | null>(null)
  const messageTextarea = ref<HTMLTextAreaElement | null>(null)

  interface AIInfo {
    provider: string
    model: string
    available: boolean
    status: string
    error?: string
    retry_status?: {
      attempt: number
      max_attempts: number
      next_delay: number
      last_error: string | null
      can_retry: boolean
    }
  }

  const aiInfo = ref<AIInfo>({
    provider: 'unknown',
    model: 'unknown',
    available: false,
    status: 'disconnected',
  })

  // Computed properties for input availability and dynamic text
  const isInputAvailable = computed(() => {
    return terminalStore.connectionState.isConnected && aiInfo.value.available
  })

  const placeholderText = computed(() => {
    if (!terminalStore.connectionState.isConnected) {
      return 'Terminal disconnected - cannot send messages'
    }
    if (!aiInfo.value.available) {
      return 'AI unavailable - please wait for connection'
    }
    return 'Type a message... (Ctrl+Enter to send)'
  })

  const helpText = computed(() => {
    if (!terminalStore.connectionState.isConnected) {
      return 'Connect to terminal first'
    }
    if (!aiInfo.value.available) {
      return 'Waiting for AI connection'
    }
    return 'Ctrl+Enter to send'
  })

  const addMessage = (
    username: string,
    content: string,
    type: 'user' | 'system' | 'ai' = 'user'
  ): ChatMessage => {
    const message: ChatMessage = {
      id: Date.now().toString(),
      username,
      content,
      timestamp: new Date(),
      type,
    }

    messages.value.push(message)

    // Auto-scroll to bottom
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })

    return message
  }

  const sendMessage = () => {
    if (!newMessage.value.trim() || !isInputAvailable.value) {
      // Provide appropriate error messages when unable to send
      if (!terminalStore.connectionState.isConnected) {
        addMessage('System', 'Cannot send message: Terminal not connected', 'system')
      } else if (!aiInfo.value.available) {
        addMessage('System', 'Cannot send message: AI service unavailable', 'system')
      }
      return
    }

    const userMessage = newMessage.value.trim()

    // Add user message to local display
    addMessage('You', userMessage, 'user')

    // Send to AI for response
    sendAIMessage(userMessage)

    newMessage.value = ''

    // Focus back to textarea
    nextTick(() => {
      messageTextarea.value?.focus()
    })
  }

  const isAITyping = ref(false)
  const currentAIMessageId = ref('')

  const sendAIMessage = async (userMessage: string) => {
    if (!terminalStore.socket || !terminalStore.connectionState.isConnected) {
      console.warn('Socket not available for AI chat')
      addMessage('System', 'Cannot send message: Terminal connection unavailable', 'system')
      return
    }

    if (!aiInfo.value.available) {
      console.warn('AI service not available')
      addMessage('System', 'Cannot send message: AI service unavailable. Please wait for AI to connect.', 'system')
      return
    }

    // Generate unique message ID
    const messageId = Date.now().toString() + Math.random().toString(36).substr(2, 9)
    currentAIMessageId.value = messageId

    // Create placeholder AI message
    const aiMessage = addMessage('Aether AI', '', 'ai')
    aiMessage.streaming = true
    aiMessage.messageId = messageId

    isAITyping.value = true

    // Send to AI service with terminal context
    terminalStore.socket.emit('ai_chat_message', {
      message: userMessage,
      message_id: messageId,
      session_id: terminalStore.session.id,
      stream: true
    })
  }

  // Handle external messages (Ask AI from terminal selection)
  const handleExternalMessage = (message: string) => {
    console.log('SimpleChatComponent: Received external message:', message)
    
    // Add user message to local display
    addMessage('Terminal Selection', message, 'user')
    
    // Send to AI for response
    sendAIMessage(message)
  }

  // Expose method for external use
  defineExpose({
    handleExternalMessage
  })

  // Handle AI streaming responses
  onMounted(() => {
    // Add welcome message
    addMessage(
      'Aether AI',
      'Welcome to Aether Assistant! I am your AI assistant for terminal operations, troubleshooting, and guidance.',
      'system'
    )

    // Listen for chat messages from socket
    terminalStore.onChatMessage((data: ChatMessageData) => {
      console.log('Received chat message:', data)
      addMessage(data.username || 'Unknown User', data.message || data.content, 'user')
    })

    // Listen for Ask AI events from Spine
    terminalStore.onAskAI((selectedText: string) => {
      console.log('SimpleChatComponent: Received Ask AI event:', selectedText)
      const message = `Please analyze this terminal output: "${selectedText}"`
      handleExternalMessage(message)
    })

    // Set up AI Event Listeners when socket becomes available
    const setupAIListeners = () => {
      if (!terminalStore.socket) return

      // Remove existing listeners first to prevent duplicates
      terminalStore.socket.off('ai_chat_typing')
      terminalStore.socket.off('ai_chat_chunk')
      terminalStore.socket.off('ai_chat_complete')
      terminalStore.socket.off('ai_chat_error')
      terminalStore.socket.off('ai_info_response')
      terminalStore.socket.off('ai_reset_retry_response')

      // AI typing indicator
      terminalStore.socket.on('ai_chat_typing', (data: AIChatTypingData) => {
        isAITyping.value = data.typing
      })

      // AI response chunks
      terminalStore.socket.on('ai_chat_chunk', (data: AIChatChunkData) => {
        const messageId = data.message_id
        const chunk = data.chunk

        // Find the AI message and append chunk
        const aiMessage = messages.value.find((m) => m.messageId === messageId)
        if (aiMessage) {
          aiMessage.content += chunk

          // Auto-scroll to bottom
          nextTick(() => {
            if (messagesContainer.value) {
              messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
            }
          })
        }
      })

      // AI response complete
      terminalStore.socket.on('ai_chat_complete', (data: AIChatCompleteData) => {
        const messageId = data.message_id
        const fullResponse = data.full_response

        // Find the AI message and finalize
        const aiMessage = messages.value.find((m) => m.messageId === messageId)
        if (aiMessage) {
          aiMessage.content = fullResponse
          aiMessage.streaming = false
        }

        isAITyping.value = false
        currentAIMessageId.value = ''
      })

      // AI error handling
      terminalStore.socket.on('ai_chat_error', (data: AIChatErrorData) => {
        const messageId = data.message_id
        const error = data.error

        // Find the AI message and show error
        const aiMessage = messages.value.find((m) => m.messageId === messageId)
        if (aiMessage) {
          aiMessage.content = `Sorry, I encountered an error: ${error}`
          aiMessage.streaming = false
          aiMessage.type = 'system' // Mark as system message for error styling
        }

        isAITyping.value = false
        currentAIMessageId.value = ''
      })

      // AI info response
      terminalStore.socket.on('ai_info_response', (data: any) => {
        aiInfo.value = {
          provider: data.provider || 'unknown',
          model: data.model || 'unknown',
          available: data.available || false,
          status: data.status || 'disconnected',
          error: data.error,
          retry_status: data.retry_status,
        }

        console.log('AI Info received:', aiInfo.value)
      })
      
      // AI reset retry response
      terminalStore.socket.on('ai_reset_retry_response', (data: any) => {
        if (data.success) {
          addMessage('System', data.message, 'system')
        }
      })
    }

    // Try to setup listeners immediately
    setupAIListeners()

    // Watch for connection state changes without using $subscribe
    let isListenersSetup = false
    const watchConnection = () => {
      if (terminalStore.connectionState.isConnected && terminalStore.socket && !isListenersSetup) {
        setupAIListeners()
        requestAIInfo() // Request AI info when connection is established
        isListenersSetup = true
      }
    }

    // Set up a simple interval check instead of reactive subscription
    const connectionWatcher = setInterval(watchConnection, 1000)

    // Clean up on unmount
    onUnmounted(() => {
      clearInterval(connectionWatcher)
      terminalStore.offChatMessage()
      terminalStore.offAskAI()

      // Clean up socket listeners
      if (terminalStore.socket) {
        terminalStore.socket.off('ai_chat_typing')
        terminalStore.socket.off('ai_chat_chunk')
        terminalStore.socket.off('ai_chat_complete')
        terminalStore.socket.off('ai_chat_error')
        terminalStore.socket.off('ai_info_response')
        terminalStore.socket.off('ai_reset_retry_response')
      }
    })
  })

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const getConnectionStatus = () => {
    if (!terminalStore.connectionState.isConnected) {
      return 'Terminal Disconnected'
    }
    if (!aiInfo.value.available) {
      return 'AI Unavailable'
    }
    return 'Connected'
  }

  const requestAIInfo = () => {
    if (terminalStore.socket && terminalStore.connectionState.isConnected) {
      terminalStore.socket.emit('ai_get_info', {})
    }
  }

  const resetAIRetry = () => {
    if (terminalStore.socket && terminalStore.connectionState.isConnected) {
      terminalStore.socket.emit('ai_reset_retry', {})
    }
  }

  // Extract command suggestions from AI message content
  const extractCommands = (content: string): string[] => {
    if (!content) return []
    
    const commands: string[] = []
    
    // Look for code blocks with common command patterns
    const codeBlockPattern = /```(?:bash|shell|sh)?\s*\n?(.*?)\n?```/gis
    const matches = content.match(codeBlockPattern)
    
    if (matches) {
      matches.forEach(match => {
        // Remove the code block markers and get the content
        const cleanMatch = match.replace(/```(?:bash|shell|sh)?\s*\n?|\n?```/gi, '').trim()
        if (cleanMatch && isValidCommand(cleanMatch)) {
          // Split by lines and add each non-empty line as a command
          const lines = cleanMatch.split('\n').map(line => line.trim()).filter(line => line)
          commands.push(...lines)
        }
      })
    }
    
    // Also look for inline code with command patterns
    const inlineCodePattern = /`([^`]+)`/g
    let inlineMatch
    while ((inlineMatch = inlineCodePattern.exec(content)) !== null) {
      const cmd = inlineMatch[1].trim()
      if (isValidCommand(cmd) && !commands.includes(cmd)) {
        commands.push(cmd)
      }
    }
    
    return commands.slice(0, 5) // Limit to 5 commands max
  }

  // Check if a string looks like a valid terminal command
  const isValidCommand = (cmd: string): boolean => {
    if (!cmd || cmd.length < 2 || cmd.length > 200) return false
    
    // Common command patterns
    const commonCommands = [
      'ls', 'cd', 'pwd', 'mkdir', 'rmdir', 'rm', 'cp', 'mv', 'touch', 'cat', 'less', 'more',
      'grep', 'find', 'which', 'whereis', 'locate', 'du', 'df', 'ps', 'top', 'htop',
      'kill', 'killall', 'jobs', 'nohup', 'screen', 'tmux', 'chmod', 'chown', 'chgrp',
      'tar', 'gzip', 'gunzip', 'zip', 'unzip', 'wget', 'curl', 'ssh', 'scp', 'rsync',
      'git', 'docker', 'npm', 'yarn', 'pip', 'apt', 'yum', 'brew', 'systemctl', 'service',
      'sudo', 'su', 'whoami', 'id', 'groups', 'history', 'echo', 'printf', 'date',
      'uptime', 'uname', 'hostname', 'w', 'who', 'last', 'crontab', 'at', 'watch'
    ]
    
    // Get the first word (command name)
    const firstWord = cmd.split(/\s+/)[0].toLowerCase()
    
    // Check if it starts with a common command or contains typical command characters
    return commonCommands.some(cmd => firstWord.startsWith(cmd)) ||
           /^[a-zA-Z][a-zA-Z0-9_-]*(\s|$)/.test(cmd) ||
           /^\.\/[a-zA-Z0-9_.-]+/.test(cmd) ||
           /^~?\/[a-zA-Z0-9_.-/]+/.test(cmd)
  }

  // Send command to terminal
  const sendCommandToTerminal = (command: string) => {
    if (!terminalStore.connectionState.isConnected) {
      addMessage('System', 'Cannot send command: Terminal not connected', 'system')
      return
    }

    // Add the command with a newline to execute it
    const commandWithNewline = command + '\r'
    
    // Send the command to terminal
    terminalStore.sendInput(commandWithNewline)
    
    // Add a confirmation message to the chat
    addMessage('System', `Command sent to terminal: ${command}`, 'system')
    
    console.log('Command sent to terminal:', command)
  }
</script>

<style scoped>
  .simple-chat-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    background-color: #2d2d2d;
    color: #ffffff;
  }

  .chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px;
    border-bottom: 1px solid #444;
    background-color: #1e1e1e;
  }

  .chat-header h3 {
    margin: 0;
    color: #4caf50;
    font-size: 16px;
  }

  .status-info {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }

  .ai-info {
    display: flex;
    gap: 6px;
    font-size: 11px;
    color: #888;
  }

  .ai-info .provider {
    background-color: #424242;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
    text-transform: uppercase;
  }

  .ai-info .model {
    background-color: #616161;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
  }

  .connection-status {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    background-color: #f44336;
    color: white;
  }

  .connection-status.connected {
    background-color: #4caf50;
  }

  /* Retry Status Styling */
  .retry-status {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 5px;
    padding: 6px 10px;
    background-color: #ff6b35;
    border-radius: 4px;
    font-size: 12px;
  }

  .retry-info {
    display: flex;
    align-items: center;
    gap: 8px;
    color: white;
  }

  .retry-label {
    font-weight: bold;
  }

  .retry-attempt {
    background-color: rgba(0, 0, 0, 0.2);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
  }

  .retry-delay {
    font-style: italic;
    opacity: 0.9;
  }

  .retry-reset-btn {
    background-color: rgba(255, 255, 255, 0.2);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
  }

  .retry-reset-btn:hover {
    background-color: rgba(255, 255, 255, 0.3);
    border-color: rgba(255, 255, 255, 0.5);
    transform: translateY(-1px);
  }

  .retry-reset-btn:active {
    transform: translateY(0);
  }

  .chat-messages {
    flex: 1;
    padding: 15px;
    overflow-y: auto;
    min-height: 0; /* flexで縮小可能にする */
  }

  .message {
    margin-bottom: 15px;
    padding: 10px;
    border-radius: 8px;
    background-color: #3d3d3d;
  }

  .message.system {
    background-color: #1976d2;
  }

  .message.ai {
    background-color: #9c27b0;
  }

  .message-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 5px;
  }

  .username {
    font-weight: bold;
    color: #4caf50;
    font-size: 14px;
  }

  .timestamp {
    color: #ccc;
    font-size: 12px;
  }

  .message-content {
    line-height: 1.4;
    color: #e0e0e0;
  }

  .no-messages {
    text-align: center;
    color: #666;
    margin-top: 50px;
  }

  .chat-input {
    padding: 15px;
    border-top: 1px solid #444;
    background-color: #1e1e1e;
    box-sizing: border-box;
    overflow-x: hidden; /* 横スクロールを防ぐ */
  }

  .message-input {
    width: 100%;
    padding: 12px;
    border: 1px solid #444;
    border-radius: 6px;
    background-color: #2d2d2d;
    color: #ffffff;
    font-size: 14px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.4;
    resize: vertical;
    min-height: 60px;
    max-height: 120px;
    box-sizing: border-box; /* パディングとボーダーを幅に含める */
  }

  .message-input:focus {
    outline: none;
    border-color: #4caf50;
    box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2);
  }

  .message-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background-color: #1a1a1a;
    border-color: #333;
  }

  .input-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 10px;
  }

  .input-help {
    color: #666;
  }

  .input-help small {
    font-size: 12px;
  }

  /* Enhanced styling for disabled input help */
  .chat-input:has(.message-input:disabled) .input-help {
    color: #888;
  }

  .chat-input:has(.message-input:disabled) .input-help small {
    font-style: italic;
  }

  .send-button {
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
    background-color: #4caf50;
    color: white;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 14px;
  }

  .send-button:hover:not(:disabled) {
    background-color: #45a049;
    transform: translateY(-1px);
  }

  .send-button:disabled {
    background-color: #666;
    cursor: not-allowed;
    transform: none;
  }

  /* Scrollbar styling */
  .chat-messages::-webkit-scrollbar {
    width: 8px;
  }

  .chat-messages::-webkit-scrollbar-track {
    background: #2d2d2d;
  }

  .chat-messages::-webkit-scrollbar-thumb {
    background: #666;
    border-radius: 4px;
  }

  .chat-messages::-webkit-scrollbar-thumb:hover {
    background: #888;
  }

  /* AI Typing Indicator */
  .ai-typing {
    padding: 15px;
    margin-bottom: 10px;
  }

  .typing-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .typing-indicator .username {
    font-weight: bold;
    color: #4caf50;
    font-size: 14px;
  }

  .typing-dots {
    display: flex;
    gap: 4px;
  }

  .typing-dots span {
    width: 6px;
    height: 6px;
    background-color: #4caf50;
    border-radius: 50%;
    opacity: 0.4;
    animation: typing 1.4s infinite;
  }

  .typing-dots span:nth-child(1) {
    animation-delay: 0s;
  }

  .typing-dots span:nth-child(2) {
    animation-delay: 0.2s;
  }

  .typing-dots span:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes typing {
    0%,
    60%,
    100% {
      opacity: 0.4;
      transform: translateY(0);
    }
    30% {
      opacity: 1;
      transform: translateY(-4px);
    }
  }

  /* Streaming Content */
  .streaming-content {
    position: relative;
  }

  .streaming-content .cursor {
    color: #4caf50;
    animation: blink 1s infinite;
    font-weight: bold;
  }

  @keyframes blink {
    0%,
    50% {
      opacity: 1;
    }
    51%,
    100% {
      opacity: 0;
    }
  }

  /* Enhanced AI message styling */
  .message.ai {
    background-color: #1976d2;
    border-left: 4px solid #4caf50;
  }

  .message.ai .username {
    color: #4caf50;
  }

  /* Enhanced system message styling */
  .message.system {
    background-color: #424242;
    border-left: 4px solid #ff9800;
  }

  .message.system .username {
    color: #ff9800;
  }

  /* Command suggestions styling */
  .command-suggestions {
    margin-top: 12px;
    padding: 12px;
    background-color: rgba(0, 0, 0, 0.2);
    border-radius: 6px;
    border-left: 3px solid #4caf50;
  }

  .commands-header {
    font-size: 12px;
    font-weight: bold;
    color: #4caf50;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .commands-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .command-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 8px;
    background-color: rgba(255, 255, 255, 0.05);
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  .command-text {
    flex: 1;
    font-family: 'Courier New', monospace;
    font-size: 12px;
    color: #e0e0e0;
    background-color: rgba(0, 0, 0, 0.3);
    padding: 4px 6px;
    border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    word-break: break-all;
  }

  .send-command-btn {
    background-color: #4caf50;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: bold;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .send-command-btn:hover {
    background-color: #45a049;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  }

  .send-command-btn:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  }

  /* Command item hover effect */
  .command-item:hover {
    background-color: rgba(255, 255, 255, 0.08);
    border-color: rgba(76, 175, 80, 0.3);
  }

  .command-item:hover .command-text {
    background-color: rgba(0, 0, 0, 0.4);
    border-color: rgba(76, 175, 80, 0.4);
  }
</style>
