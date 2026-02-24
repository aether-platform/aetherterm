<script setup lang="ts">
  import 'normalize.css'
  import { onMounted, onUnmounted, ref, watch } from 'vue'
  import AppHeader from './components/AppHeader.vue'
  import ChatFirstLayout from './components/ChatFirstLayout.vue'
  import ChatOverlay from './components/ChatOverlay.vue'
  import CommandPalette from './components/CommandPalette.vue'
  import DevJWTRegister from './components/DevJWTRegister.vue'
  import OnboardingTutorial from './components/OnboardingTutorial.vue'
  import PaneLayout from './components/PaneLayout.vue'
  import PaneTreeSidebar from './components/PaneTreeSidebar.vue'
  import PlatformHeader from './components/PlatformHeader.vue'
  import SupervisorControlPanel from './components/SupervisorControlPanel.vue'
  import { enableJWTDevRegister } from './config/environment'
  import { useAetherTerminalServiceStore } from './stores/aetherTerminalServiceStore'
  import { usePaneStore } from './stores/paneStore'
  import { useUIModeStore } from './stores/uiModeStore'

  const paneStore = usePaneStore()
  const terminalStore = useAetherTerminalServiceStore()
  const uiModeStore = useUIModeStore()

  // Sidebar visibility
  const isSidebarVisible = ref(true)
  const SIDEBAR_VISIBILITY_KEY = 'aetherterm-sidebar-visible'

  // Chat overlay (Terminal-first mode only)
  const isChatVisible = ref(true)
  const chatOverlayRef = ref<InstanceType<typeof ChatOverlay> | null>(null)

  // Right panel (supervisor/dev-auth)
  const activeTab = ref<'supervisor' | 'dev-auth' | null>(null)

  const showCommandPalette = ref(false)

  const loadSidebarVisibility = () => {
    const saved = localStorage.getItem(SIDEBAR_VISIBILITY_KEY)
    if (saved !== null) {
      isSidebarVisible.value = saved === 'true'
    }
  }

  const toggleSidebar = () => {
    isSidebarVisible.value = !isSidebarVisible.value
    localStorage.setItem(SIDEBAR_VISIBILITY_KEY, isSidebarVisible.value.toString())
  }

  const toggleRightPanel = (tab: 'supervisor' | 'dev-auth') => {
    if (activeTab.value === tab) {
      activeTab.value = null
    } else {
      activeTab.value = tab
    }
  }

  // Chat overlay toggle (Terminal-first) / Terminal panel toggle (Chat-first)
  const toggleChat = () => {
    if (uiModeStore.isChatFirst) {
      uiModeStore.toggleTerminalPanel()
      return
    }
    if (chatOverlayRef.value) {
      chatOverlayRef.value.toggle()
    } else {
      isChatVisible.value = !isChatVisible.value
    }
  }

  // Keyboard shortcuts
  const handleKeyDown = (event: KeyboardEvent) => {
    // Ctrl+Shift+M: Toggle UI mode
    if (event.ctrlKey && event.shiftKey && event.key === 'M') {
      event.preventDefault()
      uiModeStore.toggleMode()
      return
    }
    // Ctrl+Space: Toggle chat overlay / terminal panel
    if (event.ctrlKey && !event.shiftKey && event.code === 'Space') {
      event.preventDefault()
      toggleChat()
      return
    }
    // Ctrl+Shift+S: Toggle sidebar
    if (event.ctrlKey && event.shiftKey && event.key === 'S') {
      event.preventDefault()
      toggleSidebar()
    }
    // Ctrl+Shift+\: Split vertical
    if (event.ctrlKey && event.shiftKey && event.key === '|') {
      event.preventDefault()
      paneStore.addPane('vertical')
    }
    // Ctrl+Shift+-: Split horizontal
    if (event.ctrlKey && event.shiftKey && event.key === '_') {
      event.preventDefault()
      paneStore.addPane('horizontal')
    }
    // Ctrl+Shift+W: Close focused pane
    if (event.ctrlKey && event.shiftKey && event.key === 'W') {
      event.preventDefault()
      if (paneStore.focusedPaneId && paneStore.paneCount > 1) {
        paneStore.removePane(paneStore.focusedPaneId)
      }
    }
    // Ctrl+Tab: Focus next pane
    if (event.ctrlKey && event.key === 'Tab') {
      event.preventDefault()
      paneStore.focusNextPane()
    }
  }

  // Re-register panes on socket reconnection
  let wasConnected = false
  watch(
    () => terminalStore.connectionState.isConnected,
    (connected) => {
      if (connected && wasConnected) {
        // Reconnected after a disconnect — re-register panes
        paneStore.reconnectPanes()
      }
      wasConnected = connected
    }
  )

  onMounted(() => {
    uiModeStore.loadFromStorage()
    loadSidebarVisibility()
    paneStore.initialize()
    document.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })
