<template>
  <div class="cost-realtime">
    <div class="realtime-header">
      <span class="status-indicator" :class="{ active: isMonitoring }"></span>
      <span class="title">Real-time Monitor</span>
      <button @click="toggleMonitoring" class="monitor-btn">
        {{ isMonitoring ? '⏸️' : '▶️' }}
      </button>
    </div>
    
    <div v-if="burnRate.available" class="burn-rate">
      <div class="rate-item">
        <span class="label">Current Rate:</span>
        <span class="value">${{ burnRate.hourly_rate }}/hr</span>
      </div>
      <div class="rate-item">
        <span class="label">Daily Projection:</span>
        <span class="value">${{ burnRate.daily_projection }}</span>
      </div>
      <div class="rate-item">
        <span class="label">Monthly Projection:</span>
        <span class="value">${{ burnRate.monthly_projection }}</span>
      </div>
    </div>
    
    <div v-if="burnRate.time_windows" class="time-windows">
      <h4>Time Windows</h4>
      <div v-for="window in burnRate.time_windows" :key="window.window" class="window-item">
        <span class="window-label">{{ window.window }}:</span>
        <span class="window-cost">${{ window.cost }}</span>
        <span class="window-rate">({{ window.rate_per_hour }}/hr)</span>
      </div>
    </div>
    
    <div v-if="billingBlocks.length > 0" class="billing-blocks">
      <h4>5-Hour Billing Blocks</h4>
      <div v-for="block in billingBlocks.slice(0, 3)" :key="block.block_start" class="block-item">
        <span class="block-time">{{ formatBlockTime(block.block_start) }}</span>
        <span class="block-cost">${{ block.cost }}</span>
        <span class="block-requests">{{ block.requests }} req</span>
      </div>
    </div>
    
    <div class="last-update">
      Last update: {{ formatTime(lastUpdate) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface BurnRate {
  available: boolean
  hourly_rate: number
  daily_projection: number
  monthly_projection: number
  time_windows?: Array<{
    window: string
    cost: number
    rate_per_hour: number
  }>
  last_update?: string
}

interface BillingBlock {
  block_start: string
  cost: number
  requests: number
  duration_hours: number
  active: boolean
}

const isMonitoring = ref(false)
const burnRate = ref<BurnRate>({
  available: false,
  hourly_rate: 0,
  daily_projection: 0,
  monthly_projection: 0
})
const billingBlocks = ref<BillingBlock[]>([])
const lastUpdate = ref(new Date())
let intervalId: number | null = null

const makeRequest = async (url: string) => {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`)
  }
  return response.json()
}

const loadBurnRate = async () => {
  try {
    const data = await makeRequest('/api/ai/costs/burn-rate')
    burnRate.value = data
    lastUpdate.value = new Date()
  } catch (error) {
    console.error('Failed to load burn rate:', error)
  }
}

const loadBillingBlocks = async () => {
  try {
    const data = await makeRequest('/api/ai/costs/blocks?hours=24')
    billingBlocks.value = data.billing_blocks || []
  } catch (error) {
    console.error('Failed to load billing blocks:', error)
  }
}

const startMonitoring = () => {
  loadBurnRate()
  loadBillingBlocks()
  
  // Update every 30 seconds
  intervalId = window.setInterval(() => {
    loadBurnRate()
    loadBillingBlocks()
  }, 30000)
}

const stopMonitoring = () => {
  if (intervalId !== null) {
    clearInterval(intervalId)
    intervalId = null
  }
}

const toggleMonitoring = () => {
  isMonitoring.value = !isMonitoring.value
  if (isMonitoring.value) {
    startMonitoring()
  } else {
    stopMonitoring()
  }
}

const formatTime = (date: Date) => {
  return date.toLocaleTimeString()
}

const formatBlockTime = (isoString: string) => {
  const date = new Date(isoString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  // Load initial data
  loadBurnRate()
  loadBillingBlocks()
})

onUnmounted(() => {
  stopMonitoring()
})
</script>

<style scoped>
.cost-realtime {
  padding: 12px;
  background: #1a1a1a;
  border-radius: 4px;
  margin: 8px;
  font-size: 11px;
}

.realtime-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #333;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #666;
  transition: all 0.3s;
}

.status-indicator.active {
  background: #4caf50;
  box-shadow: 0 0 4px #4caf50;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.title {
  flex: 1;
  font-weight: 600;
  color: #fff;
}

.monitor-btn {
  background: #333;
  border: 1px solid #555;
  border-radius: 3px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.monitor-btn:hover {
  background: #444;
  border-color: #666;
}

.burn-rate {
  margin-bottom: 12px;
}

.rate-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid #2a2a2a;
}

.rate-item:last-child {
  border-bottom: none;
}

.label {
  color: #888;
}

.value {
  color: #4caf50;
  font-weight: 600;
}

.time-windows {
  margin-bottom: 12px;
}

.time-windows h4,
.billing-blocks h4 {
  margin: 0 0 8px 0;
  color: #aaa;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.window-item {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 10px;
}

.window-label {
  color: #888;
  min-width: 30px;
}

.window-cost {
  color: #ffc107;
  font-weight: 600;
}

.window-rate {
  color: #666;
  font-size: 9px;
}

.billing-blocks {
  margin-bottom: 8px;
}

.block-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid #2a2a2a;
  font-size: 10px;
}

.block-time {
  color: #888;
  flex: 1;
}

.block-cost {
  color: #ffc107;
  font-weight: 600;
  margin: 0 8px;
}

.block-requests {
  color: #666;
  font-size: 9px;
}

.last-update {
  text-align: center;
  color: #666;
  font-size: 9px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #2a2a2a;
}
</style>