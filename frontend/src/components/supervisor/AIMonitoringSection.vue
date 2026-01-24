<template>
  <div class="control-section">
    <h4>AI Monitoring Status</h4>
    <div class="ai-monitoring-grid">
      <div class="monitoring-item">
        <span class="label">Overall Risk:</span>
        <span class="value" :class="`risk-${riskAssessment}`">
          {{ riskAssessment.toUpperCase() }}
        </span>
      </div>
      <div class="monitoring-item">
        <span class="label">Commands Intercepted:</span>
        <span class="value">{{ commandsIntercepted }}</span>
      </div>
      <div class="monitoring-item">
        <span class="label">Approvals Required:</span>
        <span class="value warning">{{ approvalsRequired }}</span>
      </div>
      <div class="monitoring-item">
        <span class="label">Auto-Approved:</span>
        <span class="value success">{{ autoApproved }}</span>
      </div>
      <div class="monitoring-item">
        <span class="label">Rejected:</span>
        <span class="value error">{{ rejected }}</span>
      </div>
      <div class="monitoring-item">
        <span class="label">Last Activity:</span>
        <span class="value">{{ lastActivity || 'None' }}</span>
      </div>
    </div>
    
    <div class="ai-controls">
      <button @click="$emit('toggle-monitoring')" class="control-btn toggle-btn">
        {{ monitoringEnabled ? 'Disable' : 'Enable' }} AI Monitoring
      </button>
      <button @click="$emit('clear-history')" class="control-btn clear-btn">
        Clear History
      </button>
      <button @click="$emit('refresh-stats')" class="control-btn refresh-btn">
        Refresh Stats
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  riskAssessment: string
  commandsIntercepted: number
  approvalsRequired: number
  autoApproved: number
  rejected: number
  lastActivity?: string
  monitoringEnabled: boolean
}

interface Emits {
  (e: 'toggle-monitoring'): void
  (e: 'clear-history'): void
  (e: 'refresh-stats'): void
}

defineProps<Props>()
defineEmits<Emits>()
</script>

<style scoped>
.ai-monitoring-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.monitoring-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.label {
  font-weight: 500;
  color: var(--text-secondary);
}

.value {
  font-weight: 600;
  color: var(--text-primary);
  
  &.success {
    color: var(--success-color);
  }
  
  &.warning {
    color: var(--warning-color);
  }
  
  &.error {
    color: var(--error-color);
  }
  
  &.risk-low {
    color: var(--success-color);
  }
  
  &.risk-medium {
    color: var(--warning-color);
  }
  
  &.risk-high {
    color: var(--error-color);
  }
}

.ai-controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.control-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn {
  background: var(--primary-color);
  color: white;
  
  &:hover {
    background: var(--primary-color-dark);
  }
}

.clear-btn {
  background: var(--error-color);
  color: white;
  
  &:hover {
    background: var(--error-color-dark);
  }
}

.refresh-btn {
  background: var(--success-color);
  color: white;
  
  &:hover {
    background: var(--success-color-dark);
  }
}
</style>