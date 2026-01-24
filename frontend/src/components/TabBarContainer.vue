<template>
  <div 
    class="terminal-tab-bar" 
    :class="{ 'sidebar-closed': !sidebarOpen, 'sidebar-open': sidebarOpen }" 
    @contextmenu.prevent
    :data-sidebar-state="sidebarOpen ? 'open' : 'closed'"
  >
    <!-- Existing Tabs -->
    <div class="tab-list">
      <!-- Workspace tabs (priority) -->
      <div
        v-for="tab in workspaceStore.currentWorkspace?.tabs || []"
        :key="`ws-${tab.id}`"
        class="terminal-tab"
        :class="{ 
          'active': tab.isActive,
          'terminal': !tab.type || tab.type === 'terminal',
          'ai-agent': tab.type === 'ai-agent',
          'log-monitor': tab.type === 'log-monitor'
        }"
        @click="switchToWorkspaceTab(tab.id)"
      >
        <div class="tab-content">
          <span class="tab-icon">
            {{ (!tab.type || tab.type === 'terminal')
                ? '💻' 
                : tab.type === 'ai-agent'
                  ? '🤖'
                  : '📈' }}
          </span>
          <span class="tab-title">{{ tab.title }}</span>
        </div>
        <button @click.stop="closeTab(tab.id)" class="tab-close">×</button>
      </div>
      
      <!-- Legacy tabs (fallback) -->
      <div
        v-if="!workspaceStore.currentWorkspace"
        v-for="tab in tabStore.displayTabs"
        :key="tab.id"
        class="terminal-tab"
        :class="{ 
          'active': tab.id === tabStore.activeTabId,
          'terminal': tab.type === 'terminal',
          'ai-agent': tab.type === 'ai-agent',
          'log-monitor': tab.type === 'log-monitor',
          'connecting': tab.status === 'connecting',
          'error': tab.status === 'error'
        }"
        @click="tabStore.switchToTab(tab.id)"
      >
        <div class="tab-content">
          <span class="tab-icon">
            {{ tab.type === 'terminal' 
                ? '💻' 
                : tab.type === 'ai-agent'
                  ? '🤖'
                  : '📈' }}
          </span>
          <span class="tab-title">{{ tab.title }}</span>
          <span class="tab-status-indicator" :class="tab.status"></span>
        </div>
        <button 
          v-if="tabStore.displayTabs.length > 1"
          @click.stop="tabStore.closeTab(tab.id)"
          class="tab-close-btn"
          title="Close Tab"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- Add Tab Button with Menu -->
    <TabCreationMenu @add-tab="addNewTab" />

    <!-- Fixed Log Monitor Tab -->
    <div
      class="terminal-tab fixed-tab log-monitor-tab"
      :class="{ 'active': isLogMonitorActive }"
      @click="switchToLogMonitor"
    >
      <div class="tab-content">
        <span class="tab-icon">📈</span>
        <span class="tab-title">Log Monitor</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useTerminalTabStore } from '../stores/terminalTabStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import TabCreationMenu from './terminal/tabs/TabCreationMenu.vue'

const tabStore = useTerminalTabStore()
const workspaceStore = useWorkspaceStore()

// Switch to workspace tab and update activation states
const switchToWorkspaceTab = (tabId: string) => {
  if (!workspaceStore.currentWorkspace) return
  
  // Update all tabs' isActive state
  workspaceStore.currentWorkspace.tabs.forEach(tab => {
    tab.isActive = tab.id === tabId
  })
  
  // No need to save - server handles persistence
  
  console.log('🔥 SWITCHED TO WORKSPACE TAB:', tabId)
}

