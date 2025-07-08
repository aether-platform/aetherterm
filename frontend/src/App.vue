<script setup lang="ts">
  import 'normalize.css' // インストールしたライブラリの場合
  import { onMounted, onUnmounted, ref, watch, defineAsyncComponent } from 'vue'
  import TerminalComponent from './components/TerminalComponent.vue'
  import { useChatStore } from './stores/chatStore'
  import { useAetherTerminalServiceStore } from './stores/aetherTerminalServiceStore'
  import { useTheme } from './composables/useTheme'
  import { enableJWTDevRegister } from './config/environment'
  
  // Lazy load heavy components
  const SupervisorControlPanel = defineAsyncComponent(() => 
    import('./components/SupervisorControlPanel.vue')
  )
  const SimpleChatComponent = defineAsyncComponent(() => 
    import('./components/SimpleChatComponent.vue')
  )
  const DevJWTRegister = defineAsyncComponent(() => 
    import('./components/DevJWTRegister.vue')
  )
  const ServerInventoryPanel = defineAsyncComponent(() => 
    import('./components/ServerInventoryPanel.vue')
  )
  const ThemeSelector = defineAsyncComponent(() => 
    import('./components/ThemeSelector.vue')
  )
  const S3BrowserSidebar = defineAsyncComponent(() => 
    import('./components/S3BrowserSidebar.vue')
  )
  const AICostSidebar = defineAsyncComponent(() => 
    import('./components/AICostSidebar.vue')
  )

  const chatStore = useChatStore()
  const terminalStore = useAetherTerminalServiceStore()
  const { initialize: initializeTheme } = useTheme()
  const activeTab = ref('chat') // 'chat', 'inventory', 'supervisor', 'theme', 's3', 'cost', or 'debug'
  const isSupervisorPanelFloating = ref(false)
  const isSupervisorPanelVisible = ref(false)

  // Panel width management
  const panelWidth = ref(320) // デフォルト幅
  const isResizing = ref(false)
  const resizeStartX = ref(0)
  const resizeStartWidth = ref(0)

  // Dragging functionality for floating panel
  const isDragging = ref(false)
  const dragOffset = ref({ x: 0, y: 0 })
  const panelPosition = ref({ x: 20, y: 60 })

  const startDrag = (event: MouseEvent) => {
    if (!isSupervisorPanelFloating.value) return

    isDragging.value = true
    const rect = (event.target as HTMLElement)
      .closest('#supervisor-container')
      ?.getBoundingClientRect()
    if (rect) {
      dragOffset.value = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      }
    }

    document.addEventListener('mousemove', onDrag)
    document.addEventListener('mouseup', stopDrag)
    event.preventDefault()
  }

  const onDrag = (event: MouseEvent) => {
    if (!isDragging.value) return

    const newX = event.clientX - dragOffset.value.x
    const newY = event.clientY - dragOffset.value.y

    // Constrain to viewport
    const maxX = window.innerWidth - 300 // min panel width
    const maxY = window.innerHeight - 400 // min panel height

    panelPosition.value = {
      x: Math.max(0, Math.min(newX, maxX)),
      y: Math.max(0, Math.min(newY, maxY)),
    }
  }

  const stopDrag = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)
  }

  // Panel resize functionality with throttling
  let resizeThrottleId = 0

  const startResize = (event: MouseEvent) => {
    if (isSupervisorPanelFloating.value) return // リサイズはFixed時のみ

    isResizing.value = true
    resizeStartX.value = event.clientX
    resizeStartWidth.value = panelWidth.value

    document.addEventListener('mousemove', onResize)
    document.addEventListener('mouseup', stopResize)
    event.preventDefault()
  }

  const onResize = (event: MouseEvent) => {
    if (!isResizing.value) return

    // スロットル処理でパフォーマンス向上
    if (resizeThrottleId) {
      cancelAnimationFrame(resizeThrottleId)
    }

    resizeThrottleId = requestAnimationFrame(() => {
      const deltaX = resizeStartX.value - event.clientX // 左に動かすとプラス
      const newWidth = resizeStartWidth.value + deltaX

      // 最小幅と最大幅を制限
      const minWidth = 250
      const maxWidth = Math.min(600, window.innerWidth * 0.4)

      panelWidth.value = Math.max(minWidth, Math.min(newWidth, maxWidth))
      resizeThrottleId = 0
    })
  }

  const stopResize = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', onResize)
    document.removeEventListener('mouseup', stopResize)

    // 幅をlocalStorageに保存
    savePanelWidth()
  }

  // LocalStorage関連
  const PANEL_WIDTH_KEY = 'aetherterm-panel-width'

  const loadPanelWidth = () => {
    const saved = localStorage.getItem(PANEL_WIDTH_KEY)
    if (saved) {
      const width = parseInt(saved, 10)
      if (width >= 250 && width <= 600) {
        panelWidth.value = width
      }
    }
  }

  const savePanelWidth = () => {
    localStorage.setItem(PANEL_WIDTH_KEY, panelWidth.value.toString())
  }

  // Panel visibility management
  const PANEL_VISIBILITY_KEY = 'aetherterm-panel-visible'

  const loadPanelVisibility = () => {
    const saved = localStorage.getItem(PANEL_VISIBILITY_KEY)
    if (saved !== null) {
      isSupervisorPanelVisible.value = saved === 'true'
    }
  }

  const savePanelVisibility = () => {
    localStorage.setItem(PANEL_VISIBILITY_KEY, isSupervisorPanelVisible.value.toString())
  }

  const togglePanelVisibility = () => {
    isSupervisorPanelVisible.value = !isSupervisorPanelVisible.value
    savePanelVisibility()
  }

  const openS3BrowserFromTerminal = () => {
    activeTab.value = 's3'
    isSupervisorPanelVisible.value = true
    savePanelVisibility()
  }

  // 初期化時に保存された設定を読み込み
  onMounted(async () => {
    loadPanelWidth()
    loadPanelVisibility()

    // Initialize theme system
    await initializeTheme()

    // Listen for Ask AI events from Spine and auto-show side panel
    terminalStore.onAskAI((selectedText: string) => {
      console.log('App.vue: Ask AI triggered, showing side panel and switching to assistant tab')
      
      // Switch to assistant tab and show panel
      activeTab.value = 'chat'
      isSupervisorPanelVisible.value = true
    })
  })



  onUnmounted(() => {
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)
    document.removeEventListener('mousemove', onResize)
    document.removeEventListener('mouseup', stopResize)
    
    // Clean up Spine event listeners
    terminalStore.offAskAI()
  })

  watch(chatStore.activeMessages, (newMessages) => {
    if (newMessages.length > 0 && activeTab.value !== 'chat') {
      activeTab.value = 'chat'
    }
  })
