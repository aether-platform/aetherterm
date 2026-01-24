<template>
  <div class="aether-terminal-container" @click="handleClick" ref="containerRef">
    <TerminalOverlays
      :is-connecting="isConnecting"
      :is-terminal-closed="isTerminalClosed"
      :is-access-denied="isAccessDenied"
      @download-logs="downloadLogs"
      @restart-terminal="restartTerminal"
    />
    
    <div 
      v-show="!isConnecting"
      :id="terminalElementId"
      class="aether-terminal"
      ref="terminalRef"
      :style="{ visibility: isConnecting ? 'hidden' : 'visible' }"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref, watch, watchEffect } from 'vue'
import TerminalOverlays from './TerminalOverlays.vue'
import { useTerminalCore } from './composables/useTerminalCore'
import { useTerminalSession } from './composables/useTerminalSession'
import { useAetherTerminalStore } from '../../stores/aetherTerminalStore'
import { useScreenBufferStore } from '../../stores/screenBufferStore'

interface Props {
  id: string // ターミナルのID（tabId または paneId）
  mode?: 'tab' | 'pane' // モード指定
  subType?: 'pure' | 'inventory' | 'agent' | 'main-agent'
}

interface Emits {
  (e: 'click'): void
  (e: 'terminal-initialized'): void
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'pane',
  subType: 'pure'
})

const emit = defineEmits<Emits>()

// Component refs
const containerRef = ref<HTMLElement | null>(null)
const terminalRef = ref<HTMLElement | null>(null)

// Composables
const {
  terminal,
  initializeTerminal,
  fitTerminal,
  writeToTerminal,
  clearTerminal,
  focusTerminal,
  disposeTerminal
} = useTerminalCore()

const {
  isConnecting,
  isTerminalClosed,
  isAccessDenied,
  terminalElementId,
  sessionId,
  initializeSession,
  closeSession,
  restartSession,
  handleTerminalReady,
  handleTerminalClosed,
  handleTerminalError
} = useTerminalSession(props)

// Stores
const aetherStore = useAetherTerminalStore()
const screenBufferStore = useScreenBufferStore()

// Event handlers
const handleClick = () => {
  focusTerminal()
  emit('click')
}

const downloadLogs = () => {
  if (sessionId.value) {
    const buffer = screenBufferStore.getBuffer(sessionId.value)
    if (buffer) {
      const blob = new Blob([buffer], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `terminal-${sessionId.value}-${Date.now()}.log`
      a.click()
      URL.revokeObjectURL(url)
    }
  }
}

const restartTerminal = async () => {
  if (terminal.value) {
    clearTerminal()
    await restartSession(terminal.value)
  }
}

// Socket event listeners
const setupSocketListeners = () => {
  if (!aetherStore.socket) return

  aetherStore.socket.on('terminal_ready', handleTerminalReady)
  aetherStore.socket.on('terminal_closed', handleTerminalClosed)
  aetherStore.socket.on('terminal_error', handleTerminalError)
  
  aetherStore.socket.on('terminal_output', (data: any) => {
    if (data.session === sessionId.value && data.data) {
      writeToTerminal(data.data)
      screenBufferStore.appendToBuffer(data.session, data.data)
    }
  })
}

const removeSocketListeners = () => {
  if (!aetherStore.socket) return

  aetherStore.socket.off('terminal_ready', handleTerminalReady)
  aetherStore.socket.off('terminal_closed', handleTerminalClosed)
  aetherStore.socket.off('terminal_error', handleTerminalError)
  aetherStore.socket.off('terminal_output')
}

// Resize handler
const handleResize = () => {
  setTimeout(() => {
    fitTerminal()
  }, 100)
}

// Lifecycle
onMounted(async () => {
  if (isAccessDenied.value) {
    console.warn('Access denied - terminal not initialized')
    return
  }

  try {
    // Initialize terminal
    await initializeTerminal(terminalElementId.value)
    
    // Setup socket listeners
    setupSocketListeners()
    
    // Initialize session
    if (terminal.value) {
      await initializeSession(terminal.value)
    }
    
    // Setup resize listener
    window.addEventListener('resize', handleResize)
    
    emit('terminal-initialized')
  } catch (error) {
    console.error('Error during terminal mount:', error)
  }
})

onBeforeUnmount(() => {
  removeSocketListeners()
  window.removeEventListener('resize', handleResize)
  disposeTerminal()
})

// Watch for theme changes and resize events
watchEffect(() => {
  fitTerminal()
})

// Watch for session changes
watch(sessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    console.log('Session ID changed:', { old: oldSessionId, new: newSessionId })
  }
})
</script>

<style scoped lang="scss">
.aether-terminal-container {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--terminal-bg-color);
  border-radius: 4px;
}

.aether-terminal {
  width: 100%;
  height: 100%;
  padding: 8px;
  box-sizing: border-box;
  
  // Ensure xterm.js styles are properly applied
  :deep(.xterm) {
    height: 100% !important;
  }
  
  :deep(.xterm-viewport) {
    overflow-y: auto;
  }
  
  :deep(.xterm-screen) {
    height: 100%;
  }
}

// Dark mode support
:deep(.theme-dark) {
  .aether-terminal-container {
    background: #1a1a1a;
  }
}

:deep(.theme-light) {
  .aether-terminal-container {
    background: #ffffff;
  }
}
</style>