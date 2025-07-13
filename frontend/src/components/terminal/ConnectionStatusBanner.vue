<template>
  <div class="connection-status-banner" :class="statusClass" v-if="showBanner">
    <div class="status-content">
      <!-- Connection Status Indicator -->
      <div class="status-indicator">
        <div class="status-dot" :class="statusDotClass"></div>
        <span class="status-text">{{ statusText }}</span>
      </div>

      <!-- Logo/Brand Section -->
      <div class="brand-section" v-if="status === 'disconnected'">
        <div class="aether-logo">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M16 2L28 8V24L16 30L4 24V8L16 2Z" stroke="currentColor" stroke-width="2" fill="none"/>
            <path d="M16 8L22 12V20L16 24L10 20V12L16 8Z" stroke="currentColor" stroke-width="1.5" fill="none"/>
            <circle cx="16" cy="16" r="3" fill="currentColor"/>
          </svg>
        </div>
        <div class="brand-text">
          <div class="brand-name">AetherTerm</div>
          <div class="brand-subtitle">AI Terminal Platform</div>
        </div>
      </div>

      <!-- Reconnect Button -->
      <div class="actions" v-if="status === 'disconnected'">
        <v-btn 
          color="primary" 
          variant="outlined"
          size="small"
          @click="reconnect"
          :loading="isReconnecting"
        >
          <v-icon start>mdi-connection</v-icon>
          再接続
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAetherTerminalStore } from '../../stores/aetherTerminalStore'

const terminalStore = useAetherTerminalStore()

const status = computed(() => terminalStore.connectionStatus)
const isReconnecting = computed(() => terminalStore.connectionState.isReconnecting)

const showBanner = computed(() => {
  return status.value !== 'connected'
})

const statusClass = computed(() => {
  return `status-${status.value}`
})

const statusDotClass = computed(() => {
  return `dot-${status.value}`
})

const statusText = computed(() => {
  switch (status.value) {
    case 'connected':
      return '接続済み'
    case 'connecting':
      return '接続中...'
    case 'reconnecting':
      return '再接続中...'
    case 'disconnected':
    default:
      return '切断済み'
  }
})

const reconnect = () => {
  terminalStore.connect()
}
</script>

<style scoped lang="scss">
.connection-status-banner {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1000;
  padding: 24px 32px;
  border-radius: 12px;
  min-width: 400px;
  transition: all 0.3s ease;
  backdrop-filter: blur(20px);
  
  &.status-disconnected {
    background: linear-gradient(135deg, rgba(244, 67, 54, 0.1) 0%, rgba(156, 39, 176, 0.1) 100%);
    border: 1px solid rgba(244, 67, 54, 0.3);
    box-shadow: 0 4px 12px rgba(244, 67, 54, 0.2);
  }
  
  &.status-connecting {
    background: linear-gradient(135deg, rgba(255, 193, 7, 0.1) 0%, rgba(255, 152, 0, 0.1) 100%);
    border: 1px solid rgba(255, 193, 7, 0.3);
    box-shadow: 0 4px 12px rgba(255, 193, 7, 0.2);
  }
  
  &.status-reconnecting {
    background: linear-gradient(135deg, rgba(33, 150, 243, 0.1) 0%, rgba(63, 81, 181, 0.1) 100%);
    border: 1px solid rgba(33, 150, 243, 0.3);
    box-shadow: 0 4px 12px rgba(33, 150, 243, 0.2);
  }
}

.status-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  position: relative;
  
  &.dot-disconnected {
    background: #f44336;
  }
  
  &.dot-connecting {
    background: #ff9800;
    animation: pulse 1.5s infinite;
  }
  
  &.dot-reconnecting {
    background: #2196f3;
    animation: pulse 1.5s infinite;
  }
  
  &.dot-connected {
    background: #4caf50;
  }
}

.status-text {
  font-weight: 500;
  font-size: 14px;
}

.brand-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.aether-logo {
  color: #6366f1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-text {
  text-align: center;
}

.brand-name {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
}

.brand-subtitle {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 400;
}

.actions {
  display: flex;
  gap: 8px;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(0.95);
  }
}

// レスポンシブ対応
@media (max-width: 768px) {
  .connection-status-banner {
    margin: 8px;
    padding: 12px 16px;
  }
  
  .status-content {
    flex-direction: column;
    gap: 12px;
    text-align: center;
  }
  
  .brand-section {
    order: -1;
  }
}
</style>