</script>

<template>
  <!-- Onboarding Tutorial -->
  <OnboardingTutorial v-if="uiModeStore.showOnboarding" />

  <div id="app-container" :class="{ 'mode-transitioning': uiModeStore.isTransitioning }">
    <!-- Platform Header (Global) -->
    <PlatformHeader />

    <!-- App Header -->
    <AppHeader />

    <!-- App Body -->
    <div class="app-body">
      <!-- Terminal-first mode -->
      <template v-if="uiModeStore.isTerminalFirst">
        <PaneTreeSidebar v-if="isSidebarVisible" />

        <div class="main-content">
          <PaneLayout :node="paneStore.layout" />
        </div>

        <!-- Right Panel (optional) -->
        <div v-if="activeTab" class="right-panel">
          <div class="right-panel-header">
            <span>{{ activeTab === 'supervisor' ? 'Supervisor Control' : 'Dev Auth' }}</span>
            <button class="right-panel-close" @click="activeTab = null">x</button>
          </div>
          <div class="right-panel-content">
            <SupervisorControlPanel v-if="activeTab === 'supervisor'" />
            <DevJWTRegister v-if="activeTab === 'dev-auth'" />
          </div>
        </div>

        <!-- Chat Overlay (floating) -->
        <ChatOverlay v-if="isChatVisible" ref="chatOverlayRef" @close="isChatVisible = false" />
      </template>

      <!-- Chat-first mode -->
      <template v-else>
        <ChatFirstLayout />
      </template>
    </div>

    <!-- Command Palette -->
    <CommandPalette v-model:show="showCommandPalette" />

    <!-- Bottom toolbar (Status Bar) -->
    <div class="bottom-toolbar">
      <div class="toolbar-left">
        <button
          v-if="uiModeStore.isTerminalFirst"
          class="toolbar-item"
          :class="{ active: isSidebarVisible }"
          @click="toggleSidebar"
          title="Toggle Sidebar (Ctrl+Shift+S)"
        >
          <span class="icon">&#x1F4C1;</span>
          <span class="label">Explorer</span>
        </button>
        <div class="status-separator"></div>
        <div class="status-info">
          <span class="info-item">
            <span class="info-icon">&#x21AF;</span>
            <span class="info-text">{{ terminalStore.connectionStatus }}</span>
          </span>
          <span class="info-item" v-if="paneStore.paneCount > 0">
            <span class="info-icon">&#x25A3;</span>
            <span class="info-text">{{ paneStore.paneCount }} Panes</span>
          </span>
        </div>
      </div>

      <div class="toolbar-center">
        <button class="toolbar-item search-btn" @click="showCommandPalette = true">
          <span class="icon">&#x1F50D;</span>
          <span class="label">Command Palette (Ctrl+P)</span>
        </button>
      </div>

      <div class="toolbar-right">
        <button
          class="toolbar-item"
          :class="{
            active: uiModeStore.isTerminalFirst
              ? isChatVisible
              : !uiModeStore.isTerminalPanelCollapsed,
          }"
          @click="toggleChat"
        >
          <span class="icon">&#x2728;</span>
          <span class="label">{{ uiModeStore.isTerminalFirst ? 'Pilot Chat' : 'Terminal' }}</span>
        </button>
        <div class="status-separator"></div>
        <button
          class="toolbar-item"
          :class="{ active: activeTab === 'supervisor' }"
          @click="toggleRightPanel('supervisor')"
        >
          <span class="icon">&#x1F6E1;</span>
          <span class="label">Supervisor</span>
        </button>
        <button
          v-if="enableJWTDevRegister"
          class="toolbar-item dev-btn"
          :class="{ active: activeTab === 'dev-auth' }"
          @click="toggleRightPanel('dev-auth')"
        >
          <span class="icon">&#x1F511;</span>
          <span class="label">Dev Auth</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style>
  :root {
    --bg-primary: #0b0d11;
    --bg-secondary: #14171d;
    --bg-glass: rgba(20, 23, 29, 0.85);
    --border-color: rgba(255, 255, 255, 0.08);
    --accent-color: #4caf50;
    --accent-glow: rgba(76, 175, 80, 0.4);
    --text-main: #e6edf3;
    --text-muted: #7d8590;
    --panel-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    --font-family: 'Inter', system-ui, -apple-system, sans-serif;
  }

  html,
  body,
  #app {
    height: 100vh;
    margin: 0 !important;
    padding: 0 !important;
    font-family: var(--font-family);
    background-color: var(--bg-primary);
    color: var(--text-main);
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }
</style>