// Close workspace tab
const closeTab = async (tabId: string) => {
  if (!workspaceStore.currentWorkspace) return
  
  const tabIndex = workspaceStore.currentWorkspace.tabs.findIndex(tab => tab.id === tabId)
  if (tabIndex === -1) return
  
  console.log('🔥 CLOSING WORKSPACE TAB:', tabId)
  
  try {
    // Import terminal store to send close request to server
    const { useAetherTerminalStore } = await import('../stores/aetherTerminalStore')
    const terminalStore = useAetherTerminalStore()
    
    const socket = terminalStore.getSocket()
    if (socket && socket.connected) {
      // Send tab close request to server
      socket.emit('tab_close', { tabId })
      
      // Listen for tab_closed confirmation
      const handleTabClosed = (data: any) => {
        if (data.success && data.tabId === tabId) {
          socket.off('tab_closed', handleTabClosed)
          socket.off('workspace_error', handleError)
          
          // Remove from local store after server confirmation
          const wasActive = workspaceStore.currentWorkspace!.tabs[tabIndex].isActive
          workspaceStore.currentWorkspace!.tabs.splice(tabIndex, 1)
          
          // If this was the active tab and there are remaining tabs, activate the last one
          if (wasActive && workspaceStore.currentWorkspace!.tabs.length > 0) {
            const lastTab = workspaceStore.currentWorkspace!.tabs[workspaceStore.currentWorkspace!.tabs.length - 1]
            lastTab.isActive = true
          }
          
          console.log('✅ WORKSPACE TAB CLOSED:', tabId)
        }
      }
      
      const handleError = (error: any) => {
        socket.off('tab_closed', handleTabClosed)
        socket.off('workspace_error', handleError)
        console.error('❌ Error closing tab:', error)
      }
      
      socket.on('tab_closed', handleTabClosed)
      socket.on('workspace_error', handleError)
      
      // Timeout after 5 seconds
      setTimeout(() => {
        socket.off('tab_closed', handleTabClosed)
        socket.off('workspace_error', handleError)
      }, 5000)
      
    } else {
      // Fallback: remove locally if no server connection
      console.warn('⚠️ No server connection, removing tab locally only')
      const wasActive = workspaceStore.currentWorkspace.tabs[tabIndex].isActive
      workspaceStore.currentWorkspace.tabs.splice(tabIndex, 1)
      
      if (wasActive && workspaceStore.currentWorkspace.tabs.length > 0) {
        const lastTab = workspaceStore.currentWorkspace.tabs[workspaceStore.currentWorkspace.tabs.length - 1]
        lastTab.isActive = true
      }
    }
    
  } catch (error) {
    console.error('❌ Error in closeTab:', error)
  }
}
const router = useRouter()

// リアクティブなサイドバー状態（DOM検出のみ）
const isSidebarOpen = ref(false)

// DOM監視でサイドバー状態を更新
const updateSidebarState = () => {
  if (typeof window !== 'undefined') {
    const supervisorPanel = document.getElementById('supervisor-container')
    // supervisor-containerが存在する = サイドバーが開いている
    // supervisor-containerが存在しない = サイドバーが閉じている
    const newState = supervisorPanel !== null
    if (newState !== isSidebarOpen.value) {
      isSidebarOpen.value = newState
    }
  }
}

// Reactiveなサイドバー状態 - DOM検出のみ使用
const sidebarOpen = computed(() => {
  // DOM検出の結果のみを使用
  return isSidebarOpen.value
})

// Check if log monitor tab is active
const isLogMonitorActive = computed(() => {
  return tabStore.isLogMonitorActive
})

// Switch to log monitor
const switchToLogMonitor = () => {
  tabStore.switchToLogMonitor()
}
const addNewTab = async (type: 'terminal' | 'ai-agent') => {
  console.log('🔥 ADD NEW TAB CALLED:', { type })
  console.log('🔥 Current workspace:', workspaceStore.currentWorkspace)
  
  // Wait for workspace initialization if needed
  if (!workspaceStore.currentWorkspace && !workspaceStore.isResuming) {
    console.log('🔥 WAITING FOR WORKSPACE INITIALIZATION...')
    await workspaceStore.initializeWorkspace()
    
    // Wait a bit more for workspace to be ready
    let retries = 0
    while (!workspaceStore.currentWorkspace && retries < 10) {
      await new Promise(resolve => setTimeout(resolve, 200))
      retries++
    }
  }
  
  // Use workspace store for modern tab management
  if (workspaceStore.currentWorkspace) {
    try {
      if (type === 'terminal') {
        // Create terminal tab with pane
        const newTab = await workspaceStore.createTabWithPane()
        console.log('🔥 NEW TERMINAL TAB WITH PANE CREATED:', newTab)
        console.log('🔥 Workspace tabs after creation:', workspaceStore.currentWorkspace.tabs)
      } else if (type === 'ai-agent') {
        // Create AI Agent tab without pane
        const newTab = await workspaceStore.createSpecialTab()
        console.log('🔥 NEW AI AGENT TAB CREATED:', newTab)
        console.log('🔥 Workspace tabs after creation:', workspaceStore.currentWorkspace.tabs)
      }
      
      // No need to save - server handles persistence
    } catch (error) {
      console.error('🔥 ERROR CREATING TAB:', error)
    }
  } else {
    console.log('🔥 NO CURRENT WORKSPACE - initializing workspace first')
    // Initialize workspace if not ready
    await workspaceStore.initializeWorkspace()
    
    // Try again after initialization
    if (workspaceStore.currentWorkspace) {
      await addNewTab(type)  // Recursive call to try again
    } else {
      console.error('🔥 Failed to initialize workspace for tab creation')
    }
  }
}
// MutationObserverでDOM変更を監視
let observer: MutationObserver | null = null

// Watch for workspace tab changes
watch(() => workspaceStore.currentWorkspace?.tabs, (newTabs, oldTabs) => {
  // Debug logs removed for performance
}, { deep: true, immediate: true })

