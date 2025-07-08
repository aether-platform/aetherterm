<template>
  <div class="aether-terminal-container" @click="handleClick" ref="containerRef">
    <div 
      :id="terminalElementId"
      class="aether-terminal"
      ref="terminalRef"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { FitAddon } from '@xterm/addon-fit'
import { SearchAddon } from '@xterm/addon-search'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { useAetherTerminalStore } from '../../stores/aetherTerminalStore'
import { useScreenBufferStore } from '../../stores/screenBufferStore'
import { useTerminalPaneStore } from '../../stores/terminalPaneStore'
import { useTerminalTabStore } from '../../stores/terminalTabStore'
import { useThemeStore } from '../../stores/themeStore'
import { hasRole } from '@/utils/jwtUtils'
import { useTerminalPermissionsStore } from '../../stores/terminalPermissionsStore'

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
const terminal = ref<Terminal | null>(null)
const fitAddon = ref<FitAddon | null>(null)
const searchAddon = ref<SearchAddon | null>(null)
const webLinksAddon = ref<WebLinksAddon | null>(null)

// Store references（新しいクリーンなストア）
const aetherStore = useAetherTerminalStore()
const tabStore = useTerminalTabStore()
const paneStore = useTerminalPaneStore()
const themeStore = useThemeStore()
const screenBufferStore = useScreenBufferStore()

// State
const sessionId = ref<string | null>(null)
const isInitialized = ref(false)

// Computed
const terminalElementId = computed(() => `aether-${props.mode}-${props.id}`)

// Terminal theme configuration
const terminalTheme = computed(() => {
  const colors = themeStore.currentColors
  if (!colors) {
    // Fallback theme
    return {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#ffffff',
      selection: '#264f78',
      black: '#000000',
      red: '#cd3131',
      green: '#0dbc79',
      yellow: '#e5e510',
      blue: '#2472c8',
      magenta: '#bc3fbc',
      cyan: '#11a8cd',
      white: '#e5e5e5',
      brightBlack: '#666666',
      brightRed: '#f14c4c',
      brightGreen: '#23d18b',
      brightYellow: '#f5f543',
      brightBlue: '#3b8eea',
      brightMagenta: '#d670d6',
      brightCyan: '#29b8db',
      brightWhite: '#e5e5e5'
    }
  }
  
  return {
    background: colors.background,
    foreground: colors.foreground,
    cursor: colors.cursor,
    selection: colors.selection,
    black: colors.black,
    red: colors.red,
    green: colors.green,
    yellow: colors.yellow,
    blue: colors.blue,
    magenta: colors.magenta,
    cyan: colors.cyan,
    white: colors.white,
    brightBlack: colors.bright_black,
    brightRed: colors.bright_red,
    brightGreen: colors.bright_green,
    brightYellow: colors.bright_yellow,
    brightBlue: colors.bright_blue,
    brightMagenta: colors.bright_magenta,
    brightCyan: colors.bright_cyan,
    brightWhite: colors.bright_white
  }
})

// セッション管理（統一）- 安定したセッション管理
const getCurrentSession = () => {
  if (props.mode === 'pane') {
    return paneStore.getPaneSession(props.id)
  } else {
    return tabStore.getTabSession(props.id)
  }
}

const setCurrentSession = (newSessionId: string) => {
  if (props.mode === 'pane') {
    paneStore.setPaneSession(props.id, newSessionId)
  } else {
    tabStore.setTabSession(props.id, newSessionId)
  }
  sessionId.value = newSessionId
}

// 既存のセッションIDを取得（サーバーが割り当てたもののみ）
const getExistingSession = () => {
  if (props.mode === 'pane') {
    return paneStore.getPaneSession(props.id)
  } else {
    return tabStore.getTabSession(props.id)
  }
}

