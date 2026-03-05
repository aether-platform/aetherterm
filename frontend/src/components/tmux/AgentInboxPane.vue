<template>
  <div class="agent-inbox-pane">
    <!-- Header bar -->
    <div class="inbox-header">
      <span class="inbox-title">Agent Inbox</span>
      <div class="mode-toggle">
        <button
          class="toggle-btn"
          :class="{ active: !isBroadcast }"
          @click="isBroadcast = false"
        >
          DM
        </button>
        <button
          class="toggle-btn"
          :class="{ active: isBroadcast }"
          @click="isBroadcast = true"
        >
          Broadcast
        </button>
      </div>
    </div>

    <!-- Agent selector -->
    <div v-if="!isBroadcast" class="agent-selector">
      <select v-model="selectedAgent" class="agent-dropdown">
        <option value="">-- Select Agent --</option>
        <option
          v-for="agent in messagingStore.agentList"
          :key="agent.id"
          :value="agent.id"
        >
          {{ agent.id }}
          <template v-if="agent.isIdle"> (idle)</template>
          <template v-else> (busy)</template>
        </option>
      </select>
      <button
        v-if="selectedAgent"
        class="shutdown-btn"
        title="Request shutdown"
        @click="handleShutdown"
      >
        Shutdown
      </button>
    </div>

    <!-- Messages list -->
    <div ref="messagesContainer" class="messages-list">
      <div
        v-for="msg in displayedMessages"
        :key="msg.message_id"
        class="message-item"
        :class="{ 'message-self': msg.from_agent === 'self' }"
      >
        <div class="message-meta">
          <span class="message-sender">
            {{ msg.from_agent }}
            <span
              class="agent-badge"
              :class="agentStatusClass(msg.from_agent)"
              :title="agentStatusTitle(msg.from_agent)"
            ></span>
          </span>
          <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
        </div>
        <div class="message-content">{{ msg.payload.content || msg.payload.summary || '' }}</div>
      </div>
      <div v-if="displayedMessages.length === 0" class="messages-empty">
        No messages yet.
      </div>
    </div>

    <!-- Input area -->
    <div class="inbox-input">
      <input
        v-model="inputText"
        class="message-input"
        type="text"
        :placeholder="inputPlaceholder"
        @keydown.enter="handleSend"
      />
      <button class="send-btn" :disabled="!canSend" @click="handleSend">Send</button>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { useAgentMessagingStore, type AgentMessage } from '../../stores/agentMessagingStore'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const messagingStore = useAgentMessagingStore()
  const tmuxStore = useTmuxStore()

  const selectedAgent = ref('')
  const isBroadcast = ref(false)
  const inputText = ref('')
  const messagesContainer = ref<HTMLElement | null>(null)

  const inputPlaceholder = computed(() => {
    if (isBroadcast.value) return 'Broadcast to all agents...'
    if (!selectedAgent.value) return 'Select an agent first...'
    return `Message ${selectedAgent.value}...`
  })

  const canSend = computed(() => {
    if (!inputText.value.trim()) return false
    if (!isBroadcast.value && !selectedAgent.value) return false
    return true
  })

  const displayedMessages = computed(() => {
    if (isBroadcast.value) {
      // Show all messages from all agents
      const all: AgentMessage[] = []
      Object.values(messagingStore.messages).forEach((msgs) => {
        all.push(...msgs)
      })
      return all.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    }
    if (selectedAgent.value) {
      return messagingStore.messagesForPane(selectedAgent.value)
    }
    return []
  })

  // Auto-scroll to bottom when messages change
  watch(
    () => displayedMessages.value.length,
    async () => {
      await nextTick()
      scrollToBottom()
    }
  )

  // Clear unread when selecting an agent
  watch(selectedAgent, (agentId) => {
    if (agentId) {
      messagingStore.clearUnread(agentId)
    }
  })

  function scrollToBottom() {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }

  function handleSend() {
    if (!canSend.value) return
    const content = inputText.value.trim()

    if (isBroadcast.value) {
      tmuxStore.sendAgentBroadcast(content, content.slice(0, 50))
    } else {
      tmuxStore.sendAgentDM(selectedAgent.value, content, content.slice(0, 50))
    }
    inputText.value = ''
  }

  function handleShutdown() {
    if (!selectedAgent.value) return
    tmuxStore.sendShutdownRequest(selectedAgent.value)
  }

  function formatTime(timestamp: string): string {
    try {
      const date = new Date(timestamp)
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return timestamp
    }
  }

  function agentStatusClass(agentId: string): string {
    const agent = messagingStore.agents[agentId]
    if (!agent) return 'status-unknown'
    return agent.isIdle ? 'status-idle' : 'status-busy'
  }

  function agentStatusTitle(agentId: string): string {
    const agent = messagingStore.agents[agentId]
    if (!agent) return 'Unknown'
    return agent.isIdle ? 'Idle' : 'Busy'
  }
