<template>
  <div v-if="isVisible" class="block-alert-overlay" @click="handleOverlayClick">
    <div class="block-alert-container" :class="severityClass">
      <div class="alert-header">
        <div class="alert-icon">
          <span v-if="severity === 'critical'">🚨</span>
          <span v-else-if="severity === 'high'">⚠️</span>
          <span v-else-if="severity === 'medium'">⚡</span>
          <span v-else>ℹ️</span>
        </div>
        <h2 class="alert-title">{{ alertTitle }}</h2>
        <button class="close-button" @click="dismissAlert" aria-label="Close">×</button>
      </div>

      <div class="alert-content">
        <div class="alert-message">
          {{ message }}
        </div>

        <div v-if="detectedKeywords.length > 0" class="detected-keywords">
          <h4>検出されたキーワード:</h4>
          <div class="keyword-list">
            <span
              v-for="keyword in detectedKeywords"
              :key="keyword"
              class="keyword-tag"
              :class="getKeywordSeverity(keyword)"
            >
              {{ keyword }}
            </span>
          </div>
        </div>

        <div class="unlock-instructions">
          <div class="unlock-message">
            {{ alertMessage }}
          </div>
          <div class="unlock-hint"><kbd>Ctrl</kbd> + <kbd>D</kbd> を押してブロックを解除</div>
          <div class="unlock-status" :class="{ listening: isListening }">
            {{ isListening ? 'キー入力を待機中...' : 'キー入力監視停止中' }}
          </div>
        </div>

        <div class="alert-actions">
          <button class="unlock-button" @click="requestUnblock" :disabled="isUnlocking">
            {{ isUnlocking ? '解除中...' : '手動解除' }}
          </button>
          <button class="dismiss-button" @click="dismissAlert">警告を閉じる</button>
        </div>
      </div>

      <div class="alert-footer">
        <div class="timestamp">
          {{ formatTimestamp(timestamp) }}
        </div>
        <div class="session-info">セッション: {{ sessionId }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useTerminalBlockStore } from '../stores/terminalBlockStore'

  interface Props {
    sessionId: string
    severity: 'low' | 'medium' | 'high' | 'critical'
    message: string
    alertMessage: string
    detectedKeywords: string[]
    timestamp: number
    isVisible: boolean
  }

  const props = withDefaults(defineProps<Props>(), {
    detectedKeywords: () => [],
    isVisible: true,
  })

  const emit = defineEmits<{
    dismiss: []
    unlock: []
  }>()

  const blockStore = useTerminalBlockStore()
  const isUnlocking = ref(false)

  // Computed properties
  const severityClass = computed(() => `severity-${props.severity}`)

  const alertTitle = computed(() => {
    switch (props.severity) {
      case 'critical':
        return 'CRITICAL ALERT'
      case 'high':
        return 'HIGH RISK ALERT'
      case 'medium':
        return 'WARNING ALERT'
      default:
        return 'INFORMATION ALERT'
    }
  })

  const isListening = computed(() => {
    return blockStore.isListeningForUnlock.get(props.sessionId) || false
  })

  // Methods
  const dismissAlert = () => {
    emit('dismiss')
  }

  const requestUnblock = async () => {
    isUnlocking.value = true
    try {
      emit('unlock')
    } finally {
      isUnlocking.value = false
    }
  }

  const handleOverlayClick = (event: MouseEvent) => {
    // オーバーレイクリックで閉じる（コンテナ内のクリックは除外）
    if (event.target === event.currentTarget) {
      dismissAlert()
    }
  }

  const getKeywordSeverity = (keyword: string) => {
    const criticalKeywords = [
      'rm -rf',
      'sudo rm',
      'format',
      'mkfs',
      'hack',
      'attack',
      'exploit',
      'malware',
    ]
    const highKeywords = ['critical', 'fatal', 'emergency', 'security']

    if (criticalKeywords.some((ck) => keyword.toLowerCase().includes(ck.toLowerCase()))) {
      return 'keyword-critical'
    } else if (highKeywords.some((hk) => keyword.toLowerCase().includes(hk.toLowerCase()))) {
      return 'keyword-high'
    }
    return 'keyword-medium'
  }

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString('ja-JP')
  }

  // キーボードイベントリスナー
  const handleKeyDown = (event: KeyboardEvent) => {
    if (!props.isVisible) return

    const isUnlockKey = blockStore.handleKeyPress(props.sessionId, event.key, event.ctrlKey)

    if (isUnlockKey) {
      event.preventDefault()
      requestUnblock()
    }

    // ESCキーで閉じる
    if (event.key === 'Escape') {
      dismissAlert()
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })
</script>

