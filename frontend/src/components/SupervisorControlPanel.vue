<template>
  <div v-if="userInfo?.isSupervisor" class="supervisor-control-panel">
    <div class="panel-header">
      <h3>Supervisor Control Panel</h3>
      <div class="connection-status" :class="connectionStatusClass">
        {{ terminalStore.connectionStatus }}
      </div>
    </div>

    <SystemStatusSection
      :session-id="terminalStore.session.id"
      :supervisor-controlled="terminalStore.session.supervisorControlled"
      :risk-level="terminalStore.aiMonitoring.riskAssessment"
      :mcp-server-running="supervisordStatus.mcp_server_running"
    />

    <ProcessManagementSection
      :processes="supervisordProcesses"
      :loading="loading"
      @refresh-processes="refreshProcesses"
      @start-all="startAllProcesses"
      @stop-all="stopAllProcesses"
      @restart-all="restartAllProcesses"
      @start-process="startProcess"
      @stop-process="stopProcess"
      @restart-process="restartProcess"
    />

    <AIMonitoringSection
      :risk-assessment="terminalStore.aiMonitoring.riskAssessment"
      :commands-intercepted="terminalStore.aiMonitoring.commandsIntercepted"
      :approvals-required="terminalStore.aiMonitoring.approvalsRequired"
      :auto-approved="terminalStore.aiMonitoring.autoApproved"
      :rejected="terminalStore.aiMonitoring.rejected"
      :last-activity="terminalStore.aiMonitoring.lastActivity"
      :monitoring-enabled="terminalStore.aiMonitoring.enabled"
      @toggle-monitoring="toggleAIMonitoring"
      @clear-history="clearAIHistory"
      @refresh-stats="refreshAIStats"
    />

    <div class="control-section">
      <h4>Terminal Control</h4>
      <div class="terminal-controls">
        <button @click="pauseTerminal" class="control-btn pause-btn">
          ⏸️ Pause AI
        </button>
        <button @click="resumeTerminal" class="control-btn resume-btn">
          ▶️ Resume AI
        </button>
        <button @click="emergencyStop" class="control-btn emergency-btn">
          🚨 Emergency Stop
        </button>
      </div>
    </div>

    <CommandReviewSection
      v-if="terminalStore.pendingCommands.length > 0"
      :pending-commands="terminalStore.pendingCommands"
      @approve-command="approveCommand"
      @reject-command="rejectCommand"
      @modify-command="modifyCommand"
      @approve-all="approveAllCommands"
      @reject-all="rejectAllCommands"
    />

    <CommandHistorySection
      :recent-commands="commandHistory"
      :loading="loadingHistory"
      :has-more="hasMoreHistory"
      @refresh-history="refreshCommandHistory"
      @clear-history="clearCommandHistory"
      @export-history="exportCommandHistory"
      @load-more="loadMoreHistory"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import SystemStatusSection from './supervisor/SystemStatusSection.vue'
import ProcessManagementSection from './supervisor/ProcessManagementSection.vue'
import AIMonitoringSection from './supervisor/AIMonitoringSection.vue'
import CommandReviewSection from './supervisor/CommandReviewSection.vue'
import CommandHistorySection from './supervisor/CommandHistorySection.vue'
import { useTerminalStore } from '../stores/terminalStore'
import { useUserStore } from '../stores/userStore'

// Stores
const terminalStore = useTerminalStore()
const userStore = useUserStore()

// State
const loading = ref(false)
const loadingHistory = ref(false)
const hasMoreHistory = ref(true)
const supervisordProcesses = ref([])
const supervisordStatus = ref({
  mcp_server_running: false
})
const commandHistory = ref([])

// Computed
const userInfo = computed(() => userStore.userInfo)
const connectionStatusClass = computed(() => ({
  connected: terminalStore.connectionStatus === 'Connected',
  disconnected: terminalStore.connectionStatus === 'Disconnected',
  connecting: terminalStore.connectionStatus === 'Connecting'
}))