</script>

<style scoped>
  .agent-inbox-pane {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: #1a1b26;
    color: #c0caf5;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
  }

  .inbox-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    background: #16161e;
    border-bottom: 1px solid #292e42;
    flex-shrink: 0;
  }

  .inbox-title {
    font-weight: 700;
    font-size: 13px;
    color: #7aa2f7;
  }

  .mode-toggle {
    display: flex;
    gap: 2px;
  }

  .toggle-btn {
    background: #292e42;
    color: #565f89;
    border: none;
    padding: 3px 10px;
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }

  .toggle-btn:first-child {
    border-radius: 3px 0 0 3px;
  }

  .toggle-btn:last-child {
    border-radius: 0 3px 3px 0;
  }

  .toggle-btn.active {
    background: #7aa2f7;
    color: #1a1b26;
  }

  .agent-selector {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-bottom: 1px solid #292e42;
    flex-shrink: 0;
  }

  .agent-dropdown {
    flex: 1;
    background: #292e42;
    color: #c0caf5;
    border: 1px solid #3b4261;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 11px;
    font-family: inherit;
    outline: none;
  }

  .agent-dropdown:focus {
    border-color: #7aa2f7;
  }

  .shutdown-btn {
    background: #f7768e;
    color: #1a1b26;
    border: none;
    border-radius: 3px;
    padding: 4px 10px;
    font-size: 11px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s;
  }

  .shutdown-btn:hover {
    opacity: 0.85;
  }

  .messages-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .messages-list::-webkit-scrollbar {
    width: 4px;
  }

  .messages-list::-webkit-scrollbar-thumb {
    background: #3b4261;
    border-radius: 10px;
  }

  .messages-empty {
    color: #565f89;
    text-align: center;
    margin-top: 24px;
    font-style: italic;
  }

  .message-item {
    padding: 6px 8px;
    background: #1e2030;
    border-radius: 4px;
    border-left: 2px solid #3b4261;
  }

  .message-item.message-self {
    border-left-color: #7aa2f7;
    background: #1f2335;
  }

  .message-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 3px;
  }

  .message-sender {
    font-weight: 600;
    color: #bb9af7;
    font-size: 11px;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  .agent-badge {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }

  .agent-badge.status-idle {
    background: #9ece6a;
  }

  .agent-badge.status-busy {
    background: #e0af68;
  }

  .agent-badge.status-unknown {
    background: #565f89;
  }

  .message-time {
    color: #565f89;
    font-size: 10px;
  }

  .message-content {
    color: #c0caf5;
    line-height: 1.4;
    word-break: break-word;
    white-space: pre-wrap;
  }

  .inbox-input {
    display: flex;
    gap: 6px;
    padding: 8px 10px;
    border-top: 1px solid #292e42;
    background: #16161e;
    flex-shrink: 0;
  }

  .message-input {
    flex: 1;
    background: #292e42;
    color: #c0caf5;
    border: 1px solid #3b4261;
    border-radius: 3px;
    padding: 6px 10px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
  }

  .message-input:focus {
    border-color: #7aa2f7;
  }

  .message-input::placeholder {
    color: #565f89;
  }

  .send-btn {
    background: #7aa2f7;
    color: #1a1b26;
    border: none;
    border-radius: 3px;
    padding: 6px 14px;
    font-size: 12px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    flex-shrink: 0;
    transition: opacity 0.15s;
  }

  .send-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .send-btn:not(:disabled):hover {
    opacity: 0.85;
  }
</style>