</script>

<template>
  <div id="app-container">
    <!-- Main Content Area -->
    <div class="main-content">
      <!-- Terminal Container (Full Width) -->
      <div id="terminal-container">
        <TerminalComponent @open-s3-browser="openS3BrowserFromTerminal" />
      </div>
    </div>

    <!-- Supervisor Control Panel (Fixed or Floating) -->
    <div
      v-if="isSupervisorPanelVisible"
      id="supervisor-container"
      :class="{
        'supervisor-floating': isSupervisorPanelFloating,
        'supervisor-fixed': !isSupervisorPanelFloating,
        dragging: isDragging,
        resizing: isResizing,
      }"
      :style="
        isSupervisorPanelFloating
          ? {
              top: panelPosition.y + 'px',
              right: 'auto',
              left: panelPosition.x + 'px',
            }
          : {
              width: panelWidth + 'px',
            }
      "
    >
      <!-- Resize Handle (Fixed時のみ表示) -->
      <div v-if="!isSupervisorPanelFloating" class="resize-handle-container">
        <div
          class="resize-handle-button"
          @mousedown="startResize"
          :class="{ active: isResizing }"
        ></div>
      </div>
      <!-- Tab Navigation -->
      <div class="tab-navigation">
        <button 
          @click="togglePanelVisibility"
          class="panel-close-btn"
          title="Close Panel"
        >
          »
        </button>
        <button :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">Assistant</button>
        <button :class="{ active: activeTab === 'inventory' }" @click="activeTab = 'inventory'">
          🖥️ Inventory
        </button>
        <button :class="{ active: activeTab === 's3' }" @click="activeTab = 's3'">
          🗂️ S3
        </button>
        <button :class="{ active: activeTab === 'cost' }" @click="activeTab = 'cost'">
          💰 AI Costs
        </button>
        <button :class="{ active: activeTab === 'supervisor' }" @click="activeTab = 'supervisor'">
          👮 Admin
        </button>
        <button :class="{ active: activeTab === 'theme' }" @click="activeTab = 'theme'">
          🎨 Theme
        </button>
        <button
          v-if="enableJWTDevRegister"
          :class="{ active: activeTab === 'debug' }"
          @click="activeTab = 'debug'"
          class="debug-tab"
        >
          🔧 Debug
        </button>
      </div>

      <!-- Tab Content -->
      <div v-if="activeTab === 'chat'" class="tab-content chat-tab">
        <SimpleChatComponent />
      </div>
      <div v-if="activeTab === 'inventory'" class="tab-content inventory-tab">
        <ServerInventoryPanel />
      </div>
      <div v-if="activeTab === 's3'" class="tab-content s3-tab">
        <S3BrowserSidebar />
      </div>
      <div v-if="activeTab === 'cost'" class="tab-content cost-tab">
        <AICostSidebar />
      </div>
      <div v-if="activeTab === 'supervisor'" class="tab-content supervisor-tab">
        <SupervisorControlPanel />
      </div>
      <div v-if="activeTab === 'theme'" class="tab-content theme-tab">
        <ThemeSelector />
      </div>
      <div v-if="activeTab === 'debug'" class="tab-content debug-tab">
        <DevJWTRegister />
      </div>
    </div>

    <!-- Sidebar (when panel is hidden) -->
    <div
      v-show="!isSupervisorPanelVisible"
      class="sidebar"
    >
      <div class="sidebar-content">
        <!-- Panel Toggle Button -->
        <button 
          @click="togglePanelVisibility"
          class="sidebar-toggle-btn"
          :title="isSupervisorPanelVisible ? 'Hide Panel' : 'Show Panel'"
        >
          {{ isSupervisorPanelVisible ? '→' : '←' }}
        </button>
        
        <!-- Assistant Button -->
        <button 
          @click="activeTab = 'chat'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 'chat' && isSupervisorPanelVisible }"
          title="Open Assistant"
        >
          🤖
        </button>
        
        <!-- Inventory Button -->
        <button 
          @click="activeTab = 'inventory'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 'inventory' && isSupervisorPanelVisible }"
          title="Open Server Inventory"
        >
          🖥️
        </button>
        
        <!-- S3 Browser Button -->
        <button 
          @click="activeTab = 's3'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 's3' && isSupervisorPanelVisible }"
          title="Open S3 Browser"
        >
          🗂️
        </button>
        
        <!-- AI Costs Button -->
        <button 
          @click="activeTab = 'cost'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 'cost' && isSupervisorPanelVisible }"
          title="AI Costs"
        >
          💰
        </button>
        
        <!-- Admin Button -->
        <button 
          @click="activeTab = 'supervisor'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 'supervisor' && isSupervisorPanelVisible }"
          title="Admin Panel"
        >
          👮
        </button>
        
        <!-- Theme Button -->
        <button 
          @click="activeTab = 'theme'; isSupervisorPanelVisible = true"
          class="sidebar-tab-btn"
          :class="{ active: activeTab === 'theme' && isSupervisorPanelVisible }"
          title="Theme Settings"
        >
          🎨
        </button>
      </div>
    </div>

    <!-- Debug Info -->
    <div v-if="false" class="debug-info" style="position: fixed; top: 100px; left: 10px; background: rgba(0,0,0,0.8); color: white; padding: 10px; z-index: 9999; font-size: 12px;">
      <div>Panel Visible: {{ isSupervisorPanelVisible }}</div>
      <div>Active Tab: {{ activeTab }}</div>
      <div>Panel Floating: {{ isSupervisorPanelFloating }}</div>
      <div>Sidebar Should Show: {{ !isSupervisorPanelVisible }}</div>
    </div>


  </div>
