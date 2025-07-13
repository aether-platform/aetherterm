<template>
  <div class="aether-terminal-container" @click="handleClick" ref="containerRef">
    <div 
      v-if="isConnecting"
      class="terminal-loading"
    >
      <div class="loading-spinner"></div>
      <div class="loading-text">Connecting to terminal...</div>
    </div>
    <div 
      v-show="!isConnecting"
      :id="terminalElementId"
      class="aether-terminal"
      ref="terminalRef"
      :style="{ visibility: isConnecting ? 'hidden' : 'visible' }"
    ></div>
    <div v-if="searchVisible" class="terminal-search">
      <input
        v-model="searchTerm"
        @keydown.enter="searchNext(searchTerm)"
        @keydown.shift.enter="searchPrevious(searchTerm)"
        @keydown.escape="closeSearch"
        @input="onSearchInput"
        placeholder="Search (Enter: next, Shift+Enter: previous, Esc: close)"
        class="search-input"
        ref="searchInput"
      />
      <div class="search-controls">
        <button @click="searchPrevious(searchTerm)" class="search-button">↑</button>
        <button @click="searchNext(searchTerm)" class="search-button">↓</button>
        <button @click="closeSearch" class="search-button">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FitAddon } from '@xterm/addon-fit'
import { SearchAddon } from '@xterm/addon-search'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect, type Ref } from 'vue'
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
const searchInput = ref<HTMLInputElement | null>(null)

// Store references（新しいクリーンなストア）
const aetherStore = useAetherTerminalStore()
const tabStore = useTerminalTabStore()
const paneStore = useTerminalPaneStore()
const themeStore = useThemeStore()
const screenBufferStore = useScreenBufferStore()

