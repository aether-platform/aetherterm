<template>
  <div class="main-content-view" @contextmenu.prevent>
    <!-- Main terminal area -->
    <div class="terminal-area">
      <TabContentArea 
        :is-terminal-paused="isTerminalPaused"
        :is-supervisor-locked="isSupervisorLocked"
        @terminal-initialized="$emit('terminal-initialized')"
      />
    </div>
    
    <!-- Sidebar panels -->
    <div class="sidebar-panels" v-if="showSidebar">
      <!-- Admin Panel -->
      <div class="sidebar-panel admin-panel" v-if="showAdminPanel">
        <div class="panel-header">
          <h3>Admin Panel</h3>
          <v-btn
            size="x-small"
            icon="mdi-close"
            @click="showAdminPanel = false"
          />
        </div>
        <div class="panel-content">
          <SupervisorControlPanel />
        </div>
      </div>
      
      <!-- Debug Panel -->
      <div class="sidebar-panel debug-panel" v-if="showDebugPanel">
        <div class="panel-header">
          <h3>Debug Panel</h3>
          <v-btn
            size="x-small"
            icon="mdi-close"
            @click="showDebugPanel = false"
          />
        </div>
        <div class="panel-content">
          <TerminalLogMonitorPanel />
        </div>
      </div>
    </div>
    
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import TabContentArea from './terminal/TabContentArea.vue'
import SupervisorControlPanel from './SupervisorControlPanel.vue'
import TerminalLogMonitorPanel from './TerminalLogMonitorPanel.vue'

interface Props {
  isTerminalPaused?: boolean
  isSupervisorLocked?: boolean
}

interface Emits {
  (e: 'terminal-initialized'): void
}

defineProps<Props>()
defineEmits<Emits>()

// Sidebar state
const showAdminPanel = ref(false)
const showDebugPanel = ref(false)

const showSidebar = computed(() => showAdminPanel.value || showDebugPanel.value)

// Panel toggle methods
const toggleAdminPanel = () => {
  showAdminPanel.value = !showAdminPanel.value
}

const toggleDebugPanel = () => {
  showDebugPanel.value = !showDebugPanel.value
}
</script>

<style scoped>
.main-content-view {
  display: flex;
  flex-direction: row;
  flex: 1;
  overflow: hidden;
  position: relative;
  height: 100%;
}

.terminal-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sidebar-panels {
  width: 400px;
  background: var(--v-theme-surface);
  border-left: 1px solid var(--v-theme-outline);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--v-theme-outline);
  
  &:last-child {
    border-bottom: none;
  }
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--v-theme-surface-variant);
  border-bottom: 1px solid var(--v-theme-outline);
  
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--v-theme-on-surface);
  }
}

.panel-content {
  flex: 1;
  overflow: auto;
  padding: 16px;
}


.tab-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.terminal-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.ai-chat-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.log-monitor-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  background-color: var(--color-bg-primary);
}

.no-tabs-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  color: #888;
}

.no-tabs-message h3 {
  margin-bottom: 8px;
  color: #aaa;
}

.no-tabs-message p {
  color: #666;
  font-size: 14px;
}
</style>