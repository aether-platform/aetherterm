<template>
  <div class="terminal-container" :class="{ focused: isFocused }" @click="handleClick">
    <!-- Connection Status -->
    <div v-if="!terminalStore.connectionState.isConnected" class="connection-status">
      <div class="status-indicator" :class="connectionStatusClass">
        {{ connectionStatusText }}
      </div>
      <div v-if="terminalStore.connectionState.isReconnecting" class="reconnect-info">
        Reconnection attempt:
        {{ terminalStore.connectionState.reconnectAttempts }}/{{
          terminalStore.connectionState.maxReconnectAttempts
        }}
      </div>
    </div>

    <!-- Terminal Lock Status -->
    <div v-if="terminalStore.isTerminalBlocked" class="lock-status">
      <div class="lock-indicator">Terminal Locked</div>
    </div>

    <!-- Terminal Blocked Overlay -->
    <div v-if="terminalStore.isTerminalBlocked" class="terminal-overlay"></div>

    <!-- Pane title bar -->
    <div class="pane-title-bar" v-if="paneId">
      <span class="pane-title">{{ paneTitle }}</span>
      <span class="pane-session">{{ sessionId }}</span>
    </div>

    <!-- Xterm.js Integration -->
    <div ref="terminalEl" class="xterm-container" @click="hideSelectionPopup"></div>

    <!-- Selection Action Popup -->
    <SelectionActionPopup
      :show="showSelectionPopup"
      :position="popupPosition"
      :selected-text="selectedText"
      @copy="onCopyAction"
      @send-to-ai="onSendToAI"
      @hide="hideSelectionPopup"
    />
  </div>
</template>