</template>

<style scoped>
  /* Add "scoped" to limit the scope of these styles */

  .tab-navigation {
    display: flex;
    background-color: #1e1e1e;
    border-bottom: 1px solid #444;
  }

  .tab-navigation button {
    background: none;
    border: none;
    color: #ccc;
    padding: 10px 15px;
    cursor: pointer;
    font-size: 14px;
  }

  .tab-navigation button.active {
    background-color: #4caf50;
    color: white;
  }

  .tab-navigation button.debug-tab {
    border-left: 1px solid #444;
    border-right: 1px solid #444;
    background-color: #2a2a2a;
    color: #ff9800;
    font-size: 12px;
  }

  .tab-navigation button.debug-tab:hover {
    background-color: #333;
  }

  .tab-navigation button.debug-tab.active {
    background-color: #ff9800;
    color: white;
  }

  .tab-content {
    padding: 15px;
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
  }

  /* アシスタント専用のレイアウト調整 */
  .tab-content.chat-tab {
    padding: 0; /* アシスタントは独自のパディングを持つ */
  }

  .tab-content.supervisor-tab {
    /* Supervisorタブは通常のパディング */
  }

  .tab-content.debug-tab {
    /* Debugタブは通常のパディング */
    padding: 0; /* DevJWTRegisterコンポーネントが独自のパディングを持つ */
  }

  .tab-content.s3-tab {
    /* S3タブはパディングなし */
    padding: 0; /* S3Browserコンポーネントが独自のパディングを持つ */
  }

  .tab-content.cost-tab {
    /* AI Costsタブはパディングなし */
    padding: 0; /* AICostSidebarコンポーネントが独自のパディングを持つ */
  }




  .tab-navigation button.panel-close-btn {
    background-color: #1e1e1e;
    color: #999;
    border-right: 1px solid #444;
    padding: 10px 12px;
    font-size: 18px;
    font-weight: bold;
    min-width: auto;
    line-height: 1;
  }

  .tab-navigation button.panel-close-btn:hover {
    background-color: #333;
    color: #4caf50;
  }

  .tab-content.inventory-tab {
    /* Inventoryタブはパディングなし */
    padding: 0; /* InventorySearchPanelコンポーネントが独自のパディングを持つ */
  }

  html,
  body,
  #app {
    height: 100vh;
    margin: 0 !important;
    padding: 0 !important;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  #app-container {
    height: 100vh;
    position: relative;
    display: flex;
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: row; /* Make main-content a flexbox */
    height: 100%; /* Ensure full vertical height */
    min-width: 0;
  }

  #terminal-container {
    flex-grow: 1; /* Make terminal-container grow to fill space */
    overflow: hidden;
    background-color: #1e1e1e;
    will-change: transform; /* GPU最適化ヒント */
    /* transition削除 - performanceのため */
  }

  #chat-container {
    background-color: #f9f9f9;
    border-top: 1px solid #444;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }

  .chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 15px;
    background-color: #e0e0e0;
    border-bottom: 1px solid #ccc;
    color: #333;
  }

  .chat-header h3 {
    margin: 0;
    font-size: 14px;
    color: #2196f3;
  }

  /* Supervisor Panel Styles */
  #supervisor-container {
    background-color: #2d2d2d;
    display: flex;
    flex-direction: column;
    transition: width 0.1s ease-out;
    z-index: 1000;
  }

  .supervisor-fixed {
    height: 100%;
    border-left: 1px solid #444;
    flex-shrink: 0;
    position: relative;
    min-width: 250px;
    max-width: 600px;
  }

  .supervisor-floating {
    position: fixed;
    top: 60px;
    right: 20px;
    width: 400px;
    height: 70vh;
    border: 1px solid #444;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(10px);
    resize: both;
    overflow: auto;
    min-width: 300px;
    min-height: 400px;
    max-width: 90vw;
    max-height: 90vh;
  }

  .supervisor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 15px;
    background-color: #1e1e1e;
    border-bottom: 1px solid #444;
    color: white;
    cursor: move; /* For floating panel dragging */
  }

  .supervisor-floating .supervisor-header {
    border-radius: 8px 8px 0 0;
  }

  .supervisor-header h3 {
    margin: 0;
    font-size: 16px;
    color: #4caf50;
  }

  .supervisor-controls {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .float-toggle-btn {
    background: none;
    border: none;
    color: #ccc;
    font-size: 16px;
    cursor: pointer;
    padding: 4px;
    border-radius: 3px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .float-toggle-btn:hover {
    background-color: #444;
    color: white;
  }

  .close-btn {
    background: none;
    border: none;
    color: #ccc;
    font-size: 20px;
    cursor: pointer;
    padding: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 3px;
  }

  .close-btn:hover {
    background-color: #444;
    color: white;
  }

  /* Control Buttons */
  .control-buttons {
    position: fixed;
    top: 20px;
    right: 20px;
    display: flex;
    gap: 10px;
    z-index: 999;
  }

  .control-btn {
    background-color: #4caf50;
    color: white;
    border: none;
    padding: 8px 12px;
    border-radius: 5px;
    cursor: pointer;
    font-size: 12px;
    font-weight: bold;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    transition: all 0.2s ease;
  }

  .control-btn:hover {
    background-color: #45a049;
    transform: translateY(-1px);
  }

  .chat-btn {
    background-color: #2196f3;
  }

  .chat-btn:hover {
    background-color: #1976d2;
  }

  /* Responsive adjustments */
  @media (max-width: 1200px) {
    .supervisor-fixed {
      width: 300px;
    }

    .supervisor-floating {
      width: 350px;
      right: 10px;
    }
  }

  @media (max-width: 900px) {
    .main-content {
      flex-direction: column;
    }

    #chat-container {
      height: 200px !important;
      border-top: 1px solid #444;
      border-left: none;
    }

    .supervisor-fixed {
      position: fixed;
      top: 0;
      right: 0;
      width: 100%;
      height: 100%;
      z-index: 1001;
    }

    .supervisor-floating {
      width: 90vw;
      height: 80vh;
      top: 10vh;
      right: 5vw;
    }

    .control-buttons {
      top: 10px;
      right: 10px;
    }

    .control-btn {
      padding: 6px 10px;
      font-size: 11px;
    }
  }

  /* Draggable functionality for floating panel */
  .supervisor-floating .supervisor-header {
    user-select: none;
  }

  /* Scrollbar styling for admin panel */
  .supervisor-floating {
    scrollbar-width: thin;
    scrollbar-color: #666 #2d2d2d;
  }

  .supervisor-floating::-webkit-scrollbar {
    width: 8px;
  }

  .supervisor-floating::-webkit-scrollbar-track {
    background: #2d2d2d;
  }

  .supervisor-floating::-webkit-scrollbar-thumb {
    background: #666;
    border-radius: 4px;
  }

  .supervisor-floating::-webkit-scrollbar-thumb:hover {
    background: #888;
  }

  /* Draggable functionality enhancements */
  .supervisor-floating .supervisor-header {
    user-select: none;
  }

  .supervisor-container.dragging {
    opacity: 0.9;
    transform: scale(1.02);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
    z-index: 1001;
  }

  .supervisor-floating.dragging {
    transition: none;
  }

  /* Resize handle styles */
  .resize-handle-container {
    position: absolute;
    left: -8px;
    top: 0;
    bottom: 0;
    width: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    pointer-events: none; /* コンテナ自体はクリックできない */
  }

  .resize-handle-button {
    width: 10px;
    height: 80px;
    background-color: #666;
    border-radius: 5px;
    cursor: col-resize;
    transition: all 0.2s ease;
    position: relative;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    pointer-events: auto; /* ボタンのみクリック可能 */
  }

  .resize-handle-button::before {
    content: '';
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 3px;
    height: 30px;
    background: repeating-linear-gradient(
      to bottom,
      #999 0px,
      #999 3px,
      transparent 3px,
      transparent 6px
    );
    border-radius: 1.5px;
  }

  .resize-handle-button:hover {
    background-color: #777;
    transform: scaleY(1.1);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.4);
  }

  .resize-handle-button:hover::before {
    background: repeating-linear-gradient(
      to bottom,
      #bbb 0px,
      #bbb 3px,
      transparent 3px,
      transparent 6px
    );
  }

  .resize-handle-button.active {
    background-color: #4caf50;
    transform: scaleY(1.2);
    box-shadow: 0 0 8px rgba(76, 175, 80, 0.5);
  }

  .resize-handle-button.active::before {
    background: repeating-linear-gradient(
      to bottom,
      #fff 0px,
      #fff 3px,
      transparent 3px,
      transparent 6px
    );
  }

  /* Add visual feedback during resize */
  .supervisor-container.resizing {
    user-select: none;
    transition: none; /* リサイズ中はトランジションを無効化 */
  }

  .supervisor-container.resizing * {
    user-select: none;
    pointer-events: none; /* リサイズ中は子要素のイベントを無効化 */
  }

  /* Admin content and chat content styles */
  .supervisor-content {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }

  .chat-content {
    flex: 1;
    overflow: hidden;
  }

  .supervisor-floating .supervisor-header {
    border-radius: 8px 8px 0 0;
  }

  /* Panel Toggle Button */
  .panel-toggle-container {
    position: fixed;
    top: 20px;
    transform: none;
    z-index: 1001;
    transition: right 0.3s ease;
  }

  .panel-toggle-btn {
    background-color: #4caf50;
    color: white;
    border: none;
    width: 60px;
    height: 30px;
    border-radius: 0 0 0 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: bold;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    transition: all 0.3s ease;
    transform: translateY(0);
    writing-mode: initial;
    text-orientation: initial;
  }

  .panel-toggle-btn:hover {
    background-color: #45a049;
    transform: translateY(3px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }

  .panel-toggle-btn.panel-hidden {
    background-color: #2196f3;
    border-radius: 0 0 6px 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .panel-toggle-btn.panel-hidden:hover {
    background-color: #1976d2;
    transform: translateY(3px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }

  /* Sidebar Styles */
  .sidebar {
    position: fixed;
    top: 0;
    right: 0;
    height: 100vh;
    width: 60px;
    background-color: #1e1e1e;
    border-left: 1px solid #444;
    z-index: 1001;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding-top: 20px;
    box-shadow: -2px 0 8px rgba(0, 0, 0, 0.3);
  }

  .sidebar-content {
    display: flex;
    flex-direction: column;
    gap: 15px;
  }

  .sidebar-toggle-btn {
    width: 40px;
    height: 30px;
    background-color: #4caf50;
    border: none;
    border-radius: 6px;
    color: white;
    font-size: 14px;
    font-weight: bold;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    margin-bottom: 10px;
  }

  .sidebar-toggle-btn:hover {
    background-color: #45a049;
    transform: scale(1.05);
  }

  .sidebar-tab-btn {
    width: 40px;
    height: 40px;
    background: none;
    border: 2px solid #444;
    border-radius: 8px;
    color: #ccc;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }

  .sidebar-tab-btn:hover {
    background-color: #333;
    border-color: #4caf50;
    color: #4caf50;
    transform: scale(1.05);
  }

  .sidebar-tab-btn.active {
    background-color: #4caf50;
    border-color: #4caf50;
    color: white;
  }

  .sidebar-tab-btn::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(76, 175, 80, 0.3), transparent);
    transition: left 0.5s ease;
  }

  .sidebar-tab-btn:hover::before {
    left: 100%;
  }

  /* モバイル画面での調整 */
  @media (max-width: 900px) {
    .panel-toggle-container {
      top: 10px;
      right: 10px !important;
    }

    .panel-toggle-btn {
      width: 50px;
      height: 35px;
      border-radius: 0 0 6px 6px;
      font-size: 16px;
    }

    .panel-toggle-btn.panel-hidden {
      border-radius: 0 0 6px 6px;
    }

    .sidebar {
      width: 50px;
      padding-top: 60px; /* トグルボタンの下に配置 */
    }

    .sidebar-tab-btn {
      width: 35px;
      height: 35px;
      font-size: 14px;
    }
  }
</style>
