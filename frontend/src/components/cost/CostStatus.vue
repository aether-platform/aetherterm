<template>
  <div class="cost-status" :class="statusClass">
    <span class="status-icon">{{ statusIcon }}</span>
    <span class="status-text">{{ statusText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface CostData {
  total_cost: number
  available: boolean
  error?: string
  message?: string
}

const props = defineProps<{
  costData: CostData
}>()

const statusClass = computed(() => {
  if (props.costData.error) return 'error'
  if (props.costData.available && props.costData.total_cost > 0) return 'success'
  return 'info'
})

const statusIcon = computed(() => {
  if (props.costData.error) return '❌'
  if (props.costData.available && props.costData.total_cost > 0) return '💰'
  return 'ℹ️'
})

const statusText = computed(() => {
  if (props.costData.error) return `Error: ${props.costData.error}`
  if (props.costData.available && props.costData.total_cost > 0) return 'Cost data available'
  return props.costData.message || 'No cost data available'
})
</script>

<style scoped>
.cost-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2a2a2a;
  border-left: 3px solid #666;
  margin: 8px;
  font-size: 11px;
}

.cost-status.success {
  border-left-color: #4caf50;
  background: #1b5e20;
}

.cost-status.error {
  border-left-color: #f44336;
  background: #4a1b1b;
}

.cost-status.info {
  border-left-color: #2196f3;
  background: #1a2a4a;
}

.status-icon {
  flex-shrink: 0;
}

.status-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>