<script setup lang="ts">
  import { FitAddon } from '@xterm/addon-fit'
  import { Unicode11Addon } from '@xterm/addon-unicode11'
  import { WebLinksAddon } from '@xterm/addon-web-links'
  import { Terminal, type ITheme } from '@xterm/xterm'
  import '@xterm/xterm/css/xterm.css'
  import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useAetherTerminalServiceStore } from '../stores/aetherTerminalServiceStore'
  import { usePaneStore } from '../stores/paneStore'
  import SelectionActionPopup from './SelectionActionPopup.vue'

  const props = withDefaults(
    defineProps<{
      paneId?: string
      sessionId?: string
      mode?: string
      isFocused?: boolean
    }>(),
    {
      paneId: '',
      sessionId: '',
      mode: 'terminal',
      isFocused: false,
    }
  )

  const emit = defineEmits<{
    focus: []
  }>()

  const terminalEl = ref<HTMLElement | null>(null)
  const terminal = ref<Terminal | null>(null)
  const fitAddon = ref<FitAddon | null>(null)

  const terminalStore = useAetherTerminalServiceStore()
  const paneStore = usePaneStore()

  // Selection popup state
  const showSelectionPopup = ref(false)
  const popupPosition = ref({ x: 0, y: 0 })
  const selectedText = ref('')

  const isSupervisorLocked = computed(() => {
    return terminalStore.isSupervisorLocked
  })

  const paneTitle = computed(() => {
    if (props.paneId) {
      const pane = paneStore.panes.get(props.paneId)
      return pane?.title || 'Terminal'
    }
    return 'Terminal'
  })

  // Determine the session ID to use (prop or store)
  const effectiveSessionId = computed(() => {
    return props.sessionId || terminalStore.session.id
  })

  // Connection status computed properties
  const connectionStatusClass = computed(() => {
    switch (terminalStore.connectionStatus) {
      case 'connected':
        return 'status-connected'
      case 'connecting':
        return 'status-connecting'
      case 'reconnecting':
        return 'status-reconnecting'
      default:
        return 'status-disconnected'
    }
  })

  const connectionStatusText = computed(() => {
    switch (terminalStore.connectionStatus) {
      case 'connected':
        return 'Connected'
      case 'connecting':
        return 'Connecting...'
      case 'reconnecting':
        return 'Reconnecting...'
      default:
        return 'Disconnected'
    }
  })

  const theme: ITheme = {
    background: '#1e1e1e',
    foreground: '#ffffff',
    cursor: '#ffffff',
    cursorAccent: '#000000',
    selectionBackground: 'rgba(255, 255, 255, 0.3)',
    selectionForeground: '#000000',
    black: '#000000',
    red: '#cd3131',
    green: '#0dbc79',
    yellow: '#e5e510',
    blue: '#3b78ff',
    magenta: '#bc3fbc',
    cyan: '#0dc2c2',
    white: '#e5e5e5',
    brightBlack: '#666666',
    brightRed: '#f14c4c',
    brightGreen: '#23d18b',
    brightYellow: '#f5f543',
    brightBlue: '#3b8eea',
    brightMagenta: '#d670d6',
    brightCyan: '#29b8db',
    brightWhite: '#ffffff',
  }

  // Shell output handler reference for cleanup
  let shellOutputHandler: ((data: string) => void) | null = null

  // Resize observer for container changes
  let resizeObserver: ResizeObserver | null = null

  function handleClick() {
    emit('focus')
  }

  onMounted(async () => {
    if (!terminalEl.value) return

    terminal.value = new Terminal({
      convertEol: true,
      cursorBlink: true,
      disableStdin: false,
      scrollback: 1000,
      theme: theme,
      allowProposedApi: true,
    })

    fitAddon.value = new FitAddon()
    terminal.value.loadAddon(fitAddon.value)
    terminal.value.loadAddon(new WebLinksAddon())
    terminal.value.loadAddon(new Unicode11Addon())

    terminal.value.open(terminalEl.value)
    fitAddon.value.fit()

    // Listen for terminal resize events and send to backend
    terminal.value.onResize((dimensions) => {
      if (terminalStore.socket && effectiveSessionId.value) {
        if (props.paneId) {
          // Multi-pane mode: use pane_resize
          terminalStore.socket.emit('pane_resize', {
            pane_id: props.paneId,
            cols: dimensions.cols,
            rows: dimensions.rows,
          })
        } else {
          // Legacy single-pane mode
          terminalStore.socket.emit('terminal_resize', {
            session: effectiveSessionId.value,
            cols: dimensions.cols,
            rows: dimensions.rows,
          })
        }
      }
    })

    // Set up shell output listener filtered by session
    shellOutputHandler = (data: string) => {
      terminal.value?.write(data)
    }

    if (props.paneId) {
      // Multi-pane: listen for pane-specific output via backend routing
      // The backend broadcasts terminal_output with session ID;
      // we filter by our session
      const handler = (rawData: any) => {
        if (rawData && rawData.data && rawData.session === effectiveSessionId.value) {
          terminal.value?.write(rawData.data)
        }
      }
      if (terminalStore.socket) {
        terminalStore.socket.on('terminal_output', handler)
      }
      // Store handler ref for cleanup
      shellOutputHandler = handler as any
    } else {
      // Legacy single-pane: use store callback
      terminalStore.onShellOutput(shellOutputHandler)
    }

    // Handle key input
    terminal.value.onKey((e) => {
      const ev = e.domEvent

      if (isSupervisorLocked.value) {
        ev.preventDefault()
        return
      }

      sendInput(e.key)
    })

    // Handle text selection events
    terminal.value.onSelectionChange(() => {
      const selection = terminal.value?.getSelection()
      if (selection && selection.trim()) {
        selectedText.value = selection
        showSelectionPopup.value = false
      } else {
        hideSelectionPopup()
      }
    })

    // Handle mouse events for selection popup
    terminalEl.value.addEventListener('mouseup', (event: MouseEvent) => {
      setTimeout(() => {
        const selection = terminal.value?.getSelection()
        if (selection && selection.trim()) {
          selectedText.value = selection.trim()

          const terminalRect = terminalEl.value?.getBoundingClientRect()
          if (terminalRect) {
            popupPosition.value = {
              x: Math.min(event.clientX - terminalRect.left, terminalRect.width - 180),
              y: Math.max(event.clientY - terminalRect.top - 40, 0),
            }
          }

          showSelectionPopup.value = true
        }
      }, 10)
    })

    // Use ResizeObserver instead of window resize for container-level resize
    resizeObserver = new ResizeObserver(() => {
      if (fitAddon.value && terminal.value) {
        fitAddon.value.fit()
      }
    })
    resizeObserver.observe(terminalEl.value)

    // If in multi-pane mode, create terminal via pane_create is handled by paneStore
    // For legacy single-pane, the store handles create_terminal on connect
    if (!props.paneId) {
      terminalStore.connect()
    }
  })

  onUnmounted(() => {
    if (shellOutputHandler) {
      if (props.paneId && terminalStore.socket) {
        terminalStore.socket.off('terminal_output', shellOutputHandler as any)
      } else {
        terminalStore.offShellOutput(shellOutputHandler)
      }
    }
    resizeObserver?.disconnect()
    terminal.value?.dispose()
  })

  // Re-fit when focus changes
  watch(
    () => props.isFocused,
    (focused) => {
      if (focused && fitAddon.value) {
        // Small delay to let layout settle
        setTimeout(() => fitAddon.value?.fit(), 50)
      }
    }
  )

  const sendInput = (input: string) => {
    if (props.paneId) {
      // Multi-pane: send to specific pane
      if (terminalStore.socket) {
        terminalStore.socket.emit('pane_input', {
          pane_id: props.paneId,
          data: input,
        })
      }
    } else {
      // Legacy: send to store
      terminalStore.sendInput(input)
    }
  }

  const hideSelectionPopup = () => {
    showSelectionPopup.value = false
    selectedText.value = ''
  }

  const onCopyAction = () => {
    // Toast notification could go here
  }

  const onSendToAI = (text: string) => {
    const chatMessage = {
      type: 'user',
      message: `Please analyze this terminal output: ${text}`,
      timestamp: new Date(),
      source: 'terminal_selection',
    }
    terminalStore.sendChatMessage(chatMessage)
  }
