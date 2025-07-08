<template>
  <div class="terminal-view" @contextmenu.prevent>
    <!-- Command Execution Overlay -->
    <div 
      v-if="isExecutingQueue && terminalTabStore.activeTab?.subType === 'inventory'"
      class="command-execution-overlay"
    >
      <div class="execution-status">
        <div class="spinner"></div>
        <h3>Initializing {{ terminalTabStore.activeTab?.serverContext?.name }}...</h3>
        <p>Executing pre-configured commands</p>
        <div class="progress-info">
          {{ commandQueue.filter(c => c.executed).length }} / {{ commandQueue.length }} commands completed
        </div>
      </div>
    </div>

    <!-- LogMonitor Tab Content (separate from regular tabs) -->
    <div 
      v-if="terminalTabStore.isLogMonitorActive"
      class="tab-content"
    >
      <LogMonitorTab />
    </div>

    <!-- Active Terminal Tab Content with Panes -->
    <div 
      v-for="tab in workspaceStore.currentWorkspace?.tabs || []" 
      :key="tab.id"
      v-show="tab.isActive && !terminalTabStore.isLogMonitorActive"
      class="tab-content"
    >
      <!-- Use PaneContainer only for terminal tabs -->
      <PaneContainer
        v-if="!tab.type || tab.type === 'terminal'"
        :tab-id="tab.id"
        :layout="tab.layout"
        @layout-changed="handleLayoutChange(tab.id, $event)"
        @pane-created="handlePaneCreated"
        @pane-closed="handlePaneClosed"
      />
      
      <!-- AI Agent Tab -->
      <AIAgentTab 
        v-else-if="tab.type === 'ai-agent'"
        :tab-id="tab.id"
      />
      
      <!-- Other special tabs can be added here -->
    </div>
    
    <!-- Fallback: Legacy Terminal Tab Content -->
    <div 
      v-for="tab in terminalTabStore.tabs" 
      :key="`legacy-${tab.id}`"
      v-show="tab.isActive && !terminalTabStore.isLogMonitorActive && !hasWorkspaceTabs"
      class="tab-content"
    >
      <!-- Direct tab component usage based on type -->
      <TerminalTabComponent 
        v-if="tab.type === 'terminal'" 
        :id="tab.id"
        :sub-type="tab.subType"
        @click="hideSelectionPopup"
      />
      
      <AIAgentTab 
        v-else-if="tab.type === 'ai-agent'" 
        :tab-id="tab.id"
      />
      
      <div v-else class="unknown-tab-content">
        <div class="unknown-message">
          <h4>Unknown tab type: {{ tab.type }}</h4>
          <p>This tab type is not supported.</p>
        </div>
      </div>
    </div>

    <!-- Default message when no tabs -->
    <div v-if="terminalTabStore.tabs.length === 0" class="no-tabs-message">
      <h3>No active sessions</h3>
      <p>Click the + button to create a new terminal or AI chat session.</p>
    </div>

    <!-- Selection Action Popup -->
    <SelectionActionPopup
      :show="showSelectionPopup"
      :position="popupPosition"
      :selected-text="selectedText"
      @copy="selectionPopupManagerRef?.onCopyAction"
      @send-to-ai="selectionPopupManagerRef?.onSendToAI"
      @hide="selectionPopupManagerRef?.hideSelectionPopup"
    />
    
    <!-- Manager Components (hidden, logic only) -->
    <CommandQueueManager
      ref="commandQueueManagerRef"
      :active-tab="activeTab"
      style="display: none;"
    />
    
    <SelectionPopupManager
      ref="selectionPopupManagerRef"
      style="display: none;"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTerminalTabStore } from '../../stores/terminalTabStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import { useTerminalPaneStore, type TerminalPane } from '../../stores/terminalPaneStore'
import SelectionActionPopup from '../SelectionActionPopup.vue'
import TerminalTabComponent from './AetherTerminalComponent.vue'
import AIAgentTab from './AIAgentTab.vue'
import LogMonitorTab from './LogMonitorTab.vue'
import PaneContainer from './PaneContainer.vue'
import CommandQueueManager from './CommandQueueManager.vue'
import SelectionPopupManager from './SelectionPopupManager.vue'

interface Props {
  isTerminalPaused?: boolean
  isSupervisorLocked?: boolean
}

