<template>
  <div :class="statusClasses">
    <span class="status-icon">{{ statusIcon }}</span>
    <span class="status-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  status: 'success' | 'error' | 'warning' | 'info' | 'loading'
  text: string
  size?: 'small' | 'medium' | 'large'
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium'
})

const statusClasses = computed(() => [
  'status-indicator',
  `status-${props.status}`,
  `size-${props.size}`
])

const statusIcon = computed(() => {
  switch (props.status) {
    case 'success': return '✅'
    case 'error': return '❌'
    case 'warning': return '⚠️'
    case 'info': return 'ℹ️'
    case 'loading': return '⏳'
    default: return 'ℹ️'
  }
})
</script>

<style scoped>
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2a2a2a;
  border-left: 3px solid #666;
  margin: 8px;
  border-radius: 0 3px 3px 0;
}

/* Status colors */
.status-success {
  border-left-color: #4caf50;
  background: #1b5e20;
}

.status-error {
  border-left-color: #f44336;
  background: #4a1b1b;
}

.status-warning {
  border-left-color: #ff9800;
  background: #4a2c00;
}

.status-info {
  border-left-color: #2196f3;
  background: #1a2a4a;
}

.status-loading {
  border-left-color: #9c27b0;
  background: #2a1a2a;
}

/* Sizes */
.size-small {
  padding: 4px 8px;
  font-size: 10px;
}

.size-medium {
  padding: 8px 12px;
  font-size: 11px;
}

.size-large {
  padding: 12px 16px;
  font-size: 12px;
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

/* Loading animation */
.status-loading .status-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>