<template>
  <div class="pilot-chat">
    <!-- Messages -->
    <div ref="messagesEl" class="pilot-chat__messages">
      <div v-if="messages.length === 0" class="pilot-chat__empty">
        <p>Pilot Chat</p>
        <span>Type a message or command to get started.</span>
      </div>
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="pilot-chat__bubble"
        :class="'pilot-chat__bubble--' + msg.role"
      >
        <div class="pilot-chat__bubble-content">{{ msg.text }}</div>
        <div class="pilot-chat__bubble-time">{{ formatTime(msg.timestamp) }}</div>
      </div>
    </div>

    <!-- Action preview (placeholder for command-like input) -->
    <div v-if="actionPreview" class="pilot-chat__action-preview">
      <div class="action-preview__header">Action Preview</div>
      <div class="action-preview__body">{{ actionPreview }}</div>
    </div>

    <!-- Input -->
    <div class="pilot-chat__input-area">
      <input
        v-model="inputText"
        class="pilot-chat__input"
        placeholder="Message or /command..."
        @keydown.enter="sendMessage"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { nextTick, ref } from 'vue'

  interface ChatMessage {
    id: string
    role: 'user' | 'assistant'
    text: string
    timestamp: number
  }

  const messages = ref<ChatMessage[]>([])
  const inputText = ref('')
  const actionPreview = ref<string | null>(null)
  const messagesEl = ref<HTMLElement | null>(null)

  function formatTime(ts: number): string {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  function sendMessage() {
    const text = inputText.value.trim()
    if (!text) return

    // Check for command-like input
    if (text.startsWith('/')) {
      actionPreview.value = `Command: ${text}`
      setTimeout(() => {
        actionPreview.value = null
      }, 3000)
    }

    messages.value.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      role: 'user',
      text,
      timestamp: Date.now(),
    })

    inputText.value = ''

    nextTick(() => {
      if (messagesEl.value) {
        messagesEl.value.scrollTop = messagesEl.value.scrollHeight
      }
    })
  }
</script>

<style scoped>
  .pilot-chat {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .pilot-chat__messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .pilot-chat__empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #484f58;
    text-align: center;
    gap: 4px;
  }

  .pilot-chat__empty p {
    font-size: 14px;
    color: #8b949e;
    margin: 0;
  }

  .pilot-chat__empty span {
    font-size: 12px;
  }

  .pilot-chat__bubble {
    max-width: 85%;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.4;
  }

  .pilot-chat__bubble--user {
    align-self: flex-end;
    background: #1f6feb;
    color: #fff;
  }

  .pilot-chat__bubble--assistant {
    align-self: flex-start;
    background: #2d3139;
    color: #c9d1d9;
  }

  .pilot-chat__bubble-time {
    font-size: 10px;
    opacity: 0.6;
    margin-top: 4px;
  }

  .pilot-chat__action-preview {
    margin: 0 12px 8px;
    border: 1px solid #2d3139;
    border-radius: 6px;
    overflow: hidden;
    font-size: 12px;
  }

  .action-preview__header {
    background: #2d3139;
    padding: 4px 8px;
    color: #8b949e;
    font-weight: 500;
  }

  .action-preview__body {
    padding: 8px;
    color: #c9d1d9;
    font-family: monospace;
  }

  .pilot-chat__input-area {
    padding: 8px 12px;
    border-top: 1px solid #2d3139;
  }

  .pilot-chat__input {
    width: 100%;
    background: #0d1117;
    border: 1px solid #2d3139;
    border-radius: 6px;
    padding: 8px 12px;
    color: #c9d1d9;
    font-size: 13px;
    outline: none;
    box-sizing: border-box;
  }

  .pilot-chat__input:focus {
    border-color: #58a6ff;
  }

  .pilot-chat__input::placeholder {
    color: #484f58;
  }
</style>
