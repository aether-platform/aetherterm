<template>
  <div class="control-section">
    <h4>Process Management (Supervisord)</h4>
    <div class="supervisord-controls">
      <div class="control-buttons">
        <button @click="$emit('refresh-processes')" :disabled="loading" class="control-btn refresh-btn">
          {{ loading ? 'Loading...' : 'Refresh Processes' }}
        </button>
        <button @click="$emit('start-all')" :disabled="loading" class="control-btn start-btn">
          Start All
        </button>
        <button @click="$emit('stop-all')" :disabled="loading" class="control-btn stop-btn">
          Stop All
        </button>
        <button @click="$emit('restart-all')" :disabled="loading" class="control-btn restart-btn">
          Restart All
        </button>
      </div>
      
      <div class="processes-list">
        <div v-if="processes.length === 0" class="no-processes">
          No processes found. Click "Refresh Processes" to load.
        </div>
        
        <div v-for="process in processes" :key="process.name" class="process-item">
          <div class="process-info">
            <div class="process-name">{{ process.name }}</div>
            <div class="process-status" :class="`status-${process.statename.toLowerCase()}`">
              {{ process.statename }}
            </div>
            <div class="process-description">{{ process.description }}</div>
          </div>
          
          <div class="process-controls">
            <button 
              @click="$emit('start-process', process.name)"
              :disabled="loading || process.statename === 'RUNNING'"
              class="control-btn start-btn small"
            >
              Start
            </button>
            <button 
              @click="$emit('stop-process', process.name)"
              :disabled="loading || process.statename === 'STOPPED'"
              class="control-btn stop-btn small"
            >
              Stop
            </button>
            <button 
              @click="$emit('restart-process', process.name)"
              :disabled="loading"
              class="control-btn restart-btn small"
            >
              Restart
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Process {
  name: string
  statename: string
  description: string
  pid?: number
  uptime?: string
}

interface Props {
  processes: Process[]
  loading: boolean
}

interface Emits {
  (e: 'refresh-processes'): void
  (e: 'start-all'): void
  (e: 'stop-all'): void
  (e: 'restart-all'): void
  (e: 'start-process', name: string): void
  (e: 'stop-process', name: string): void
  (e: 'restart-process', name: string): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
.supervisord-controls {
  space-y: 16px;
}

.control-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
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
  
  &.small {
    padding: 4px 8px;
    font-size: 12px;
  }
}

.refresh-btn {
  background: var(--primary-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--primary-color-dark);
  }
}

.start-btn {
  background: var(--success-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--success-color-dark);
  }
}

.stop-btn {
  background: var(--error-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--error-color-dark);
  }
}

.restart-btn {
  background: var(--warning-color);
  color: white;
  
  &:hover:not(:disabled) {
    background: var(--warning-color-dark);
  }
}

.processes-list {
  border: 1px solid var(--border-color);
  border-radius: 4px;
  overflow: hidden;
}

.no-processes {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.process-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  
  &:last-child {
    border-bottom: none;
  }
  
  &:hover {
    background: rgba(255, 255, 255, 0.05);
  }
}

.process-info {
  flex: 1;
}

.process-name {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.process-status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 4px;
  
  &.status-running {
    background: rgba(34, 197, 94, 0.2);
    color: var(--success-color);
  }
  
  &.status-stopped {
    background: rgba(239, 68, 68, 0.2);
    color: var(--error-color);
  }
  
  &.status-starting {
    background: rgba(251, 191, 36, 0.2);
    color: var(--warning-color);
  }
  
  &.status-stopping {
    background: rgba(251, 191, 36, 0.2);
    color: var(--warning-color);
  }
}

.process-description {
  font-size: 12px;
  color: var(--text-secondary);
}

.process-controls {
  display: flex;
  gap: 4px;
}
</style>