// ターミナル初期化（シンプル化）
const initializeTerminal = async () => {
  // Reduced logging for performance
  
  await nextTick()
  
  if (!terminalRef.value) {
    console.error('❌ AETHER_TERMINAL: Terminal ref not found')
    return
  }

  // xterm.js作成 - パフォーマンス最適化
  terminal.value = new Terminal({
    cursorBlink: false, // パフォーマンス向上のため無効化
    theme: terminalTheme.value,
    fontSize: themeStore.themeConfig.fontSize,
    fontFamily: themeStore.themeConfig.fontFamily,
    scrollback: 2000, // Reduced for better performance
    fastScrollModifier: 'shift',
    rightClickSelectsWord: false,
    allowProposedApi: true, // Enable performance optimizations
    allowTransparency: false, // Disable transparency for performance
    disableStdin: false,
    convertEol: true,
    // Performance optimizations
    drawBoldTextInBrightColors: false,
    minimumContrastRatio: 1 // Disable contrast checking for performance
  })

  // Load addons
  fitAddon.value = new FitAddon()
  searchAddon.value = new SearchAddon()
  webLinksAddon.value = new WebLinksAddon()
  
  terminal.value.loadAddon(fitAddon.value)
  terminal.value.loadAddon(searchAddon.value)
  terminal.value.loadAddon(webLinksAddon.value)

  // ターミナルをDOMに追加
  terminal.value.open(terminalRef.value)
  
  // ResizeObserverでfitを最適化
  let fitTimeout: number | null = null
  const debouncedFit = () => {
    if (fitTimeout) clearTimeout(fitTimeout)
    fitTimeout = setTimeout(() => {
      fitAddon.value?.fit()
      fitTimeout = null
    }, 100)
  }
  
  // 初回サイズ調整
  debouncedFit()

  // 入力処理セットアップ
  setupInput()

  // セッション要求
  await requestSession()

  isInitialized.value = true
  emit('terminal-initialized')
  
  // Terminal initialized
}

// 入力処理（シンプル化）
const setupInput = () => {
  if (!terminal.value) return

  const permissionsStore = useTerminalPermissionsStore()
  
  terminal.value.onData((data) => {
    if (sessionId.value) {
      // Check if user has Viewer role
      const isViewer = hasRole('Viewer')
      if (isViewer) {
        console.warn(`⚠️ AETHER_TERMINAL: Input blocked for Viewer role`)
        terminal.value?.write('\r\n\x1b[33m[Read-only mode: Input disabled for Viewer role]\x1b[0m\r\n')
        return
      }
      
      // Check if user has control permission
      if (!permissionsStore.hasControlPermission(sessionId.value)) {
        console.warn(`⚠️ AETHER_TERMINAL: Input blocked - no permission`)
        terminal.value?.write('\r\n\x1b[33m[Read-only mode: You do not have permission to control this terminal]\x1b[0m\r\n')
        return
      }
      
      // Add input to screen buffer (only for meaningful input)
      if (data.length > 0 && !data.match(/^\x1b/)) { // Skip escape sequences
        screenBufferStore.addLine(sessionId.value, data, 'input')
      }
      aetherStore.sendInput(sessionId.value, data)
    } else {
      console.warn(`⚠️ AETHER_TERMINAL: No session for ${props.mode}:`, props.id)
    }
  })

  // Keyboard shortcuts
  terminal.value.attachCustomKeyEventHandler((event) => {
    const permissionsStore = useTerminalPermissionsStore()
    const isViewer = hasRole('Viewer')
    const hasPermission = sessionId.value ? permissionsStore.hasControlPermission(sessionId.value) : true
    
    // Ctrl+Shift+F for search (allowed for all roles)
    if (event.ctrlKey && event.shiftKey && event.key === 'F') {
      event.preventDefault()
      openSearch()
      return false
    }
    
    // Ctrl+Shift+C for copy (allowed for all roles)
    if (event.ctrlKey && event.shiftKey && event.key === 'C') {
      event.preventDefault()
      copySelection()
      return false
    }
    
    // Ctrl+Shift+V for paste (blocked for Viewer role or no permission)
    if (event.ctrlKey && event.shiftKey && event.key === 'V') {
      event.preventDefault()
      if (isViewer || !hasPermission) {
        console.warn('Paste disabled: no permission')
        return false
      }
      pasteFromClipboard()
      return false
    }
    
    // Block all other keyboard input for Viewer role or no permission
    if (isViewer || !hasPermission) {
      return false
    }
    
    return true
  })
}

