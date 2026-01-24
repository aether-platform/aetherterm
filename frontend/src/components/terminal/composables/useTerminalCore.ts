/**
 * Core terminal functionality composable
 */

import { ref, nextTick, onBeforeUnmount } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { SearchAddon } from '@xterm/addon-search'
import { WebLinksAddon } from '@xterm/addon-web-links'
import { useThemeStore } from '../../../stores/themeStore'
import { useAetherTerminalStore } from '../../../stores/aetherTerminalStore'

export function useTerminalCore() {
  // Refs
  const terminal = ref<Terminal | null>(null)
  const fitAddon = ref<FitAddon | null>(null)
  const searchAddon = ref<SearchAddon | null>(null)
  const webLinksAddon = ref<WebLinksAddon | null>(null)

  // Stores
  const themeStore = useThemeStore()
  const aetherStore = useAetherTerminalStore()

  // Terminal initialization
  const initializeTerminal = async (elementId: string) => {
    if (terminal.value) {
      console.warn('Terminal already initialized')
      return terminal.value
    }

    try {
      // Create terminal instance
      terminal.value = new Terminal({
        cursorBlink: true,
        cursorStyle: 'block',
        fontFamily: '"Fira Code", "Monaco", "Menlo", "Ubuntu Mono", monospace',
        fontSize: 14,
        lineHeight: 1.2,
        theme: getTerminalTheme(),
        allowProposedApi: true,
      })

      // Create and load addons
      fitAddon.value = new FitAddon()
      searchAddon.value = new SearchAddon()
      webLinksAddon.value = new WebLinksAddon()

      terminal.value.loadAddon(fitAddon.value)
      terminal.value.loadAddon(searchAddon.value)
      terminal.value.loadAddon(webLinksAddon.value)

      // Wait for next tick to ensure DOM element exists
      await nextTick()
      
      const element = document.getElementById(elementId)
      if (!element) {
        throw new Error(`Terminal element with ID ${elementId} not found`)
      }

      // Open terminal in DOM element
      terminal.value.open(element)
      
      // Fit terminal to container
      fitTerminal()

      // Setup event listeners
      setupTerminalEvents()

      console.log('Terminal initialized successfully')
      return terminal.value
    } catch (error) {
      console.error('Error initializing terminal:', error)
      throw error
    }
  }

  const getTerminalTheme = () => {
    const isDark = themeStore.isDarkMode
    
    return {
      background: isDark ? '#1a1a1a' : '#ffffff',
      foreground: isDark ? '#ffffff' : '#000000',
      cursor: isDark ? '#ffffff' : '#000000',
      cursorAccent: isDark ? '#000000' : '#ffffff',
      selection: isDark ? '#3e4451' : '#c7c7c7',
      black: isDark ? '#1e1e1e' : '#000000',
      red: '#e06c75',
      green: '#98c379',
      yellow: '#e5c07b',
      blue: '#61afef',
      magenta: '#c678dd',
      cyan: '#56b6c2',
      white: isDark ? '#ffffff' : '#555555',
      brightBlack: isDark ? '#5c6370' : '#666666',
      brightRed: '#e06c75',
      brightGreen: '#98c379',
      brightYellow: '#e5c07b',
      brightBlue: '#61afef',
      brightMagenta: '#c678dd',
      brightCyan: '#56b6c2',
      brightWhite: '#ffffff',
    }
  }

  const setupTerminalEvents = () => {
    if (!terminal.value) return

    // Handle data input from user
    terminal.value.onData((data) => {
      if (aetherStore.socket?.connected && aetherStore.currentSessionId) {
        aetherStore.socket.emit('terminal_input', {
          session: aetherStore.currentSessionId,
          data: data
        })
      }
    })

    // Handle terminal resize
    terminal.value.onResize(({ cols, rows }) => {
      if (aetherStore.socket?.connected && aetherStore.currentSessionId) {
        aetherStore.socket.emit('terminal_resize', {
          session: aetherStore.currentSessionId,
          cols: cols,
          rows: rows
        })
      }
    })

    // Handle selection change
    terminal.value.onSelectionChange(() => {
      // Could emit selection events here if needed
    })
  }

  const fitTerminal = () => {
    if (fitAddon.value) {
      try {
        fitAddon.value.fit()
      } catch (error) {
        console.warn('Error fitting terminal:', error)
      }
    }
  }

  const writeToTerminal = (data: string) => {
    if (terminal.value) {
      terminal.value.write(data)
    }
  }

  const clearTerminal = () => {
    if (terminal.value) {
      terminal.value.clear()
    }
  }

  const resizeTerminal = (cols: number, rows: number) => {
    if (terminal.value) {
      terminal.value.resize(cols, rows)
    }
  }

  const focusTerminal = () => {
    if (terminal.value) {
      terminal.value.focus()
    }
  }

  const searchInTerminal = (query: string, direction: 'previous' | 'next' = 'next') => {
    if (searchAddon.value && query) {
      if (direction === 'next') {
        searchAddon.value.findNext(query)
      } else {
        searchAddon.value.findPrevious(query)
      }
    }
  }

  const getTerminalSelection = (): string => {
    return terminal.value?.getSelection() || ''
  }

  const disposeTerminal = () => {
    if (terminal.value) {
      terminal.value.dispose()
      terminal.value = null
    }
    fitAddon.value = null
    searchAddon.value = null
    webLinksAddon.value = null
  }

  // Cleanup
  onBeforeUnmount(() => {
    disposeTerminal()
  })

  return {
    // Refs
    terminal,
    fitAddon,
    searchAddon,
    webLinksAddon,
    
    // Methods
    initializeTerminal,
    fitTerminal,
    writeToTerminal,
    clearTerminal,
    resizeTerminal,
    focusTerminal,
    searchInTerminal,
    getTerminalSelection,
    disposeTerminal,
    getTerminalTheme,
  }
}