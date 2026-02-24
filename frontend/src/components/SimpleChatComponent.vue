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
        <div class="header-controls">
          <label class="exec-mode-toggle" title="Auto-execute AI commands">
            <input type="checkbox" v-model="isAutoMode" @change="toggleExecutionMode" />
            <span class="toggle-label">Auto</span>
          </label>
          <div
            class="connection-status"
            :class="{ connected: terminalStore.connectionState.isConnected && aiInfo.available }"
          >
            {{ getConnectionStatus() }}
          </div>
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
          <!-- Parse and render message content with command blocks -->
          <template v-if="message.type === 'ai' && hasCommandBlocks(message.content)">
            <template v-for="(segment, idx) in parseContent(message.content)" :key="idx">
              <span v-if="segment.type === 'text'" v-text="segment.text"></span>
              <CommandApproval
                v-if="segment.type === 'command'"
                :command="segment.command!"
                :command-id="message.id + '_cmd_' + idx"
                @executed="onCommandExecuted"
                @rejected="onCommandRejected"
              />
            </template>
            <span v-if="message.streaming" class="cursor">|</span>
          </template>
          <template v-else>
            <span v-if="message.streaming" class="streaming-content"
              >{{ message.content }}<span class="cursor">|</span></span
            >
            <span v-else>{{ message.content }}</span>
          </template>
        </div>
      </div>

      <!-- AI Typing Indicator -->
      <div v-if="chatStore.isAITyping" class="ai-typing">
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
        placeholder="Type a message... (Ctrl+Enter to send)"
        :disabled="!terminalStore.connectionState.isConnected"
        class="message-input"
        rows="3"
        ref="messageTextarea"
      ></textarea>
      <div class="input-actions">
        <div class="input-help">
          <small>Ctrl+Enter to send</small>
        </div>
        <button
          @click="sendMessage"
          :disabled="!newMessage.trim() || !terminalStore.connectionState.isConnected"
          class="send-button"
        >
          Send
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useAetherTerminalServiceStore } from '../stores/aetherTerminalServiceStore'
  import { useChatStore } from '../stores/chatStore'
  import CommandApproval from './CommandApproval.vue'

  interface ContentSegment {
    type: 'text' | 'command'
    text?: string
    command?: string
  }

  const terminalStore = useAetherTerminalServiceStore()
  const chatStore = useChatStore()
  const messages = chatStore.aiMessages
  const newMessage = ref('')
  const messagesContainer = ref<HTMLElement | null>(null)
  const messageTextarea = ref<HTMLTextAreaElement | null>(null)
  const isAutoMode = ref(false)

  interface AIInfo {
    provider: string
    model: string
    available: boolean
    status: string
    error?: string
  }

  const aiInfo = ref<AIInfo>({
    provider: 'unknown',
    model: 'unknown',
    available: false,
    status: 'disconnected',
  })

  // Command block parsing
  const COMMAND_BLOCK_REGEX = /```command\n([\s\S]*?)```/g

  function hasCommandBlocks(content: string): boolean {
    return /```command\n/.test(content)
  }

  function parseContent(content: string): ContentSegment[] {
    const segments: ContentSegment[] = []
    let lastIndex = 0

    // Reset regex
    const regex = new RegExp(COMMAND_BLOCK_REGEX.source, 'g')
    let match: RegExpExecArray | null

    while ((match = regex.exec(content)) !== null) {
      // Text before match
      if (match.index > lastIndex) {
        segments.push({ type: 'text', text: content.slice(lastIndex, match.index) })
      }
      // Command block
      segments.push({ type: 'command', command: match[1].trim() })
      lastIndex = match.index + match[0].length
    }

    // Remaining text
    if (lastIndex < content.length) {
      segments.push({ type: 'text', text: content.slice(lastIndex) })
    }

    return segments
  }

  function onCommandExecuted(commandId: string) {
    // Optional: show toast
  }

  function onCommandRejected(commandId: string) {
    // Optional: show toast
  }

  function toggleExecutionMode() {
    if (terminalStore.socket) {
      terminalStore.socket.emit('ai_set_execution_mode', {
        mode: isAutoMode.value ? 'auto' : 'approval',
      })
    }
  }

  const addMessage = (
    username: string,
    content: string,
    type: 'user' | 'system' | 'ai' = 'user',
  ) => {
    const message = chatStore.addAIMessage(username, content, type)

    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })

    return message
  }

  const sendMessage = () => {
    if (!newMessage.value.trim() || !terminalStore.connectionState.isConnected) return

    const userMessage = newMessage.value.trim()

    addMessage('You', userMessage, 'user')
    sendAIMessage(userMessage)

    newMessage.value = ''

    nextTick(() => {
      messageTextarea.value?.focus()
    })
  }

  const sendAIMessage = async (userMessage: string) => {
    if (!terminalStore.socket || !terminalStore.connectionState.isConnected) {
      return
    }

    const messageId = Date.now().toString() + Math.random().toString(36).substr(2, 9)
    chatStore.addStreamingAIMessage(messageId)

    terminalStore.socket.emit('ai_chat_message', {
      message: userMessage,
      message_id: messageId,
      terminal_session: terminalStore.session.id,
    })
  }

  // Auto-scroll when messages change
  watch(
    () => messages.length,
    () => {
      nextTick(() => {
        if (messagesContainer.value) {
          messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
        }
      })
    },
  )

  onMounted(() => {
    // Only add welcome message once (when store is empty)
    if (messages.length === 0) {
      addMessage(
        'Aether AI',
        'Welcome to Aether Assistant! I can help with terminal operations, troubleshooting, and code analysis. I can also propose commands for you to run.',
        'system',
      )
    }

    terminalStore.onChatMessage((data: any) => {
      addMessage(data.username || 'Unknown User', data.message || data.content, 'user')
    })

    const setupAIListeners = () => {
      if (!terminalStore.socket) return

      terminalStore.socket.off('ai_chat_typing')
      terminalStore.socket.off('ai_chat_chunk')
      terminalStore.socket.off('ai_chat_complete')
      terminalStore.socket.off('ai_chat_error')
      terminalStore.socket.off('ai_info_response')

      terminalStore.socket.on('ai_chat_typing', (data: any) => {
        chatStore.isAITyping = data.typing
      })

      terminalStore.socket.on('ai_chat_chunk', (data: any) => {
        chatStore.updateStreamingMessage(data.message_id, data.chunk)
        nextTick(() => {
          if (messagesContainer.value) {
            messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
          }
        })
      })

      terminalStore.socket.on('ai_chat_complete', (data: any) => {
        chatStore.completeStreamingMessage(data.message_id, data.full_response)
      })

      terminalStore.socket.on('ai_chat_error', (data: any) => {
        chatStore.failStreamingMessage(data.message_id, data.error)
      })

      terminalStore.socket.on('ai_info_response', (data: any) => {
        aiInfo.value = {
          provider: data.provider || 'unknown',
          model: data.model || 'unknown',
          available: data.available || false,
          status: data.status || 'disconnected',
          error: data.error,
        }
      })
    }

    setupAIListeners()

    let isListenersSetup = false
    const watchConnection = () => {
      if (terminalStore.connectionState.isConnected && terminalStore.socket && !isListenersSetup) {
        setupAIListeners()
        requestAIInfo()
        isListenersSetup = true
      }
    }

    const connectionWatcher = setInterval(watchConnection, 1000)

    onUnmounted(() => {
      clearInterval(connectionWatcher)
      terminalStore.offChatMessage()

      if (terminalStore.socket) {
        terminalStore.socket.off('ai_chat_typing')
        terminalStore.socket.off('ai_chat_chunk')
        terminalStore.socket.off('ai_chat_complete')
        terminalStore.socket.off('ai_chat_error')
        terminalStore.socket.off('ai_info_response')
      }
    })
  })

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const getConnectionStatus = () => {
    if (!terminalStore.connectionState.isConnected) return 'Terminal Disconnected'
    if (!aiInfo.value.available) return 'AI Unavailable'
    return 'Connected'
  }

  const requestAIInfo = () => {
    if (terminalStore.socket && terminalStore.connectionState.isConnected) {
      terminalStore.socket.emit('ai_get_info', {})
    }
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

  .header-controls {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .exec-mode-toggle {
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    font-size: 11px;
    color: #888;
  }

  .exec-mode-toggle input {
    accent-color: #4caf50;
  }

  .toggle-label {
    font-size: 11px;
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

  .chat-messages {
    flex: 1;
    padding: 15px;
    overflow-y: auto;
    min-height: 0;
  }

  .message {
    margin-bottom: 15px;
    padding: 10px;
    border-radius: 8px;
    background-color: #3d3d3d;
  }

  .message.system {
    background-color: #424242;
    border-left: 4px solid #ff9800;
  }

  .message.ai {
    background-color: #1976d2;
    border-left: 4px solid #4caf50;
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
    white-space: pre-wrap;
    word-break: break-word;
  }

  .message.system .username { color: #ff9800; }
  .message.ai .username { color: #4caf50; }

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
    overflow-x: hidden;
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
    box-sizing: border-box;
  }

  .message-input:focus {
    outline: none;
    border-color: #4caf50;
    box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2);
  }

  .message-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .input-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 10px;
  }

  .input-help { color: #666; }
  .input-help small { font-size: 12px; }

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

  /* Scrollbar */
  .chat-messages::-webkit-scrollbar { width: 8px; }
  .chat-messages::-webkit-scrollbar-track { background: #2d2d2d; }
  .chat-messages::-webkit-scrollbar-thumb { background: #666; border-radius: 4px; }
  .chat-messages::-webkit-scrollbar-thumb:hover { background: #888; }

  /* AI Typing Indicator */
  .ai-typing { padding: 15px; margin-bottom: 10px; }
  .typing-indicator { display: flex; align-items: center; gap: 10px; }
  .typing-indicator .username { font-weight: bold; color: #4caf50; font-size: 14px; }
  .typing-dots { display: flex; gap: 4px; }
  .typing-dots span {
    width: 6px; height: 6px; background-color: #4caf50; border-radius: 50%; opacity: 0.4;
    animation: typing 1.4s infinite;
  }
  .typing-dots span:nth-child(1) { animation-delay: 0s; }
  .typing-dots span:nth-child(2) { animation-delay: 0.2s; }
  .typing-dots span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes typing {
    0%, 60%, 100% { opacity: 0.4; transform: translateY(0); }
    30% { opacity: 1; transform: translateY(-4px); }
  }

  .streaming-content { position: relative; }
  .streaming-content .cursor, .cursor {
    color: #4caf50; animation: blink 1s infinite; font-weight: bold;
  }

  @keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
  }
</style>
