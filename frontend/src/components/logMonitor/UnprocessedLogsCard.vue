<template>
  <div class="monitor-section">
    <h4>Unprocessed Logs</h4>
    <div class="logs-container">
      <div class="logs-header">
        <v-btn
          size="small"
          color="primary"
          @click="processAllLogs"
          :loading="isProcessing"
          :disabled="!unprocessedLogs.length"
        >
          Process All ({{ unprocessedLogs.length }})
        </v-btn>
        <v-btn
          size="small"
          variant="outlined"
          @click="refreshUnprocessedLogs"
          :loading="isRefreshing"
        >
          Refresh
        </v-btn>
      </div>
      
      <div v-if="!unprocessedLogs.length" class="no-logs">
        <v-icon size="48" color="success">mdi-check-circle</v-icon>
        <p>No unprocessed logs</p>
      </div>
      
      <div v-else class="logs-list">
        <div
          v-for="(log, index) in displayedLogs"
          :key="index"
          class="log-item"
          :class="{ 'error': log.type === 'error', 'warning': log.type === 'warning' }"
        >
          <div class="log-header">
            <span class="log-timestamp">{{ formatTimestamp(log.timestamp) }}</span>
            <span class="log-terminal">{{ log.terminal_id }}</span>
            <v-chip
              size="small"
              :color="getLogTypeColor(log.type)"
              variant="outlined"
            >
              {{ log.type }}
            </v-chip>
          </div>
          <div class="log-content">{{ log.content }}</div>
          <div class="log-actions">
            <v-btn
              size="x-small"
              color="primary"
              @click="processLog(log, index)"
              :loading="log.processing"
            >
              Process
            </v-btn>
            <v-btn
              size="x-small"
              variant="outlined"
              @click="dismissLog(index)"
            >
              Dismiss
            </v-btn>
          </div>
        </div>
        
        <div v-if="unprocessedLogs.length > maxDisplayLogs" class="more-logs">
          <v-btn
            variant="text"
            @click="showMoreLogs"
          >
            Show {{ unprocessedLogs.length - maxDisplayLogs }} more...
          </v-btn>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface LogItem {
  timestamp: string | number
  terminal_id: string
  type: string
  content: string
  processing?: boolean
}

interface Props {
  unprocessedLogs: LogItem[]
  isProcessing?: boolean
  isRefreshing?: boolean
}

interface Emits {
  (e: 'process-all'): void
  (e: 'refresh'): void
  (e: 'process-log', log: LogItem, index: number): void
  (e: 'dismiss-log', index: number): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const maxDisplayLogs = ref(10)

const displayedLogs = computed(() => 
  props.unprocessedLogs.slice(0, maxDisplayLogs.value)
)

const formatTimestamp = (timestamp: string | number) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

const getLogTypeColor = (type: string) => {
  switch (type) {
    case 'error': return 'error'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'default'
  }
}

const processAllLogs = () => emit('process-all')
const refreshUnprocessedLogs = () => emit('refresh')
const processLog = (log: LogItem, index: number) => emit('process-log', log, index)
const dismissLog = (index: number) => emit('dismiss-log', index)
const showMoreLogs = () => {
  maxDisplayLogs.value += 10
}
</script>

<style scoped lang="scss">
.monitor-section {
  margin-bottom: 24px;
  
  h4 {
    margin-bottom: 16px;
    color: var(--text-primary);
    font-weight: 600;
  }
}

.logs-container {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-variant);
}

.logs-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  gap: 8px;
}

.no-logs {
  padding: 32px;
  text-align: center;
  color: var(--text-secondary);
  
  p {
    margin-top: 8px;
    margin-bottom: 0;
  }
}

.logs-list {
  max-height: 400px;
  overflow-y: auto;
}

.log-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  
  &:last-child {
    border-bottom: none;
  }
  
  &.error {
    border-left: 4px solid var(--error-color);
  }
  
  &.warning {
    border-left: 4px solid var(--warning-color);
  }
}

.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}

.log-timestamp {
  color: var(--text-secondary);
}

.log-terminal {
  font-family: monospace;
  background: var(--surface);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.log-content {
  font-family: monospace;
  font-size: 13px;
  line-height: 1.4;
  margin-bottom: 8px;
  color: var(--text-primary);
  word-break: break-word;
}

.log-actions {
  display: flex;
  gap: 8px;
}

.more-logs {
  padding: 16px;
  text-align: center;
  border-top: 1px solid var(--border-color);
}
</style>