<style scoped>
  #app-container {
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: radial-gradient(circle at 50% 50%, #1a1d23 0%, #0b0d11 100%);
    animation: fade-in 1s ease-out;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
      transform: scale(1.02);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .app-body {
    flex: 1;
    display: flex;
    flex-direction: row;
    overflow: hidden;
    margin-bottom: 22px;
    padding: 6px;
    gap: 6px;
  }

  .main-content {
    flex: 1;
    display: flex;
    min-width: 0;
    min-height: 0;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
    box-shadow: var(--panel-shadow);
    overflow: hidden;
    backdrop-filter: blur(8px);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* Right panel */
  .right-panel {
    width: 340px;
    background-color: var(--bg-glass);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    backdrop-filter: blur(16px);
    box-shadow: var(--panel-shadow);
    animation: slide-in-right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @keyframes slide-in-right {
    from {
      transform: translateX(20px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .right-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background-color: rgba(0, 0, 0, 0.2);
    border-bottom: 1px solid var(--border-color);
    color: var(--text-muted);
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    text-transform: uppercase;
  }

  .right-panel-close {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 14px;
    padding: 4px;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .right-panel-close:hover {
    color: #f44336;
    background-color: rgba(244, 67, 54, 0.1);
  }

  .right-panel-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  /* Bottom toolbar (Status Bar) */
  .bottom-toolbar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 22px;
    background-color: #0b0d11;
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    z-index: 1000;
    font-size: 11px;
    color: var(--text-muted);
  }

  .toolbar-left,
  .toolbar-right {
    display: flex;
    align-items: center;
    height: 100%;
  }

  .toolbar-center {
    flex: 0 1 500px;
    display: flex;
    justify-content: center;
    height: 100%;
  }

  .toolbar-item {
    background: none;
    border: none;
    color: var(--text-muted);
    height: 100%;
    display: flex;
    align-items: center;
    padding: 0 10px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
    gap: 6px;
  }

  .toolbar-item:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-main);
  }

  .toolbar-item.active {
    color: var(--accent-color);
    background-color: rgba(76, 175, 80, 0.08);
  }

  .toolbar-item .icon {
    font-size: 11px;
  }

  .status-separator {
    width: 1px;
    height: 12px;
    background-color: var(--border-color);
    margin: 0 6px;
  }

  .status-info {
    display: flex;
    gap: 16px;
    margin-left: 10px;
  }

  .info-item {
    display: flex;
    align-items: center;
    gap: 5px;
    opacity: 0.8;
  }

  .info-icon {
    font-size: 10px;
    color: var(--accent-color);
  }

  .search-btn {
    width: 100%;
    max-width: 400px;
    justify-content: center;
    border-radius: 4px;
    height: 18px;
    margin-top: 2px;
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-color);
  }

  .search-btn:hover {
    border-color: rgba(255, 255, 255, 0.2);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .dev-btn {
    color: #ffcc00;
  }

  /* Responsive */
  @media (max-width: 1000px) {
    .right-panel {
      position: fixed;
      top: 0;
      right: 0;
      width: 100%;
      height: 100%;
      z-index: 1001;
      margin-left: 0;
      border-radius: 0;
    }
  }
</style>
