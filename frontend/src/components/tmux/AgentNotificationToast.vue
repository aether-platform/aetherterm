<template>
  <div class="agent-toast-container">
    <TransitionGroup name="toast">
      <div
        v-for="toast in messagingStore.toasts"
        :key="toast.id"
        class="agent-toast"
        @click="dismiss(toast.id)"
      >
        <div class="toast-header">
          <span class="toast-sender">{{ toast.from }}</span>
          <span class="toast-time">{{ relativeTime(toast.timestamp) }}</span>
        </div>
        <div class="toast-body">{{ toast.summary }}</div>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
  import { useAgentMessagingStore } from '../../stores/agentMessagingStore'

  const messagingStore = useAgentMessagingStore()

  function dismiss(id: string) {
    messagingStore.removeToast(id)
  }

  function relativeTime(timestamp: number): string {
    const seconds = Math.floor((Date.now() - timestamp) / 1000)
    if (seconds < 5) return 'just now'
    if (seconds < 60) return `${seconds}s ago`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    return `${Math.floor(minutes / 60)}h ago`
  }
</script>

<style scoped>
  .agent-toast-container {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: 6px;
    pointer-events: none;
    max-width: 320px;
  }

  .agent-toast {
    background: #1e2030;
    border: 1px solid #3b4261;
    border-left: 3px solid #7aa2f7;
    border-radius: 4px;
    padding: 8px 12px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #c0caf5;
    cursor: pointer;
    pointer-events: auto;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    transition: opacity 0.15s;
  }

  .agent-toast:hover {
    opacity: 0.9;
  }

  .toast-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }

  .toast-sender {
    font-weight: 700;
    color: #bb9af7;
    font-size: 11px;
  }

  .toast-time {
    color: #565f89;
    font-size: 10px;
  }

  .toast-body {
    color: #a9b1d6;
    line-height: 1.3;
    word-break: break-word;
    font-size: 11px;
  }

  /* Slide-in animation */
  .toast-enter-active {
    transition: all 0.3s ease-out;
  }

  .toast-leave-active {
    transition: all 0.25s ease-in;
  }

  .toast-enter-from {
    opacity: 0;
    transform: translateX(40px);
  }

  .toast-leave-to {
    opacity: 0;
    transform: translateX(40px);
  }

  .toast-move {
    transition: transform 0.25s ease;
  }
</style>
