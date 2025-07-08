<template>
  <div v-if="costData.available" class="cost-overview">
    <div class="total-cost">
      <div class="cost-amount">${{ costData.total_cost.toFixed(4) }}</div>
      <div class="cost-period">{{ selectedPeriod }} days</div>
    </div>

    <!-- Usage Statistics -->
    <div v-if="costData.requests || costData.input_tokens || costData.output_tokens" class="usage-stats">
      <div class="stat-grid">
        <div class="stat-item" v-if="costData.requests">
          <div class="stat-label">Requests</div>
          <div class="stat-value">{{ formatNumber(costData.requests) }}</div>
        </div>
        <div class="stat-item" v-if="costData.input_tokens">
          <div class="stat-label">Input Tokens</div>
          <div class="stat-value">{{ formatNumber(costData.input_tokens) }}</div>
        </div>
        <div class="stat-item" v-if="costData.output_tokens">
          <div class="stat-label">Output Tokens</div>
          <div class="stat-value">{{ formatNumber(costData.output_tokens) }}</div>
        </div>
      </div>

      <!-- Token Usage Visualization -->
      <div v-if="costData.input_tokens && costData.output_tokens" class="token-usage">
        <div class="usage-header">Token Distribution</div>
        <div class="token-bars">
          <div class="token-row">
            <span class="token-label">Input</span>
            <div class="bar-container">
              <div class="bar-fill input-bar" :style="{ width: inputTokenPercentage + '%' }"></div>
            </div>
          </div>
          <div class="token-row">
            <span class="token-label">Output</span>
            <div class="bar-container">
              <div class="bar-fill output-bar" :style="{ width: outputTokenPercentage + '%' }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Cost Metrics -->
    <div v-if="costData.average_cost_per_request || costData.total_cost > 0" class="cost-metrics">
      <div class="metric-row" v-if="costData.average_cost_per_request">
        <span class="metric-label">Avg/req:</span>
        <span class="metric-value">${{ costData.average_cost_per_request.toFixed(4) }}</span>
      </div>
      <div class="metric-row" v-if="costData.cost_per_1k_tokens">
        <span class="metric-label">$/1K tok:</span>
        <span class="metric-value">${{ costData.cost_per_1k_tokens.toFixed(4) }}</span>
      </div>
      <div class="metric-row" v-if="costData.total_cost > 0">
        <span class="metric-label">Period:</span>
        <span class="metric-value">{{ selectedPeriod }}d</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface CostData {
  total_cost: number
  available: boolean
  requests?: number
  input_tokens?: number
  output_tokens?: number
  average_cost_per_request?: number
  cost_per_1k_tokens?: number
}

const props = defineProps<{
  costData: CostData
  selectedPeriod: number
}>()

const formatNumber = (num: number) => {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

const inputTokenPercentage = computed(() => {
  if (!props.costData.input_tokens || !props.costData.output_tokens) return 0
  const total = props.costData.input_tokens + props.costData.output_tokens
  return (props.costData.input_tokens / total) * 100
})

const outputTokenPercentage = computed(() => {
  if (!props.costData.input_tokens || !props.costData.output_tokens) return 0
  const total = props.costData.input_tokens + props.costData.output_tokens
  return (props.costData.output_tokens / total) * 100
})
</script>

<style scoped>
.cost-overview {
  margin: 8px;
}

.total-cost {
  text-align: center;
  padding: 12px;
  background: #2a2a2a;
  border-radius: 4px;
  margin-bottom: 12px;
}

.cost-amount {
  font-size: 18px;
  font-weight: bold;
  color: #ffeb3b;
}

.cost-period {
  font-size: 10px;
  color: #aaa;
  margin-top: 2px;
}

.usage-stats {
  margin-bottom: 12px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 4px;
  margin-bottom: 8px;
}

.stat-item {
  background: #333;
  padding: 6px;
  border-radius: 3px;
  text-align: center;
  transition: all 0.2s ease;
}

.stat-item:hover {
  background: #444;
  transform: translateY(-1px);
}

.stat-label {
  font-size: 9px;
  color: #aaa;
}

.stat-value {
  font-size: 11px;
  font-weight: bold;
  color: #fff;
  margin-top: 2px;
}

.token-usage {
  background: #2a2a2a;
  padding: 8px;
  border-radius: 3px;
  margin-top: 8px;
}

.usage-header {
  font-size: 10px;
  color: #ccc;
  margin-bottom: 6px;
  text-align: center;
}

.token-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.token-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.token-label {
  font-size: 9px;
  color: #aaa;
  width: 35px;
  flex-shrink: 0;
}

.bar-container {
  flex: 1;
  height: 8px;
  background: #444;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.input-bar {
  background: linear-gradient(90deg, #2196f3, #64b5f6);
}

.output-bar {
  background: linear-gradient(90deg, #4caf50, #81c784);
}

.cost-metrics {
  background: #2a2a2a;
  border-radius: 3px;
  padding: 8px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-size: 10px;
}

.metric-label {
  color: #aaa;
}

.metric-value {
  color: #fff;
  font-weight: 500;
}
</style>