// State
const sessionId = ref<string | null>(null)
const isInitialized = ref(false)
const isConnecting = ref(false)
const searchTerm = ref('')
const searchVisible = ref(false)
let fitTimeout: number | null = null
let themeUpdateTimeout: number | null = null

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
  
  // Also persist to localStorage for page reload recovery
  try {
    const savedSessions = JSON.parse(localStorage.getItem('aetherterm_terminal_sessions') || '[]')
    const existingIndex = savedSessions.findIndex((s: any) => s.paneId === props.id)
    const sessionData = {
      sessionId: newSessionId,
      tabId: props.mode === 'tab' ? props.id : undefined,
      paneId: props.id,
      type: 'terminal',
      subType: props.subType,
      lastActive: new Date().toISOString()
    }
    
    if (existingIndex >= 0) {
      savedSessions[existingIndex] = sessionData
    } else {
      savedSessions.push(sessionData)
    }
    
    localStorage.setItem('aetherterm_terminal_sessions', JSON.stringify(savedSessions))
    console.log(`💾 AETHER_TERMINAL: Persisted session ${newSessionId} to localStorage`)
  } catch (error) {
    console.warn('⚠️ AETHER_TERMINAL: Failed to persist session to localStorage:', error)
  }
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
  const debouncedFit = () => {
    if (fitTimeout) clearTimeout(fitTimeout)
    fitTimeout = setTimeout(() => {
      fitAddon.value?.fit()
      fitTimeout = null
    }, 100)
  }
  
  // ResizeObserver for automatic terminal fitting
  if (terminalRef.value) {
    const resizeObserver = new ResizeObserver(() => {
      debouncedFit()
    })
    resizeObserver.observe(terminalRef.value)
    
    // Store observer for cleanup
    terminal.value._resizeObserver = resizeObserver
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
  // Debug: Log current pane store state
  console.log(`📺 AETHER_TERMINAL: Current pane store panes:`, paneStore.panes.map(p => ({ id: p.id, sessionId: p.sessionId })))
  console.log(`📺 AETHER_TERMINAL: Looking for ${props.mode} ID: ${props.id}`)
  
  // Additional debug for tab mode
  if (props.mode === 'tab') {
    console.log(`📺 AETHER_TERMINAL: Current tab store tabs:`, tabStore.tabs.map(t => ({ id: t.id, sessionId: t.sessionId })))
  }
  
  // First check if we already have a server-assigned session ID
  const existingSession = props.mode === 'pane' 
    ? paneStore.getPaneSession(props.id)
    : tabStore.getTabSession(props.id)
    
  console.log(`📺 AETHER_TERMINAL: Checking for existing session - mode: ${props.mode}, id: ${props.id}, existingSession: ${existingSession}`)
  
  // If no session found, wait a bit for workspace restoration to complete
  if (!existingSession) {
    console.log(`📺 AETHER_TERMINAL: No session found, waiting for workspace restoration...`)
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    const retrySession = props.mode === 'pane' 
      ? paneStore.getPaneSession(props.id)
      : tabStore.getTabSession(props.id)
    
    console.log(`📺 AETHER_TERMINAL: After waiting, retrySession: ${retrySession}`)
    console.log(`📺 AETHER_TERMINAL: Pane store after waiting:`, paneStore.panes.map(p => ({ id: p.id, sessionId: p.sessionId })))
  }
    
  if (existingSession) {
    console.log(`📺 AETHER_TERMINAL: Using existing server session: ${existingSession}`)
    sessionId.value = existingSession
    setupOutput()
    
    // Don't return here - continue to try reconnecting below
  } else {
    // If no session in store, try to restore from localStorage
    try {
      const WorkspacePersistenceManager = (await import('../../stores/workspace/persistenceManager')).WorkspacePersistenceManager
      const savedSessions = WorkspacePersistenceManager.loadTerminalSessions()
      const savedSession = savedSessions.find(s => s.paneId === props.id)
      if (savedSession) {
        console.log(`📺 AETHER_TERMINAL: Restored session from localStorage: ${savedSession.sessionId}`)
        sessionId.value = savedSession.sessionId
        setCurrentSession(savedSession.sessionId)
        setupOutput()
      }
    } catch (error) {
      console.warn('⚠️ AETHER_TERMINAL: Failed to restore session from localStorage:', error)
    }
  }
  
  // Ensure connection is established before proceeding
  if (!aetherStore.connectionState.isConnected) {
    console.log('⏳ AETHER_TERMINAL: Waiting for connection before requesting session...')
    isConnecting.value = true
    
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
        isConnecting.value = false
        // Continue with local-only mode
      }
    }
    isConnecting.value = false
  }
  
  // Check if we already have a server-assigned session ID (if not already set above)
  if (!sessionId.value) {
    const existingSessionId = getExistingSession()
    if (existingSessionId) {
      console.log(`📺 AETHER_TERMINAL: Found existing session: ${existingSessionId}`)
      sessionId.value = existingSessionId
      setupOutput()
    }
  }
  
  // If we have a session ID, try to reconnect
  if (sessionId.value) {
    // Ensure terminal is ready before reconnecting
    await nextTick()
    
    // Try to reconnect to this existing session
    try {
      const reconnected = await aetherStore.reconnectSession(sessionId.value)
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
          // Debug logging
          console.log(`✍️ AETHER_TERMINAL: Writing ${outputBuffer.length} chars to terminal`)
          
          // Batch write for better performance
          terminal.value.write(outputBuffer)
          // Add output to screen buffer - handle history vs live output
          processOutputForScreenBuffer(sessionId.value, outputBuffer)
        } catch (error) {
          console.error('❌ AETHER_TERMINAL: Error writing to terminal:', error)
          // Simplified error handling for performance
          const filteredBuffer = outputBuffer.replace(/[\x7F\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
          if (filteredBuffer) {
            try {
              terminal.value.write(filteredBuffer)
              processOutputForScreenBuffer(sessionId.value, filteredBuffer)
            } catch (retryError) {
              console.error('❌ AETHER_TERMINAL: Retry failed:', retryError)
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
  
  // Debug logging
  console.log(`📝 SCREEN_BUFFER: Added ${data.length} chars to buffer for session ${sessionId}`)
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

// Watch for tab activation to resize terminal
watch(() => {
  if (props.mode === 'pane') {
    const pane = paneStore.panes.find(p => p.id === props.id)
    return pane?.isActive
  } else {
    const tab = tabStore.tabs.find(t => t.id === props.id)
    return tab?.isActive
  }
}, (isActive) => {
  if (isActive && terminal.value && fitAddon.value) {
    // When tab becomes active, resize the terminal
    console.log(`🔄 AETHER_TERMINAL: Tab ${props.id} became active, fitting terminal`)
    nextTick(() => {
      fitAddon.value?.fit()
    })
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
  
  // Clear all timeouts to prevent memory leaks
  if (fitTimeout) {
    clearTimeout(fitTimeout)
    fitTimeout = null
  }
  if (themeUpdateTimeout) {
    clearTimeout(themeUpdateTimeout)
    themeUpdateTimeout = null
  }
  
  // クリーンアップ
  if (sessionId.value) {
    aetherStore.unregisterOutputCallback(sessionId.value)
  }
  
  // Safely dispose terminal and addons
  if (terminal.value) {
    try {
      // Cleanup ResizeObserver
      if (terminal.value._resizeObserver) {
        terminal.value._resizeObserver.disconnect()
      }
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
  searchVisible.value = true
  nextTick(() => {
    searchInput.value?.focus()
    searchInput.value?.select()
  })
}

const closeSearch = () => {
  searchVisible.value = false
  searchTerm.value = ''
  if (searchAddon.value) {
    searchAddon.value.clearDecorations()
  }
  terminal.value?.focus()
}

const onSearchInput = () => {
  if (searchAddon.value && searchTerm.value) {
    searchAddon.value.findNext(searchTerm.value, {
      regex: false,
      wholeWord: false,
      caseSensitive: false,
      decorations: {
        matchBackground: '#ffff00',
        matchBorder: '#ffff00',
        matchOverviewRuler: '#ffff00',
        activeMatchBackground: '#ff8800',
        activeMatchBorder: '#ff8800',
        activeMatchColorOverviewRuler: '#ff8800'
      }
    })
  }
}

const searchNext = (term: string) => {
  if (searchAddon.value && term) {
    searchAddon.value.findNext(term, {
      regex: false,
      wholeWord: false,
      caseSensitive: false
    })
  }
}

const searchPrevious = (term: string) => {
  if (searchAddon.value && term) {
    searchAddon.value.findPrevious(term, {
      regex: false,
      wholeWord: false,
      caseSensitive: false
    })
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

.terminal-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--terminal-foreground, #d4d4d4);

  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--terminal-background, #1e1e1e);
    border-top-color: var(--terminal-cyan, #11a8cd);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 16px;
  }

  .loading-text {
    font-size: 14px;
    opacity: 0.8;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.terminal-search {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 8px;
  background: var(--terminal-background, #1e1e1e);
  border: 1px solid var(--terminal-bright-black, #666666);
  border-radius: 4px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  z-index: 100;

  .search-input {
    background: var(--terminal-black, #000000);
    color: var(--terminal-foreground, #d4d4d4);
    border: 1px solid var(--terminal-bright-black, #666666);
    border-radius: 4px;
    padding: 4px 8px;
    font-family: var(--terminal-font-family);
    font-size: 14px;
    width: 300px;
    outline: none;

    &:focus {
      border-color: var(--terminal-cyan, #11a8cd);
    }

    &::placeholder {
      color: var(--terminal-bright-black, #666666);
      font-size: 12px;
    }
  }

  .search-controls {
    display: flex;
    gap: 4px;
  }

  .search-button {
    background: var(--terminal-bright-black, #666666);
    color: var(--terminal-foreground, #d4d4d4);
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    cursor: pointer;
    font-size: 14px;
    transition: background-color 0.2s;

    &:hover {
      background: var(--terminal-white, #e5e5e5);
      color: var(--terminal-background, #1e1e1e);
    }

    &:active {
      transform: translateY(1px);
    }
  }
}

// Search highlight styles
:deep(.xterm-search-bar__results) {
  background: var(--terminal-yellow, #e5e510) !important;
}

:deep(.xterm-search-bar__results.xterm-search-bar__results--current) {
  background: var(--terminal-red, #cd3131) !important;
}
</style>