<template>
  <div class="sidebar-header">
    <div class="sidebar-title">
      <span class="sidebar-icon">💰</span>
      <span class="title-text">AI Costs</span>
      <span v-if="costData.available" class="cost-badge">
        ${{ costData.total_cost.toFixed(4) }}
      </span>
    </div>
    <div class="sidebar-controls">
      <button @click="$emit('toggle-view', 'dashboard')" class="control-btn" :class="{ active: viewMode === 'dashboard' }" title="Dashboard">
        📊
      </button>
      <button @click="$emit('toggle-view', 'table')" class="control-btn" :class="{ active: viewMode === 'table' }" title="Table">
        📋
      </button>
      <button @click="$emit('refresh')" :disabled="loading" class="control-btn" title="Refresh">
        🔄
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
interface CostData {
  total_cost: number
  available: boolean
}

defineProps<{
  loading?: boolean
  costData: CostData
  viewMode?: string
}>()

defineEmits<{
  refresh: []
  'toggle-view': [mode: string]
}>()
</script>

<style scoped>
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 8px;
  background: #252525;
  border-bottom: 1px solid #333;
  min-height: 44px;
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.sidebar-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.title-text {
  font-size: 14px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
}

.cost-badge {
  background: #ffeb3b;
  color: #000;
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: bold;
}

.sidebar-controls {
  display: flex;
  gap: 4px;
}

.control-btn {
  background: none;
  border: none;
  color: #ccc;
  padding: 4px;
  cursor: pointer;
  border-radius: 3px;
  font-size: 12px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.control-btn:hover {
  background: #333;
  color: white;
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-btn.active {
  background: #4caf50;
  color: #000;
}
</style>