import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type UIMode = 'terminal-first' | 'chat-first'

const STORAGE_KEYS = {
  mode: 'aetherterm-ui-mode',
  onboarding: 'aetherterm-onboarding-complete',
  terminalPanelHeight: 'aetherterm-terminal-panel-height',
} as const

export const useUIModeStore = defineStore('uiMode', () => {
  const currentMode = ref<UIMode>('terminal-first')
  const hasCompletedOnboarding = ref(false)
  const terminalPanelHeight = ref(250)
  const isTerminalPanelCollapsed = ref(false)
  const isTransitioning = ref(false)

  // Getters
  const isTerminalFirst = computed(() => currentMode.value === 'terminal-first')
  const isChatFirst = computed(() => currentMode.value === 'chat-first')
  const showOnboarding = computed(() => !hasCompletedOnboarding.value)

  // Actions
  function setMode(mode: UIMode) {
    if (currentMode.value === mode) return
    isTransitioning.value = true
    currentMode.value = mode
    localStorage.setItem(STORAGE_KEYS.mode, mode)
    setTimeout(() => {
      isTransitioning.value = false
    }, 300)
  }

  function toggleMode() {
    setMode(currentMode.value === 'terminal-first' ? 'chat-first' : 'terminal-first')
  }

  function completeOnboarding(mode: UIMode) {
    hasCompletedOnboarding.value = true
    localStorage.setItem(STORAGE_KEYS.onboarding, 'true')
    setMode(mode)
  }

  function toggleTerminalPanel() {
    isTerminalPanelCollapsed.value = !isTerminalPanelCollapsed.value
  }

  function setTerminalPanelHeight(height: number) {
    terminalPanelHeight.value = Math.max(100, Math.min(height, window.innerHeight - 200))
    localStorage.setItem(STORAGE_KEYS.terminalPanelHeight, String(terminalPanelHeight.value))
  }

  function loadFromStorage() {
    const savedMode = localStorage.getItem(STORAGE_KEYS.mode)
    if (savedMode === 'terminal-first' || savedMode === 'chat-first') {
      currentMode.value = savedMode
    }

    const savedOnboarding = localStorage.getItem(STORAGE_KEYS.onboarding)
    hasCompletedOnboarding.value = savedOnboarding === 'true'

    const savedHeight = localStorage.getItem(STORAGE_KEYS.terminalPanelHeight)
    if (savedHeight) {
      terminalPanelHeight.value = Number(savedHeight) || 250
    }
  }

  return {
    // State
    currentMode,
    hasCompletedOnboarding,
    terminalPanelHeight,
    isTerminalPanelCollapsed,
    isTransitioning,

    // Getters
    isTerminalFirst,
    isChatFirst,
    showOnboarding,

    // Actions
    setMode,
    toggleMode,
    completeOnboarding,
    toggleTerminalPanel,
    setTerminalPanelHeight,
    loadFromStorage,
  }
})
