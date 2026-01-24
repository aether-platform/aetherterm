<template>
  <div class="terminal-log-monitor-panel">
    <div class="panel-header">
      <h3>Terminal Log Monitor</h3>
      <div class="refresh-controls">
        <v-btn
          size="small"
          icon="mdi-refresh"
          @click="refreshStatistics"
          :loading="isLoading"
        />
        <v-switch
          v-model="autoRefresh"
          label="Auto Refresh"
          density="compact"
          hide-details
        />
      </div>
    </div>

    <!-- Memory Status -->
    <MemoryStatusCard
      :redis-connected="redisConnected"
      :redis-stats="redisStats"
      :control-server-connected="controlServerConnected"
      :control-server-stats="controlServerStats"
    />

    <!-- System Overview -->
    <SystemOverviewCard
      :statistics="statistics"
    />

    <!-- Unprocessed Logs -->
    <UnprocessedLogsCard
      :unprocessed-logs="unprocessedLogs"
      :is-processing="isProcessingLogs"
      :is-refreshing="isRefreshingLogs"
      @process-all="processAllLogs"
      @refresh="refreshUnprocessedLogs"
      @process-log="processLog"
      @dismiss-log="dismissLog"
    />

    <!-- Log Search & Analysis -->
    <LogSearchCard
      :terminal-options="terminalOptions"
      :search-results="searchResults"
      :is-searching="isSearching"
      @search="performSearch"
      @export-results="exportSearchResults"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import MemoryStatusCard from './logMonitor/MemoryStatusCard.vue'
import SystemOverviewCard from './logMonitor/SystemOverviewCard.vue'
import UnprocessedLogsCard from './logMonitor/UnprocessedLogsCard.vue'
import LogSearchCard from './logMonitor/LogSearchCard.vue'

// State
const isLoading = ref(false)
const autoRefresh = ref(true)
const redisConnected = ref(false)
const controlServerConnected = ref(false)
const isProcessingLogs = ref(false)
const isRefreshingLogs = ref(false)
const isSearching = ref(false)

// Data
const redisStats = ref({
  used_memory: '',
  total_keys: 0
})

const controlServerStats = ref({
  total_logs: 0,
  memory_size: ''
})

const statistics = ref({
  active_terminals: 0,
  total_logs: 0,
  error_count: 0,
  processing_active: false
})

const unprocessedLogs = ref<Array<{
  timestamp: string | number
  terminal_id: string
  type: string
  content: string
  processing?: boolean
}>>([])

const searchResults = ref<Array<{
  timestamp: string | number
  terminal_id: string
  log_type: string
  content: string
}>>([])

// Computed
const terminalOptions = computed(() => [
  { title: 'All Terminals', value: '' },
  // Add more terminal options dynamically
])

// Methods
const refreshStatistics = async () => {
  isLoading.value = true
  try {
    // Implement statistics refresh logic
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock delay
  } finally {
    isLoading.value = false
  }
}

const processAllLogs = async () => {
  isProcessingLogs.value = true
  try {
    // Implement process all logs logic
    await new Promise(resolve => setTimeout(resolve, 2000)) // Mock delay
    unprocessedLogs.value = []
  } finally {
    isProcessingLogs.value = false
  }
}

const refreshUnprocessedLogs = async () => {
  isRefreshingLogs.value = true
  try {
    // Implement refresh unprocessed logs logic
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock delay
  } finally {
    isRefreshingLogs.value = false
  }
}

const processLog = async (log: any, index: number) => {
  log.processing = true
  try {
    // Implement individual log processing logic
    await new Promise(resolve => setTimeout(resolve, 500)) // Mock delay
    unprocessedLogs.value.splice(index, 1)
  } finally {
    log.processing = false
  }
}

const dismissLog = (index: number) => {
  unprocessedLogs.value.splice(index, 1)
}

const performSearch = async (params: {
  query: string
  terminal?: string
  limit: number
}) => {
  isSearching.value = true
  try {
    // Implement search logic
    await new Promise(resolve => setTimeout(resolve, 1000)) // Mock delay
    // searchResults.value = mockSearchResults
  } finally {
    isSearching.value = false
  }
}

const exportSearchResults = () => {
  // Implement export logic
  const data = JSON.stringify(searchResults.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'search-results.json'
  a.click()
  URL.revokeObjectURL(url)
}

// Lifecycle
let refreshInterval: number | null = null

onMounted(() => {
  refreshStatistics()
  
  if (autoRefresh.value) {
    refreshInterval = setInterval(refreshStatistics, 5000)
  }
})

onBeforeUnmount(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped lang="scss">
.terminal-log-monitor-panel {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
  
  h3 {
    margin: 0;
    color: var(--text-primary);
    font-weight: 600;
  }
}

.refresh-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}
</style>