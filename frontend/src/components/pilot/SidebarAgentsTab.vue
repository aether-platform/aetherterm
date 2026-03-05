<template>
  <div class="agents-tab">
    <!-- Agent list -->
    <div v-if="agentStore.agentList.length === 0" class="agents-tab__empty">
      <span>No agents connected</span>
    </div>

    <template v-else>
      <div class="agents-tab__list">
        <div
          v-for="agent in agentStore.agentList"
          :key="agent.id"
          class="agents-tab__agent"
          :class="{ 'agents-tab__agent--selected': selectedAgent === agent.id }"
          @click="selectAgent(agent.id)"
        >
          <span class="agents-tab__status-dot" :class="agent.isIdle ? 'dot--idle' : 'dot--busy'" />
          <span class="agents-tab__name">{{ agent.id }}</span>
          <span v-if="unreadFor(agent.id)" class="agents-tab__unread">{{ unreadFor(agent.id) }}</span>
          <div class="agents-tab__actions">
            <button class="agents-tab__btn" title="Message">Msg</button>
            <button class="agents-tab__btn agents-tab__btn--danger" title="Shutdown">Stop</button>
          </div>
        </div>
      </div>

      <!-- Message thread for selected agent -->
      <div v-if="selectedAgent" class="agents-tab__thread">
        <div class="agents-tab__thread-header">
          <span>{{ selectedAgent }}</span>
          <button class="agents-tab__thread-close" @click="selectedAgent = null">&times;</button>
        </div>
        <div class="agents-tab__thread-messages">
          <div v-for="msg in threadMessages" :key="msg.message_id" class="agents-tab__msg">
            <span class="agents-tab__msg-from">{{ msg.from_agent }}</span>
            <span class="agents-tab__msg-text">{{ msg.payload.content || msg.payload.summary }}</span>
          </div>
          <div v-if="threadMessages.length === 0" class="agents-tab__thread-empty">
            No messages yet
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useAgentMessagingStore } from '../../stores/agentMessagingStore'

  const agentStore = useAgentMessagingStore()
  const selectedAgent = ref<string | null>(null)

  const threadMessages = computed(() => {
    if (!selectedAgent.value) return []
    return agentStore.messagesForPane(selectedAgent.value)
  })

  function unreadFor(agentId: string): number {
    return agentStore.unreadCounts[agentId] || 0
  }

  function selectAgent(agentId: string) {
    selectedAgent.value = agentId
    agentStore.clearUnread(agentId)
  }

  watch(selectedAgent, (id) => {
    if (id) agentStore.clearUnread(id)
  })
</script>

<style scoped>
  .agents-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .agents-tab__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #484f58;
    font-size: 13px;
  }

  .agents-tab__list {
    flex-shrink: 0;
    overflow-y: auto;
    max-height: 50%;
    border-bottom: 1px solid #2d3139;
  }

  .agents-tab__agent {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    cursor: pointer;
    transition: background 0.15s;
  }

  .agents-tab__agent:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .agents-tab__agent--selected {
    background: rgba(88, 166, 255, 0.08);
  }

  .agents-tab__status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .dot--busy {
    background: #3fb950;
  }

  .dot--idle {
    background: #d29922;
  }

  .agents-tab__name {
    flex: 1;
    font-size: 13px;
    color: #c9d1d9;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .agents-tab__unread {
    background: #1f6feb;
    color: #fff;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 10px;
    font-weight: 600;
  }

  .agents-tab__actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .agents-tab__agent:hover .agents-tab__actions {
    opacity: 1;
  }

  .agents-tab__btn {
    background: #2d3139;
    border: none;
    color: #8b949e;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 3px;
    cursor: pointer;
  }

  .agents-tab__btn:hover {
    background: #3d4450;
    color: #c9d1d9;
  }

  .agents-tab__btn--danger:hover {
    background: #da3633;
    color: #fff;
  }

  .agents-tab__thread {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .agents-tab__thread-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    font-size: 12px;
    color: #8b949e;
    border-bottom: 1px solid #2d3139;
  }

  .agents-tab__thread-close {
    background: none;
    border: none;
    color: #8b949e;
    cursor: pointer;
    font-size: 16px;
    padding: 0 4px;
  }

  .agents-tab__thread-messages {
    flex: 1;
    overflow-y: auto;
    padding: 8px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .agents-tab__msg {
    font-size: 12px;
    line-height: 1.4;
  }

  .agents-tab__msg-from {
    color: #58a6ff;
    font-weight: 500;
    margin-right: 6px;
  }

  .agents-tab__msg-text {
    color: #c9d1d9;
  }

  .agents-tab__thread-empty {
    color: #484f58;
    font-size: 12px;
    text-align: center;
    padding: 16px;
  }
</style>
