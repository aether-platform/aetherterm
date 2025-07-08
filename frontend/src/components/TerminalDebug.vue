<template>
  <div class="terminal-debug pa-4">
    <h3>Terminal Debug Info</h3>
    
    <div class="debug-section">
      <h4>Workspace Info:</h4>
      <div v-if="workspace">
        <p>Workspace ID: {{ workspace.id }}</p>
        <p>Workspace Name: {{ workspace.name }}</p>
        <p>Tab Count: {{ workspace.tabs?.length || 0 }}</p>
        <p>Tab IDs: {{ workspace.tabs?.map(t => t.id).join(', ') || 'None' }}</p>
      </div>
      <div v-else>
        <p class="error">No workspace found!</p>
      </div>
    </div>

    <div class="debug-section">
      <h4>Pane Info:</h4>
      <div v-if="currentTab">
        <p>Current Tab ID: {{ currentTab.id }}</p>
        <p>Pane Count: {{ currentTab.panes?.length || 0 }}</p>
        <p>Active Pane: {{ currentTab.activePaneId || 'None' }}</p>
        <div v-if="currentTab.panes?.length > 0">
          <p>Panes:</p>
          <div v-for="pane in currentTab.panes" :key="pane.id" style="margin-left: 16px; font-size: 11px;">
            <p>ID: {{ pane.id }} | Type: {{ pane.type }} | Active: {{ pane.id === currentTab.activePaneId }}</p>
          </div>
        </div>
      </div>
      <div v-else>
        <p class="error">No current tab found!</p>
      </div>
    </div>

    <div class="debug-section">
      <h4>Connection Info:</h4>
      <p>WebSocket Connected: {{ isConnected ? 'Yes' : 'No' }}</p>
      <p>Connection State: {{ connectionState }}</p>
      <p>Socket ID: {{ socketId || 'None' }}</p>
    </div>

    <div class="debug-section">
      <h4>Tab Info:</h4>
      <p>Legacy Tab Count: {{ tabCount }}</p>
      <p>Active Tab ID: {{ activeTabId || 'None' }}</p>
      <p class="important">LogMonitor Active: {{ isLogMonitorActive ? 'YES (hiding terminals!)' : 'No' }}</p>
    </div>

    <div class="debug-section">
      <h4>Actions:</h4>
      <v-btn @click="createNewTab" color="primary" size="small">Create New Tab</v-btn>
      <v-btn @click="clearWorkspace" color="error" size="small" class="ml-2">Clear Workspace</v-btn>
      <v-btn @click="refreshConnection" color="info" size="small" class="ml-2">Refresh Connection</v-btn>
      <v-btn @click="createPaneForTab" color="success" size="small" class="ml-2">Add Pane</v-btn>
      <v-btn @click="ensureAllTabsHavePanes" color="warning" size="small" class="ml-2">Fix All Tabs</v-btn>
      <v-btn v-if="isLogMonitorActive" @click="disableLogMonitor" color="warning" size="small" class="ml-2">Disable LogMonitor</v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useTerminalTabStore } from '@/stores/terminalTabStore'
import { useAetherTerminalStore } from '@/stores/aetherTerminalStore'

const workspaceStore = useWorkspaceStore()
const tabStore = useTerminalTabStore()
const terminalStore = useAetherTerminalStore()

const workspace = computed(() => workspaceStore.currentWorkspace)
const currentTab = computed(() => {
  // First try to find a tab marked as active
  const activeTab = workspace.value?.tabs?.find(t => t.isActive)
  if (activeTab) return activeTab
  
  // If no active tab, try using activeTabId
  const activeTabId = workspace.value?.activeTabId
  if (activeTabId) {
    return workspace.value?.tabs?.find(t => t.id === activeTabId)
  }
  
  // If still no tab, return the first tab
  return workspace.value?.tabs?.[0]
})
const isConnected = computed(() => terminalStore.connectionState.isConnected)
const connectionState = computed(() => JSON.stringify(terminalStore.connectionState))
const socketId = computed(() => terminalStore.socket?.id)
const tabCount = computed(() => tabStore.tabs.length)
const activeTabId = computed(() => tabStore.activeTabId)
const isLogMonitorActive = computed(() => tabStore.isLogMonitorActive)

const createNewTab = async () => {
  console.log('Creating new tab...')
  const tab = await workspaceStore.createTab('terminal', { 
    name: 'Debug Terminal',
    terminalId: `term-${Date.now()}`
  })
  console.log('Created tab:', tab)
}

const createPaneForTab = async () => {
  if (!currentTab.value) {
    console.error('No current tab to add pane to')
    return
  }
  
  console.log('Creating pane for tab:', currentTab.value.id)
  const pane = await workspaceStore.createPane(currentTab.value.id, 'terminal', {
    terminalId: `pane-${Date.now()}`
  })
  console.log('Created pane:', pane)
}

const clearWorkspace = () => {
  if (confirm('Clear all workspace data?')) {
    localStorage.clear()
    location.reload()
  }
}

const refreshConnection = async () => {
  await terminalStore.connect()
}

const disableLogMonitor = () => {
  console.log('Disabling LogMonitor...')
  tabStore.setActiveTab(null)
  // Activate the first workspace tab if available
  if (currentTab.value) {
    workspaceStore.setActiveTab(currentTab.value.id)
  }
}

const ensureAllTabsHavePanes = async () => {
  console.log('Ensuring all tabs have panes...')
  if (!workspace.value) return
  
  let fixed = 0
  for (const tab of workspace.value.tabs) {
    if (tab.type === 'terminal' && (!tab.panes || tab.panes.length === 0)) {
      console.log(`Tab ${tab.id} has no panes, creating one...`)
      const pane = await workspaceStore.createPane(tab.id, 'terminal', {
        terminalId: `pane-${Date.now()}`
      })
      if (pane) {
        fixed++
      }
    }
  }
  
  console.log(`Fixed ${fixed} tabs`)
  if (fixed > 0) {
    alert(`Fixed ${fixed} tabs. Please refresh the page.`)
  } else {
    alert('All tabs already have panes.')
  }
}
</script>

<style scoped>
.terminal-debug {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: rgba(0, 0, 0, 0.9);
  color: white;
  border: 1px solid #666;
  border-radius: 8px;
  max-width: 400px;
  z-index: 9999;
  font-size: 12px;
}

.debug-section {
  margin-bottom: 16px;
  padding: 8px;
  border: 1px solid #333;
  border-radius: 4px;
}

.debug-section h4 {
  margin: 0 0 8px 0;
  color: #90caf9;
}

.debug-section p {
  margin: 4px 0;
}

.error {
  color: #f44336;
}

.important {
  color: #ffeb3b;
  font-weight: bold;
}
</style>