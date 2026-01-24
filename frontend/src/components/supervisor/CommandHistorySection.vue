<template>
  <div class="control-section">
    <h4>Recent Commands</h4>
    <div class="command-history-controls">
      <button @click="$emit('refresh-history')" class="control-btn refresh-btn">
        Refresh History
      </button>
      <button @click="$emit('clear-history')" class="control-btn clear-btn">
        Clear History
      </button>
      <button @click="$emit('export-history')" class="control-btn export-btn">
        Export CSV
      </button>
    </div>
    
    <div class="command-history-list">
      <div v-if="recentCommands.length === 0" class="no-commands">
        No recent commands found.
      </div>
      
      <div v-for="command in recentCommands" :key="command.id" class="command-history-item">
        <div class="command-header">
          <div class="command-status" :class="`status-${command.status}`">
            {{ formatStatus(command.status) }}
          </div>
          <div class="command-timestamp">
            {{ formatTimestamp(command.timestamp) }}
          </div>
        </div>
        
        <div class="command-content">
          <div class="command-text">{{ command.command }}</div>
          <div v-if="command.output" class="command-output">
            Output: {{ truncateOutput(command.output) }}
          </div>
        </div>
        
        <div class="command-metadata">
          <span class="metadata-item">
            Risk: <span :class="`risk-${command.riskLevel}`">{{ command.riskLevel }}</span>
          </span>
          <span class="metadata-item">
            Duration: {{ command.duration }}ms
          </span>
          <span v-if="command.userId" class="metadata-item">
            User: {{ command.userId }}
          </span>
        </div>
      </div>
    </div>
    
    <div v-if="hasMore" class="load-more">
      <button @click="$emit('load-more')" :disabled="loading" class="control-btn load-more-btn">
        {{ loading ? 'Loading...' : 'Load More' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Command {
  id: string
  command: string
  output?: string
  status: string
  riskLevel: string
  timestamp: number
  duration: number
  userId?: string
}

interface Props {
  recentCommands: Command[]
  loading: boolean
  hasMore: boolean
}

interface Emits {
  (e: 'refresh-history'): void
  (e: 'clear-history'): void
  (e: 'export-history'): void
  (e: 'load-more'): void
}

defineProps<Props>()
defineEmits<Emits>()

const formatTimestamp = (timestamp: number): string => {
  return new Date(timestamp).toLocaleString()
}

const formatStatus = (status: string): string => {
  switch (status) {
    case 'approved': return 'Approved'
    case 'rejected': return 'Rejected'
    case 'executed': return 'Executed'
    case 'failed': return 'Failed'
    case 'pending': return 'Pending'
    default: return status
  }
}

const truncateOutput = (output: string, maxLength: number = 100): string => {
  if (output.length <= maxLength) return output
  return output.substring(0, maxLength) + '...'
}
</script>

<style scoped>
.command-history-controls {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.command-history-list {
  border: 1px solid var(--border-color);
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}

.no-commands {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.command-history-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  
  &:last-child {
    border-bottom: none;
  }
  
  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
}

.command-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.command-status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  
  &.status-approved {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success-color);
  }
  
  &.status-rejected {
    background: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
  }
  
  &.status-executed {
    background: rgba(59, 130, 246, 0.2);
    color: var(--primary-color);
  }
  
  &.status-failed {
    background: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
  }
  
  &.status-pending {
    background: rgba(251, 191, 36, 0.2);
    color: var(--warning-color);
  }
}

.command-timestamp {
  font-size: 12px;
  color: var(--text-secondary);
}

.command-content {
  margin-bottom: 8px;
}

.command-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  background: rgba(0, 0, 0, 0.3);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.command-output {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  background: rgba(0, 0, 0, 0.2);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  border-left: 2px solid var(--border-color);
}

.command-metadata {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.metadata-item {
  font-size: 12px;
  color: var(--text-secondary);
  
  .risk-low {
    color: var(--success-color);
  }
  
  .risk-medium {
    color: var(--warning-color);
  }
  
  .risk-high {
    color: var(--error-color);
  }
}

.load-more {
  margin-top: 16px;
  text-align: center;
}

.control-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  
  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.refresh-btn {
  background: var(--primary-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--primary-color-dark);
  }
}

.clear-btn {
  background: var(--error-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--error-color-dark);
  }
}

.export-btn {
  background: var(--success-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--success-color-dark);
  }
}

.load-more-btn {
  background: var(--secondary-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--secondary-color-dark);
  }
}
</style>