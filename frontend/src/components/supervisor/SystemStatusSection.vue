<template>
  <div class="control-section priority">
    <h4>System Status</h4>
    <div class="status-grid">
      <div class="status-item">
        <span class="label">Session ID:</span>
        <span class="value">{{ sessionId }}</span>
      </div>
      <div class="status-item">
        <span class="label">Supervisor Control:</span>
        <span class="value" :class="{ active: supervisorControlled }">
          {{ supervisorControlled ? 'Enabled' : 'Disabled' }}
        </span>
      </div>
      <div class="status-item">
        <span class="label">AI Risk:</span>
        <span class="value" :class="`risk-${riskLevel}`">
          {{ riskLevel.toUpperCase() }}
        </span>
      </div>
      <div class="status-item">
        <span class="label">Supervisord MCP:</span>
        <span class="value" :class="{ active: mcpServerRunning }">
          {{ mcpServerRunning ? 'Running' : 'Stopped' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  sessionId: string
  supervisorControlled: boolean
  riskLevel: string
  mcpServerRunning: boolean
}

defineProps<Props>()
</script>

<style scoped>
.control-section.priority {
  border: 2px solid var(--warning-color);
  background: rgba(255, 165, 0, 0.1);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.status-item {
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
  
  &.active {
    color: var(--success-color);
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
</style>