// セッション要求（統一）- 安定したセッション管理
const requestSession = async () => {
  // First check if we already have a server-assigned session ID
  const existingSession = props.mode === 'pane' 
    ? paneStore.getPaneSession(props.id)
    : tabStore.getTabSession(props.id)
    
  if (existingSession) {
    console.log(`📺 AETHER_TERMINAL: Using existing server session: ${existingSession}`)
    sessionId.value = existingSession
    setupOutput()
    return
  }
  // Ensure connection is established before proceeding
  if (!aetherStore.connectionState.isConnected) {
    console.log('⏳ AETHER_TERMINAL: Waiting for connection before requesting session...')
    
    // Wait a bit for the global connection to be established
    let retries = 0
    while (!aetherStore.connectionState.isConnected && retries < 10) {
      await new Promise(resolve => setTimeout(resolve, 500))
      retries++
    }
    
    if (!aetherStore.connectionState.isConnected) {
      console.log('⏳ AETHER_TERMINAL: Still not connected, attempting direct connection...')
      const connected = await aetherStore.connect()
      if (!connected) {
        console.error('❌ AETHER_TERMINAL: Failed to establish connection for session request')
        // Continue with local-only mode
      }
    }
  }
  
  // Check if we already have a server-assigned session ID
  const existingSessionId = getExistingSession()
  if (existingSessionId) {
    console.log(`📺 AETHER_TERMINAL: Found existing session: ${existingSessionId}`)
    sessionId.value = existingSessionId
    setupOutput()
    
    // Try to reconnect to this existing session
    try {
      const reconnected = await aetherStore.reconnectSession(existingSessionId)
      if (reconnected) {
        console.log(`📺 AETHER_TERMINAL: Successfully reconnected to backend session`)
        // Backend will send history automatically via terminal_output events
        return
      }
    } catch (error) {
      console.warn('⚠️ AETHER_TERMINAL: Backend reconnection failed:', error)
    }
  }
  
  // Create new backend session if reconnection failed
  try {
    const newSessionId = await aetherStore.requestSession(props.id, props.mode, props.subType || 'pure')
    if (newSessionId) {
      // Always use the server-generated session ID
      console.log(`📺 AETHER_TERMINAL: Server created session: ${newSessionId}`)
      setCurrentSession(newSessionId)
      setupOutput() // Re-setup output with new session ID
    }
  } catch (error) {
    console.error('❌ AETHER_TERMINAL: Failed to create backend session:', error)
  }
}