</script>

<style scoped>
  .terminal-container {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    background-color: var(--bg-secondary);
    color: var(--text-main);
    font-family: 'Inter', system-ui, sans-serif;
    position: relative;
    min-height: 80px;
    border: 2px solid transparent;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  .terminal-container.focused {
    border-color: var(--accent-color);
    box-shadow: inset 0 0 10px var(--accent-glow);
  }

  .pane-title-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    background-color: rgba(0, 0, 0, 0.2);
    border-bottom: 1px solid var(--border-color);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    flex-shrink: 0;
    color: var(--text-muted);
  }

  .pane-title {
    color: var(--text-main);
  }

  .pane-session {
    opacity: 0.5;
    font-family: monospace;
    font-size: 9px;
  }

  .connection-status {
    padding: 10px 16px;
    background-color: var(--bg-glass);
    border-bottom: 1px solid var(--border-color);
    backdrop-filter: blur(8px);
  }

  .status-indicator {
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .status-connected {
    color: var(--accent-color);
  }
  .status-connecting,
  .status-reconnecting {
    color: #ff9800;
  }
  .status-disconnected {
    color: #f44336;
  }

  .reconnect-info {
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 4px;
  }

  .lock-status {
    padding: 12px;
    background-color: #f44336;
    border-bottom: 1px solid var(--border-color);
    text-align: center;
    box-shadow: 0 4px 12px rgba(244, 67, 54, 0.3);
  }

  .lock-indicator {
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #ffffff;
  }

  .terminal-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.4);
    pointer-events: none;
    z-index: 10;
    backdrop-filter: grayscale(0.5) blur(1px);
  }

  .xterm-container {
    flex: 1;
    min-height: 0;
    background-color: var(--bg-secondary);
    padding: 4px;
  }

  /* Customize xterm scrollbar if possible or just use overflow */
  :deep(.xterm-viewport::-webkit-scrollbar) {
    width: 6px;
  }
  :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
    background: var(--border-color);
    border-radius: 10px;
  }
</style>
