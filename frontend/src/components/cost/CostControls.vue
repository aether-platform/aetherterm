<template>
  <div class="cost-controls">
    <div class="control-group">
      <label class="control-label">Period:</label>
      <select 
        :value="selectedPeriod" 
        @change="$emit('updatePeriod', Number(($event.target as HTMLSelectElement).value))"
        class="period-select"
      >
        <option value="7">7 days</option>
        <option value="30">30 days</option>
        <option value="90">90 days</option>
      </select>
    </div>
    
    <div v-if="modelData.length > 0" class="model-breakdown">
      <h4>By Model</h4>
      <div class="model-list">
        <div 
          v-for="model in modelData.slice(0, 3)" 
          :key="model.model"
          class="model-item"
        >
          <div class="model-name">{{ truncateModel(model.model) }}</div>
          <div class="model-cost">${{ model.cost.toFixed(4) }}</div>
          <div class="model-usage">{{ model.requests }} req</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ModelData {
  model: string
  cost: number
  requests: number
}

defineProps<{
  selectedPeriod: number
  modelData: ModelData[]
}>()

defineEmits<{
  updatePeriod: [period: number]
}>()

const truncateModel = (model: string) => {
  if (model.length > 15) {
    return model.substring(0, 12) + '...'
  }
  return model
}
</script>

<style scoped>
.cost-controls {
  margin: 8px;
  padding-top: 8px;
  border-top: 1px solid #333;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.control-label {
  font-size: 11px;
  color: #ccc;
}

.period-select {
  background: #2a2a2a;
  border: 1px solid #444;
  color: #fff;
  padding: 4px 6px;
  border-radius: 3px;
  font-size: 10px;
  cursor: pointer;
  outline: none;
}

.period-select:focus {
  border-color: #4caf50;
}

.model-breakdown h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #fff;
  font-weight: 500;
}

.model-list {
  max-height: 120px;
  overflow-y: auto;
}

.model-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 4px 6px;
  background: #2a2a2a;
  border-radius: 3px;
  margin-bottom: 3px;
  font-size: 9px;
  transition: all 0.2s ease;
}

.model-item:hover {
  background: #333;
  transform: translateY(-1px);
}

.model-name {
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-cost {
  color: #ffeb3b;
  font-weight: bold;
  text-align: right;
}

.model-usage {
  color: #aaa;
  font-size: 8px;
  text-align: right;
}

/* Scrollbar styling */
.model-list::-webkit-scrollbar {
  width: 4px;
}

.model-list::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.model-list::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.model-list::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>