// 出力処理（シンプル化）
const setupOutput = () => {
  if (!sessionId.value || !terminal.value) return

  // 出力バッファリングでパフォーマンス最適化
  let outputBuffer = ''
  let flushTimeout: number | null = null
  
  const outputCallback = (data: string) => {
    outputBuffer += data
    
    if (flushTimeout) clearTimeout(flushTimeout)
    
    flushTimeout = setTimeout(() => {
      if (outputBuffer && terminal.value && sessionId.value) {
        try {
          // Batch write for better performance
          terminal.value.write(outputBuffer)
          // Add output to screen buffer - handle history vs live output
          processOutputForScreenBuffer(sessionId.value, outputBuffer)
        } catch (error) {
          // Simplified error handling for performance
          const filteredBuffer = outputBuffer.replace(/[\x7F\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
          if (filteredBuffer) {
            try {
              terminal.value.write(filteredBuffer)
              processOutputForScreenBuffer(sessionId.value, filteredBuffer)
            } catch (retryError) {
              // Silent fail for performance
            }
          }
        }
        outputBuffer = ''
      }
      flushTimeout = null
    }, 8) // Faster flush for better responsiveness
  }

  aetherStore.registerOutputCallback(sessionId.value, outputCallback)
  console.log(`📺 AETHER_TERMINAL: Output setup for ${props.mode}:`, props.id)
}

// Process output for screen buffer - simplified
const processOutputForScreenBuffer = (sessionId: string, data: string) => {
  // Simply add to buffer for local display
  screenBufferStore.addLine(sessionId, data, 'output')
}

// Restore terminal content from screen buffer - 高速化
const restoreTerminalFromBuffer = (buffer: any) => {
  if (!terminal.value || !buffer || buffer.lines.length === 0) return
  
  // ターミナルをクリアしてから復元
  terminal.value.clear()
  
  // バッファの内容を一括で書き込み（パフォーマンス向上）
  const allContent = buffer.lines
    .filter((line: any) => line.content)
    .map((line: any) => line.content)
    .join('')
  
  if (allContent && terminal.value) {
    try {
      terminal.value.write(allContent)
    } catch (error) {
      // エラーがあった場合は一行ずつ処理
      buffer.lines.forEach((line: any) => {
        if (line.content && terminal.value) {
          try {
            terminal.value.write(line.content)
          } catch (lineError) {
            // サイレントフェイル
          }
        }
      })
    }
  }
}

// テーマ更新
const updateTerminalTheme = () => {
  if (!terminal.value) return
  
  console.log(`🎨 AETHER_TERMINAL: Updating theme for ${props.mode}:`, props.id, themeStore.themeConfig.colorScheme)
  
  // Update terminal theme
  terminal.value.options.theme = terminalTheme.value
  terminal.value.options.fontSize = themeStore.themeConfig.fontSize
  terminal.value.options.fontFamily = themeStore.themeConfig.fontFamily
  terminal.value.options.cursorBlink = themeStore.themeConfig.cursorBlink
  
  // Refresh terminal to apply changes
  terminal.value.refresh(0, terminal.value.rows - 1)
}

// クリック処理
const handleClick = () => {
  emit('click')
  terminal.value?.focus()
}

// 接続状態監視
watch(() => aetherStore.connectionState.isConnected, (connected) => {
  if (connected && !sessionId.value) {
    console.log(`🔌 AETHER_TERMINAL: Connection restored, requesting session for ${props.mode}:`, props.id)
    requestSession()
  }
})

// テーマ変更監視 - 統合・debounce最適化
let themeUpdateTimeout: number | null = null
const debouncedThemeUpdate = () => {
  if (themeUpdateTimeout) clearTimeout(themeUpdateTimeout)
  themeUpdateTimeout = setTimeout(() => {
    updateTerminalTheme()
    // レイアウト変更が必要な場合のみfit実行
    if (fitAddon.value) {
      fitAddon.value.fit()
    }
    themeUpdateTimeout = null
  }, 50) // 50msでdebounce
}

// 統合されたテーマwatcher
watchEffect(() => {
  // currentColors, fontSize, fontFamilyの変更を監視
  themeStore.currentColors
  themeStore.themeConfig.fontSize
  themeStore.themeConfig.fontFamily
  
  if (terminal.value) {
    debouncedThemeUpdate()
  }
})

// Watch for connection state changes
watch(() => aetherStore.connectionState.isConnected, (isConnected) => {
  if (isConnected && !terminal.value && terminalRef.value) {
    console.log('🔄 AETHER_TERMINAL: Connection established, initializing terminal...')
    initializeTerminal()
  }
})

// ライフサイクル
onMounted(async () => {
  // Terminal mounted
  
  // Initialize terminal immediately if already connected
  if (aetherStore.connectionState.isConnected) {
    initializeTerminal()
  } else {
    // Connection will be handled by the watcher above
    console.log('⏳ AETHER_TERMINAL: Waiting for connection to initialize terminal...')
  }
})

onBeforeUnmount(() => {
  // Terminal unmounting
  
  // クリーンアップ
  if (sessionId.value) {
    aetherStore.unregisterOutputCallback(sessionId.value)
  }
  
  // Safely dispose terminal and addons
  if (terminal.value) {
    try {
      terminal.value.dispose()
    } catch (error) {
      console.warn('⚠️ AETHER_TERMINAL: Error disposing terminal:', error)
    }
  }
  
  // Clear references
  terminal.value = null
  fitAddon.value = null
  searchAddon.value = null
  webLinksAddon.value = null
})

// Screen buffer API
const clearScreenBuffer = () => {
  if (sessionId.value) {
    screenBufferStore.clearBuffer(sessionId.value)
    terminal.value?.clear()
  }
}

const saveBufferState = (stateName: string) => {
  if (sessionId.value) {
    screenBufferStore.saveBufferState(sessionId.value, stateName)
  }
}

const restoreBufferState = (stateName: string) => {
  if (sessionId.value) {
    const restored = screenBufferStore.restoreBufferState(sessionId.value, stateName)
    if (restored && terminal.value) {
      terminal.value.clear()
      const lines = screenBufferStore.getBufferLines(sessionId.value)
      lines.forEach(line => {
        terminal.value?.write(line.content)
      })
    }
    return restored
  }
  return false
}

const exportBuffer = (format: 'text' | 'json' = 'text') => {
  if (sessionId.value) {
    return screenBufferStore.exportBuffer(sessionId.value, format)
  }
  return ''
}

const getBufferStats = () => {
  if (sessionId.value) {
    return screenBufferStore.getBufferStats(sessionId.value)
  }
  return { totalLines: 0, currentLine: 0, maxLines: 0 }
}

// Search functionality
const openSearch = () => {
  if (!searchAddon.value) return
  
  const searchTerm = prompt('Search terminal:')
  if (searchTerm) {
    searchAddon.value.findNext(searchTerm)
  }
}

const searchNext = (term: string) => {
  if (searchAddon.value) {
    searchAddon.value.findNext(term)
  }
}

const searchPrevious = (term: string) => {
  if (searchAddon.value) {
    searchAddon.value.findPrevious(term)
  }
}

// Copy/Paste functionality
const copySelection = () => {
  if (!terminal.value) return
  
  const selection = terminal.value.getSelection()
  if (selection) {
    navigator.clipboard.writeText(selection).then(() => {
      console.log('📋 TERMINAL: Text copied to clipboard')
    }).catch((err) => {
      console.error('❌ TERMINAL: Failed to copy text', err)
    })
  }
}

const pasteFromClipboard = async () => {
  if (!terminal.value || !sessionId.value) return
  
  try {
    const text = await navigator.clipboard.readText()
    if (text) {
      aetherStore.sendInput(sessionId.value, text)
      console.log('📋 TERMINAL: Text pasted from clipboard')
    }
  } catch (err) {
    console.error('❌ TERMINAL: Failed to paste text', err)
  }
}

// Selection utilities
const selectAll = () => {
  if (terminal.value) {
    terminal.value.selectAll()
  }
}

const clearSelection = () => {
  if (terminal.value) {
    terminal.value.clearSelection()
  }
}

// 外部API
defineExpose({
  terminal,
  sessionId,
  focus: () => terminal.value?.focus(),
  fit: () => fitAddon.value?.fit(),
  clear: () => terminal.value?.clear(),
  write: (data: string) => terminal.value?.write(data),
  // Screen buffer API
  clearScreenBuffer,
  saveBufferState,
  restoreBufferState,
  exportBuffer,
  getBufferStats,
  // Search API
  openSearch,
  searchNext,
  searchPrevious,
  // Copy/Paste API
  copySelection,
  pasteFromClipboard,
  selectAll,
  clearSelection
})
</script>

<style scoped lang="scss">
.aether-terminal-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--terminal-background, #1e1e1e);
  position: relative;
  overflow: hidden;
  font-family: var(--terminal-font-family);
  font-size: var(--terminal-font-size);
  
  // Smooth transitions for theme changes
  transition: background-color 0.3s ease;
}

.aether-terminal {
  flex: 1;
  width: 100%;
  height: 100%;
  
  :deep(.xterm) {
    height: 100% !important;
    width: 100% !important;
    font-family: var(--terminal-font-family) !important;
    font-size: var(--terminal-font-size) !important;
  }
  
  :deep(.xterm-viewport) {
    background-color: var(--terminal-background, #1e1e1e) !important;
  }
  
  :deep(.xterm-screen) {
    background-color: var(--terminal-background, #1e1e1e) !important;
  }
  
  :deep(.xterm-cursor-layer) {
    .xterm-cursor {
      background-color: var(--terminal-cursor, #ffffff) !important;
    }
  }
  
  :deep(.xterm-selection) {
    background-color: var(--terminal-selection, #264f78) !important;
  }
  
  // Scrollbar theming
  :deep(.xterm-viewport)::-webkit-scrollbar {
    width: 8px;
  }
  
  :deep(.xterm-viewport)::-webkit-scrollbar-track {
    background: var(--terminal-background, #1e1e1e);
  }
  
  :deep(.xterm-viewport)::-webkit-scrollbar-thumb {
    background: var(--terminal-bright-black, #666666);
    border-radius: 4px;
    
    &:hover {
      background: var(--terminal-white, #e5e5e5);
    }
  }
}
</style>