onMounted(async () => {
  // Tab bar mounted
  
  // Don't initialize tabs here - let workspace handle it
  
  // DOMの準備を待つ
  await nextTick()
  
  // 初期状態を設定
  updateSidebarState()
  
  // DOM変更を監視してサイドバー状態を追跡
  observer = new MutationObserver(() => {
    updateSidebarState()
  })
  
  // bodyの子要素の変更を監視
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['id', 'class']
  })
  
})

onUnmounted(() => {
  if (observer) {
    observer.disconnect()
  }
})
</script>

<style scoped>
.terminal-tab-bar {
  display: flex;
  align-items: center;
  background-color: #1e1e1e;
  border-bottom: 1px solid #444;
  min-height: 40px;
  position: relative;
  overflow-x: auto;
  overflow-y: visible !important; /* Make sure overflow is visible for dropdown */
  z-index: 100; /* Ensure tab bar has proper z-index */
}

/* サイドバーが閉じているときのみ右マージンを追加 */
.terminal-tab-bar.sidebar-open {
  margin-right: 0 !important; /* サイドバーが開いているときは余白なし */
}

.terminal-tab-bar.sidebar-closed {
  margin-right: 40px !important; /* サイドバーが閉じているときのみ余白を追加 */
}

.tab-list {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.terminal-tab {
  display: flex;
  align-items: center;
  min-width: 120px;
  max-width: 200px;
  height: 40px;
  background-color: #2d2d2d;
  border-right: 1px solid #444;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  padding: 0 12px;
  gap: 8px;
}

.terminal-tab:hover {
  background-color: #3d3d3d;
}

.terminal-tab.active {
  background-color: #4caf50;
  color: white;
}

.terminal-tab.terminal {
  border-top: 2px solid #2196f3;
}

.terminal-tab.ai-agent {
  border-top: 2px solid #9c27b0;
}

.terminal-tab.log-monitor {
  border-top: 2px solid #ff9800;
}
.terminal-tab.pure-terminal {
  border-top: 2px solid #2196f3;
}

.terminal-tab.inventory-terminal {
  border-top: 2px solid #ff9800;
}

.terminal-tab.active.terminal {
  border-top: 2px solid #1976d2;
}

.terminal-tab.active.pure-terminal {
  border-top: 2px solid #1976d2;
}

.terminal-tab.active.inventory-terminal {
  border-top: 2px solid #f57c00;
}

.terminal-tab.active.ai-agent {
  border-top: 2px solid #7b1fa2;
}

.terminal-tab.active.log-monitor {
  border-top: 2px solid #f57c00;
}
/* Fixed tab styling */
.terminal-tab.fixed-tab {
  border-left: 2px solid #444;
  background-color: #1a1a1a;
  position: relative;
}

/* サイドバーが閉じているときのみFixed tabに右側余白を追加 */
.terminal-tab-bar.sidebar-closed .terminal-tab.fixed-tab {
  margin-right: 20px; /* 右側に追加余白 */
}

.terminal-tab.fixed-tab:hover {
  background-color: #2a2a2a;
}

.terminal-tab.fixed-tab.active {
  background-color: #f57c00;
  color: white;
}

.terminal-tab.fixed-tab::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background-color: #f57c00;
}

.tab-content {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.tab-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.tab-title {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.tab-status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-left: auto;
}

.tab-status-indicator.active {
  background-color: #4caf50;
}

.tab-status-indicator.connecting {
  background-color: #ff9800;
  animation: pulse 2s infinite;
}

.tab-status-indicator.disconnected {
  background-color: #f44336;
}

.tab-status-indicator.error {
  background-color: #f44336;
  animation: blink 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.tab-close {
  background: none;
  border: none;
  color: #ccc;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 2px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 8px;
}

.tab-close:hover {
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
}

.terminal-tab.active .tab-close {
  color: rgba(255, 255, 255, 0.8);
}

.terminal-tab.active .tab-close:hover {
  background-color: rgba(255, 255, 255, 0.2);
  color: white;
}

.tab-close-btn {
  background: none;
  border: none;
  color: #ccc;
  font-size: 12px;
  cursor: pointer;
  padding: 2px;
  border-radius: 2px;
  transition: all 0.2s ease;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tab-close-btn:hover {
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
}

.terminal-tab.active .tab-close-btn {
  color: rgba(255, 255, 255, 0.8);
}

.terminal-tab.active .tab-close-btn:hover {
  background-color: rgba(255, 255, 255, 0.2);
  color: white;
}

/* Responsive */
@media (max-width: 768px) {
  .terminal-tab {
    min-width: 100px;
    max-width: 150px;
    padding: 0 8px;
  }
  
  .tab-title {
    font-size: 12px;
  }
}

</style>