// Methods
const refreshProcesses = async () => {
  loading.value = true
  try {
    // Implement supervisord process refresh
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loading.value = false
  }
}

const startAllProcesses = async () => {
  loading.value = true
  try {
    // Implement start all processes
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loading.value = false
  }
}

const stopAllProcesses = async () => {
  loading.value = true
  try {
    // Implement stop all processes
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loading.value = false
  }
}

const restartAllProcesses = async () => {
  loading.value = true
  try {
    // Implement restart all processes
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loading.value = false
  }
}

const startProcess = async (name: string) => {
  loading.value = true
  try {
    // Implement start single process
    await new Promise(resolve => setTimeout(resolve, 500)) // Mock
  } finally {
    loading.value = false
  }
}

const stopProcess = async (name: string) => {
  loading.value = true
  try {
    // Implement stop single process
    await new Promise(resolve => setTimeout(resolve, 500)) // Mock
  } finally {
    loading.value = false
  }
}

const restartProcess = async (name: string) => {
  loading.value = true
  try {
    // Implement restart single process
    await new Promise(resolve => setTimeout(resolve, 500)) // Mock
  } finally {
    loading.value = false
  }
}

const toggleAIMonitoring = () => {
  terminalStore.toggleAIMonitoring()
}

const clearAIHistory = () => {
  terminalStore.clearAIHistory()
}

const refreshAIStats = () => {
  terminalStore.refreshAIStats()
}

const pauseTerminal = () => {
  terminalStore.pauseAI()
}

const resumeTerminal = () => {
  terminalStore.resumeAI()
}

const emergencyStop = () => {
  if (confirm('Are you sure you want to perform an emergency stop? This will halt all AI operations.')) {
    terminalStore.emergencyStop()
  }
}

const approveCommand = (id: string) => {
  terminalStore.approveCommand(id)
}

const rejectCommand = (id: string) => {
  terminalStore.rejectCommand(id)
}

const modifyCommand = (id: string) => {
  // Implement command modification logic
  console.log('Modify command:', id)
}

const approveAllCommands = () => {
  terminalStore.approveAllCommands()
}

const rejectAllCommands = () => {
  terminalStore.rejectAllCommands()
}

const refreshCommandHistory = async () => {
  loadingHistory.value = true
  try {
    // Implement command history refresh
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loadingHistory.value = false
  }
}

const clearCommandHistory = () => {
  if (confirm('Are you sure you want to clear the command history?')) {
    commandHistory.value = []
  }
}

const exportCommandHistory = () => {
  // Implement CSV export
  const csv = 'timestamp,command,status,risk\n' + 
    commandHistory.value.map(cmd => 
      `${cmd.timestamp},${cmd.command},${cmd.status},${cmd.riskLevel}`
    ).join('\n')
  
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `command-history-${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

const loadMoreHistory = async () => {
  loadingHistory.value = true
  try {
    // Implement load more history
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock
  } finally {
    loadingHistory.value = false
  }
}

// Lifecycle
onMounted(() => {
  refreshProcesses()
  refreshCommandHistory()
})
</script>

<style scoped>
.supervisor-control-panel {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--border-color);
}

.panel-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 24px;
  font-weight: 600;
}

.connection-status {
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.3s ease;
  
  &.connected {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success-color);
    border: 1px solid var(--success-color);
  }
  
  &.disconnected {
    background: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
    border: 1px solid var(--error-color);
  }
  
  &.connecting {
    background: rgba(251, 191, 36, 0.2);
    color: var(--warning-color);
    border: 1px solid var(--warning-color);
  }
}

.control-section {
  margin-bottom: 32px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  
  h4 {
    margin: 0 0 16px 0;
    color: var(--text-primary);
    font-size: 18px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.terminal-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.control-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  
  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
  
  &:active {
    transform: translateY(0);
  }
}

.pause-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.resume-btn {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.emergency-btn {
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
  color: white;
  font-weight: 600;
  
  &:hover {
    background: linear-gradient(135deg, #ee5a24 0%, #d63031 100%);
  }
}
</style>