<template>
  <div class="ai-cost-sidebar">
    <CostHeader 
      :loading="loading" 
      :cost-data="costData"
      :view-mode="showDashboard ? 'dashboard' : 'table'"
      @refresh="refreshData"
      @toggle-view="handleToggleView"
    />
    
    <div class="sidebar-content">
      <CostStatus :cost-data="costData" />
      
      <CostRealtime v-if="costData.available" />
      
      <CostMetrics 
        v-if="costData.available"
        :cost-data="costData" 
        :selected-period="selectedPeriod" 
      />
      
      <CostDashboard v-if="costData.available && showDashboard" />
      
      <CostTerminalTable
        v-if="costData.available && !showDashboard"
        :daily-data="dailyData"
        :model-data="modelData"
        @export="handleExport"
      />
      
      <CostActivity 
        v-if="dailyData.length > 0"
        :daily-data="dailyData" 
      />
      
      <CostControls 
        :selected-period="selectedPeriod"
        :model-data="modelData"
        @update-period="updatePeriod"
      />
      
      <!-- Error State -->
      <div v-if="!costData.available" class="error-state">
        <div v-if="costData.error" class="error-message">
          ❌ {{ costData.error }}
          <button @click="loadCostData" class="retry-btn">
            Retry
          </button>
        </div>
        <div v-else class="info-message">
          📊 {{ costData.message || 'No AI cost data available' }}
          <div class="info-sub">
            Start using AI features to see usage statistics.
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-indicator">
      <div class="spinner">⏳</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, defineAsyncComponent } from 'vue'
import CostActivity from './cost/CostActivity.vue'
import CostControls from './cost/CostControls.vue'
// Dynamic import for CostDashboard to reduce initial bundle size
const CostDashboard = defineAsyncComponent(() => import('./cost/CostDashboard.vue'))
import CostHeader from './cost/CostHeader.vue'
import CostMetrics from './cost/CostMetrics.vue'
import CostRealtime from './cost/CostRealtime.vue'
import CostStatus from './cost/CostStatus.vue'
import CostTerminalTable from './cost/CostTerminalTable.vue'

// State
const loading = ref(false)
const selectedPeriod = ref(30)
const showDashboard = ref(true)

interface CostData {
  total_cost: number
  available: boolean
  requests?: number
  input_tokens?: number
  output_tokens?: number
  average_cost_per_request?: number
  cost_per_1k_tokens?: number
  error?: string
  message?: string
}

const costData = ref<CostData>({
  total_cost: 0,
  available: false,
  requests: 0,
  input_tokens: 0,
  output_tokens: 0,
  message: 'Loading cost data...'
})

const dailyData = ref<Array<{
  date: string
  cost: number
  requests: number
}>>([])

const modelData = ref<Array<{
  model: string
  cost: number
  requests: number
}>>([])

// API Functions - No authentication needed as page is OIDC protected
const makeRequest = async (url: string, options: RequestInit = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 5000) // 5 second timeout
  
  try {
    const response = await fetch(url, { 
      ...options, 
      headers,
      signal: controller.signal
    })
    clearTimeout(timeoutId)
    
    if (!response.ok) {
      const error = await response.text()
      throw new Error(`API Error: ${response.status} - ${error}`)
    }
    return response.json()
  } catch (error) {
    clearTimeout(timeoutId)
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timeout')
    }
    throw error
  }
}

const loadCostData = async () => {
  loading.value = true
  try {
    // Load main cost stats with timeout
    const mainData = await makeRequest(`/api/ai/costs?days=${selectedPeriod.value}`)
    costData.value = {
      ...mainData,
      available: mainData.available !== false
    }

    // Only load additional data if main data is available
    if (costData.value.available) {
      try {
        // Load daily and model breakdown in parallel for performance
        const [dailyResponse, modelResponse] = await Promise.all([
          makeRequest(`/api/ai/costs/daily?days=${selectedPeriod.value}`),
          makeRequest(`/api/ai/costs/models?days=${selectedPeriod.value}`)
        ])
        
        dailyData.value = dailyResponse.daily_breakdown || []
        modelData.value = modelResponse.model_breakdown || []
      } catch (detailError) {
        // If detail requests fail, just log but don't fail the whole component
        console.warn('Failed to load detailed cost data:', detailError)
        dailyData.value = []
        modelData.value = []
      }
    }

  } catch (error) {
    console.error('Failed to load cost data:', error)
    costData.value = {
      total_cost: 0,
      available: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      message: 'Failed to load cost data'
    }
  } finally {
    loading.value = false
  }
}

const updatePeriod = async (newPeriod: number) => {
  selectedPeriod.value = newPeriod
  await loadCostData()
}

const refreshData = () => {
  loadCostData()
}

const handleExport = async (format: string) => {
  try {
    const response = await makeRequest(`/api/ai/costs/export?days=${selectedPeriod.value}&format=${format}`)
    
    if (format === 'json') {
      // Download JSON file
      const blob = new Blob([JSON.stringify(response, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `claude-usage-${new Date().toISOString().split('T')[0]}.json`
      a.click()
      URL.revokeObjectURL(url)
    } else if (format === 'csv' && response.csv) {
      // Download CSV file
      const blob = new Blob([response.csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `claude-usage-${new Date().toISOString().split('T')[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
    }
  } catch (error) {
    console.error('Export failed:', error)
  }
}

const handleToggleView = (mode: string) => {
  showDashboard.value = mode === 'dashboard'
}

onMounted(() => {
  // No authentication check needed - page is OIDC protected
  loadCostData()
})
</script>

<style scoped>
.ai-cost-sidebar {
  height: 100%;
  width: 100%;
  background: #1e1e1e;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.error-state {
  text-align: center;
  padding: 20px;
  color: #aaa;
  font-size: 11px;
  margin: 8px;
}

.error-message { 
  color: #f44336; 
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}

.info-message { 
  color: #aaa; 
  text-align: center;
}

.info-sub {
  font-size: 10px;
  color: #666;
  margin-top: 8px;
}

.retry-btn {
  padding: 4px 8px;
  background: #4caf50;
  border: none;
  border-radius: 3px;
  color: white;
  font-size: 10px;
  cursor: pointer;
  transition: background 0.2s;
}

.retry-btn:hover {
  background: #45a049;
}

.loading-indicator {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.spinner {
  font-size: 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Scrollbar styling */
.sidebar-content::-webkit-scrollbar {
  width: 4px;
}

.sidebar-content::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.sidebar-content::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.sidebar-content::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>