interface Emits {
  (e: 'terminal-initialized'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

// Component refs
const commandQueueManagerRef = ref<InstanceType<typeof CommandQueueManager> | null>(null)
const selectionPopupManagerRef = ref<InstanceType<typeof SelectionPopupManager> | null>(null)

const terminalTabStore = useTerminalTabStore()
const workspaceStore = useWorkspaceStore()
const terminalPaneStore = useTerminalPaneStore()

// Get active tab from store
const activeTab = computed(() => terminalTabStore.activeTab)

// Check if we have workspace tabs (modern pane-based structure)
const hasWorkspaceTabs = computed(() => {
  return workspaceStore.currentWorkspace?.tabs && workspaceStore.currentWorkspace.tabs.length > 0
})

// Computed properties for template
const isExecutingQueue = computed(() => commandQueueManagerRef.value?.isExecutingQueue || false)
const commandQueue = computed(() => commandQueueManagerRef.value?.commandQueue || [])
const showSelectionPopup = computed(() => selectionPopupManagerRef.value?.showSelectionPopup || false)
const popupPosition = computed(() => selectionPopupManagerRef.value?.popupPosition || { x: 0, y: 0 })
const selectedText = computed(() => selectionPopupManagerRef.value?.selectedText || '')

onMounted(async () => {
  console.log('TerminalView mounted')
  // Terminal initialization is now handled by TerminalTab.vue components
})

// Event handlers for popup actions
const hideSelectionPopup = () => {
  selectionPopupManagerRef.value?.hideSelectionPopup()
}

// Pane event handlers
const handleLayoutChange = (tabId: string, newLayout: string) => {
  console.log('📋 TAB_CONTENT: Layout changed for tab:', tabId, 'to:', newLayout)
  terminalPaneStore.updatePaneLayout(tabId, newLayout as any)
  
  // Save workspace state
  workspaceStore.saveCurrentWorkspace()
}

const handlePaneCreated = (pane: TerminalPane) => {
  console.log('📋 TAB_CONTENT: Pane created:', pane.id)
  
  // Save workspace state
  workspaceStore.saveCurrentWorkspace()
}

const handlePaneClosed = (paneId: string) => {
  console.log('📋 TAB_CONTENT: Pane closed:', paneId)
  
  // Save workspace state
  workspaceStore.saveCurrentWorkspace()
}
</script>

<style scoped lang="scss">
.terminal-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
  height: 100%;
}

.tab-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.command-execution-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(30, 30, 30, 0.95);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(2px);
}

.execution-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  color: #ffffff;
  max-width: 400px;
  padding: 24px;
  background: #2d2d2d;
  border-radius: 8px;
  border: 1px solid #444;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #444;
  border-top: 3px solid #4caf50;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.execution-status h3 {
  margin: 0 0 8px 0;
  color: #ffffff;
  font-size: 18px;
}

.execution-status p {
  margin: 0 0 16px 0;
  color: #cccccc;
  font-size: 14px;
}

.progress-info {
  color: #4caf50;
  font-size: 14px;
  font-weight: 500;
}

.terminal-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background-color: #2d2d2d;
  border-bottom: 1px solid #444;
  font-size: 14px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  
  &.connecting {
    background-color: #ff9800;
    animation: pulse 1.5s infinite;
  }
  
  &.executing {
    background-color: #2196f3;
    animation: pulse 1s infinite;
  }
  
  &.ready {
    background-color: #4caf50;
  }
  
  &.waiting {
    background-color: #ffc107;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  color: #cccccc;
  font-weight: 500;
}

.progress-bar {
  width: 200px;
  height: 4px;
  background-color: #444;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #4caf50;
  transition: width 0.3s ease;
  border-radius: 2px;
}

.tab-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.terminal-tab-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  position: relative;
}

.ai-agent-tab-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.log-monitor-tab-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  background-color: #1e1e1e;
}

.no-tabs-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  color: #cccccc;

  h3 {
    margin-bottom: 8px;
    color: #aaaaaa;
  }

  p {
    color: #888888;
    font-size: 14px;
  }
}

.unknown-tab-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  color: #cccccc;
  
  .unknown-message {
    padding: 32px;
    
    h4 {
      margin-bottom: 8px;
      color: #ff9800;
    }

    p {
      color: #888888;
      font-size: 14px;
    }
  }
}
</style>