<style scoped>
  .block-alert-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(4px);
  }

  .block-alert-container {
    background: #2d2d2d;
    border-radius: 12px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
    max-width: 600px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    border: 2px solid;
    animation: alertSlideIn 0.3s ease-out;
  }

  @keyframes alertSlideIn {
    from {
      opacity: 0;
      transform: translateY(-20px) scale(0.95);
    }

    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .severity-critical {
    border-color: #ff4444;
    background: linear-gradient(135deg, #2d2d2d 0%, #3d1a1a 100%);
  }

  .severity-high {
    border-color: #ff8800;
    background: linear-gradient(135deg, #2d2d2d 0%, #3d2a1a 100%);
  }

  .severity-medium {
    border-color: #ffaa00;
    background: linear-gradient(135deg, #2d2d2d 0%, #3d3d1a 100%);
  }

  .severity-low {
    border-color: #4488ff;
    background: linear-gradient(135deg, #2d2d2d 0%, #1a2a3d 100%);
  }

  .alert-header {
    display: flex;
    align-items: center;
    padding: 20px;
    border-bottom: 1px solid #444;
  }

  .alert-icon {
    font-size: 24px;
    margin-right: 12px;
  }

  .alert-title {
    flex: 1;
    margin: 0;
    font-size: 18px;
    font-weight: bold;
    color: #fff;
  }

  .close-button {
    background: none;
    border: none;
    color: #ccc;
    font-size: 24px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .close-button:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }

  .alert-content {
    padding: 20px;
  }

  .alert-message {
    font-size: 16px;
    color: #fff;
    margin-bottom: 16px;
    line-height: 1.5;
  }

  .detected-keywords {
    margin-bottom: 20px;
  }

  .detected-keywords h4 {
    margin: 0 0 8px 0;
    color: #ccc;
    font-size: 14px;
  }

  .keyword-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .keyword-tag {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    color: #fff;
  }

  .keyword-critical {
    background: #ff4444;
  }

  .keyword-high {
    background: #ff8800;
  }

  .keyword-medium {
    background: #ffaa00;
    color: #000;
  }

  .unlock-instructions {
    background: rgba(0, 0, 0, 0.3);
    padding: 16px;
    border-radius: 8px;
    margin-bottom: 20px;
  }

  .unlock-message {
    font-size: 16px;
    font-weight: bold;
    color: #ff6666;
    margin-bottom: 8px;
  }

  .unlock-hint {
    font-size: 14px;
    color: #ccc;
    margin-bottom: 8px;
  }

  .unlock-hint kbd {
    background: #444;
    border: 1px solid #666;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 12px;
    color: #fff;
  }

  .unlock-status {
    font-size: 12px;
    color: #888;
    transition: color 0.3s;
  }

  .unlock-status.listening {
    color: #4caf50;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }

    50% {
      opacity: 0.6;
    }
  }

  .alert-actions {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
  }

  .unlock-button {
    background: #4caf50;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    cursor: pointer;
    font-weight: bold;
    transition: all 0.2s;
  }

  .unlock-button:hover:not(:disabled) {
    background: #45a049;
    transform: translateY(-1px);
  }

  .unlock-button:disabled {
    background: #666;
    cursor: not-allowed;
  }

  .dismiss-button {
    background: #666;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .dismiss-button:hover {
    background: #777;
  }

  .alert-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-top: 1px solid #444;
    font-size: 12px;
    color: #888;
  }

  .timestamp {
    font-family: monospace;
  }

  .session-info {
    font-family: monospace;
  }
</style>
