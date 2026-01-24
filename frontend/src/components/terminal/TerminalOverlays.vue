<template>
  <div>
    <!-- Loading Overlay -->
    <div 
      v-if="isConnecting"
      class="terminal-loading"
    >
      <div class="loading-spinner"></div>
      <div class="loading-text">Connecting to terminal...</div>
    </div>
    
    <!-- Terminal Closed Overlay -->
    <div v-if="isTerminalClosed" class="terminal-closed-overlay">
      <div class="terminal-closed-content">
        <div class="terminal-closed-icon">⚠️</div>
        <div class="terminal-closed-title">Terminal Closed</div>
        <div class="terminal-closed-message">
          The terminal session has ended. You can:
        </div>
        <div class="terminal-closed-actions">
          <button @click="downloadLogs" class="action-button download-button">
            📥 Download Logs
          </button>
          <button @click="restartTerminal" class="action-button restart-button">
            🔄 Restart Terminal
          </button>
        </div>
      </div>
    </div>
    
    <!-- Access Denied Overlay for Anonymous Users -->
    <div v-if="isAccessDenied" class="terminal-access-denied-overlay">
      <div class="terminal-access-denied-content">
        <div class="terminal-access-denied-icon">🔒</div>
        <div class="terminal-access-denied-title">Access Denied</div>
        <div class="terminal-access-denied-message">
          Anonymous users can only access debug mode.
          <br>
          Please go to the debug page to access terminal functionality.
        </div>
        <div class="terminal-access-denied-actions">
          <button @click="goToDebugPage" class="action-button debug-button">
            🔧 Go to Debug Page
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

interface Props {
  isConnecting: boolean
  isTerminalClosed: boolean
  isAccessDenied: boolean
}

interface Emits {
  (e: 'download-logs'): void
  (e: 'restart-terminal'): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const router = useRouter()

const downloadLogs = () => {
  emit('download-logs')
}

const restartTerminal = () => {
  emit('restart-terminal')
}

const goToDebugPage = () => {
  router.push('/debug')
}
</script>

<style scoped lang="scss">
.terminal-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  z-index: 10;
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top: 3px solid white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text {
  font-size: 14px;
  opacity: 0.9;
}

.terminal-closed-overlay,
.terminal-access-denied-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.9);
  z-index: 20;
}

.terminal-closed-content,
.terminal-access-denied-content {
  text-align: center;
  color: white;
  padding: 32px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  max-width: 400px;
}

.terminal-closed-icon,
.terminal-access-denied-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.terminal-closed-title,
.terminal-access-denied-title {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 16px;
}

.terminal-closed-message,
.terminal-access-denied-message {
  font-size: 16px;
  opacity: 0.9;
  margin-bottom: 24px;
  line-height: 1.5;
}

.terminal-closed-actions,
.terminal-access-denied-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.action-button {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }
}

.download-button {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;

  &:hover {
    background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
  }
}

.restart-button {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;

  &:hover {
    background: linear-gradient(135deg, #e081e9 0%, #e3455a 100%);
  }
}

.debug-button {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;

  &:hover {
    background: linear-gradient(135deg, #3d9aec 0%, #00e0ec 100%);
  }
}
</style>