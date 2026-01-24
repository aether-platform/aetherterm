<template>
  <div v-if="pendingCommands.length > 0" class="control-section">
    <h4>AI Command Review ({{ pendingCommands.length }})</h4>
    <div class="command-review-list">
      <div v-for="command in pendingCommands" :key="command.id" class="command-review-item">
        <div class="command-header">
          <div class="command-risk" :class="`risk-${command.riskLevel}`">
            {{ command.riskLevel.toUpperCase() }}
          </div>
          <div class="command-timestamp">
            {{ formatTimestamp(command.timestamp) }}
          </div>
        </div>
        
        <div class="command-content">
          <div class="command-text">{{ command.command }}</div>
          <div class="command-reason">{{ command.reason }}</div>
        </div>
        
        <div class="command-actions">
          <button 
            @click="$emit('approve-command', command.id)"
            class="control-btn approve-btn"
          >
            ✓ Approve
          </button>
          <button 
            @click="$emit('reject-command', command.id)"
            class="control-btn reject-btn"
          >
            ✗ Reject
          </button>
          <button 
            @click="$emit('modify-command', command.id)"
            class="control-btn modify-btn"
          >
            ✏️ Modify
          </button>
        </div>
      </div>
    </div>
    
    <div class="bulk-actions">
      <button @click="$emit('approve-all')" class="control-btn approve-btn">
        Approve All
      </button>
      <button @click="$emit('reject-all')" class="control-btn reject-btn">
        Reject All
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Command {
  id: string
  command: string
  reason: string
  riskLevel: string
  timestamp: number
}

interface Props {
  pendingCommands: Command[]
}

interface Emits {
  (e: 'approve-command', id: string): void
  (e: 'reject-command', id: string): void
  (e: 'modify-command', id: string): void
  (e: 'approve-all'): void
  (e: 'reject-all'): void
}

defineProps<Props>()
defineEmits<Emits>()

const formatTimestamp = (timestamp: number): string => {
  return new Date(timestamp).toLocaleTimeString()
}
</script>

<style scoped>
.command-review-list {
  margin-bottom: 16px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}

.command-review-item {
  padding: 16px;
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
  margin-bottom: 12px;
}

.command-risk {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  
  &.risk-low {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success-color);
  }
  
  &.risk-medium {
    background: rgba(251, 191, 36, 0.2);
    color: var(--warning-color);
  }
  
  &.risk-high {
    background: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
  }
}

.command-timestamp {
  font-size: 12px;
  color: var(--text-secondary);
}

.command-content {
  margin-bottom: 16px;
}

.command-text {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  background: rgba(0, 0, 0, 0.3);
  padding: 8px 12px;
  border-radius: 4px;
  border-left: 3px solid var(--primary-color);
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-primary);
}

.command-reason {
  font-size: 14px;
  color: var(--text-secondary);
  font-style: italic;
}

.command-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.bulk-actions {
  display: flex;
  gap: 8px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.control-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
}

.approve-btn {
  background: var(--success-color);
  color: white;
  
  &:hover {
    background: var(--success-color-dark);
  }
}

.reject-btn {
  background: var(--error-color);
  color: white;
  
  &:hover {
    background: var(--error-color-dark);
  }
}

.modify-btn {
  background: var(--warning-color);
  color: white;
  
  &:hover {
    background: var(--warning-color-dark);
  }
}
</style>