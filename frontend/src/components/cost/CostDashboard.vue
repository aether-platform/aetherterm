<template>
  <div class="cost-dashboard">
    <div class="dashboard-header">
      <h3>AI Cost Analytics</h3>
      <div class="time-selector">
        <button 
          v-for="range in timeRanges" 
          :key="range.value"
          @click="selectedTimeRange = range.value"
          :class="{ active: selectedTimeRange === range.value }"
          class="time-btn"
        >
          {{ range.label }}
        </button>
      </div>
    </div>

    <div class="dashboard-grid">
      <!-- Cost Over Time Chart -->
      <div class="chart-container">
        <h4>Cost Trend</h4>
        <div ref="costTrendChart" class="vega-chart"></div>
      </div>

      <!-- Token Usage Chart -->
      <div class="chart-container">
        <h4>Token Usage</h4>
        <div ref="tokenUsageChart" class="vega-chart"></div>
      </div>

      <!-- Model Distribution Chart -->
      <div class="chart-container">
        <h4>Model Distribution</h4>
        <div ref="modelDistChart" class="vega-chart"></div>
      </div>

      <!-- Hourly Heatmap -->
      <div class="chart-container full-width">
        <h4>Usage Heatmap (24h)</h4>
        <div ref="heatmapChart" class="vega-chart"></div>
      </div>
    </div>

    <div class="dashboard-stats">
      <div class="stat-card">
        <span class="stat-label">Total Cost</span>
        <span class="stat-value">${{ stats.totalCost.toFixed(2) }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Avg Cost/Day</span>
        <span class="stat-value">${{ stats.avgDailyCost.toFixed(2) }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Projected Monthly</span>
        <span class="stat-value">${{ stats.projectedMonthly.toFixed(2) }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Most Used Model</span>
        <span class="stat-value">{{ stats.topModel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
// import embed, { VisualizationSpec } from 'vega-embed' // TODO: Install vega-embed
const embed = null as any // Temporary placeholder
type VisualizationSpec = any // Temporary placeholder

interface TimeRange {
  label: string
  value: string
  days: number
}

const timeRanges: TimeRange[] = [
  { label: '24H', value: '24h', days: 1 },
  { label: '7D', value: '7d', days: 7 },
  { label: '30D', value: '30d', days: 30 },
  { label: '3M', value: '3m', days: 90 },
  { label: '1Y', value: '1y', days: 365 }
]

const selectedTimeRange = ref('7d')
const costTrendChart = ref<HTMLElement>()
const tokenUsageChart = ref<HTMLElement>()
const modelDistChart = ref<HTMLElement>()
const heatmapChart = ref<HTMLElement>()

const stats = ref({
  totalCost: 0,
  avgDailyCost: 0,
  projectedMonthly: 0,
  topModel: 'N/A'
})

const currentDays = computed(() => 
  timeRanges.find(r => r.value === selectedTimeRange.value)?.days || 7
)

// Vega-Lite specifications
const createCostTrendSpec = (data: any[]): VisualizationSpec => ({
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  data: { values: data },
  width: 400,
  height: 200,
  mark: {
    type: 'area',
    line: { color: '#4caf50' },
    color: {
      x1: 1,
      y1: 1,
      x2: 1,
      y2: 0,
      gradient: 'linear',
      stops: [
        { offset: 0, color: '#4caf5020' },
        { offset: 1, color: '#4caf5080' }
      ]
    }
  },
  encoding: {
    x: {
      field: 'date',
      type: 'temporal',
      axis: { 
        title: null,
        grid: false,
        labelColor: '#888'
      }
    },
    y: {
      field: 'cost',
      type: 'quantitative',
      axis: { 
        title: 'Cost ($)',
        grid: true,
        gridColor: '#333',
        labelColor: '#888'
      }
    },
    tooltip: [
      { field: 'date', type: 'temporal', title: 'Date' },
      { field: 'cost', type: 'quantitative', title: 'Cost', format: '$,.2f' },
      { field: 'requests', type: 'quantitative', title: 'Requests' }
    ]
  },
  config: {
    background: '#1a1a1a',
    axis: {
      domainColor: '#666',
      tickColor: '#666'
    }
  }
})

const createTokenUsageSpec = (data: any[]): VisualizationSpec => ({
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  data: { values: data },
  width: 400,
  height: 200,
  layer: [
    {
      mark: { type: 'line', color: '#2196f3', strokeWidth: 2 },
      encoding: {
        x: { field: 'date', type: 'temporal' },
        y: { field: 'input_tokens', type: 'quantitative' }
      }
    },
    {
      mark: { type: 'line', color: '#ff9800', strokeWidth: 2 },
      encoding: {
        x: { field: 'date', type: 'temporal' },
        y: { field: 'output_tokens', type: 'quantitative' }
      }
    }
  ],
  encoding: {
    x: {
      field: 'date',
      type: 'temporal',
      axis: { 
        title: null,
        grid: false,
        labelColor: '#888'
      }
    },
    tooltip: [
      { field: 'date', type: 'temporal', title: 'Date' },
      { field: 'input_tokens', type: 'quantitative', title: 'Input', format: ',.0f' },
      { field: 'output_tokens', type: 'quantitative', title: 'Output', format: ',.0f' }
    ]
  },
  resolve: { scale: { y: 'independent' } },
  config: {
    background: '#1a1a1a',
    axis: {
      domainColor: '#666',
      tickColor: '#666',
      gridColor: '#333'
    }
  }
})

const createModelDistSpec = (data: any[]): VisualizationSpec => ({
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  data: { values: data },
  width: 400,
  height: 200,
  mark: 'arc',
  encoding: {
    theta: { 
      field: 'cost', 
      type: 'quantitative',
      stack: true
    },
    color: { 
      field: 'model',
      type: 'nominal',
      scale: {
        scheme: 'category20'
      },
      legend: {
        orient: 'right',
        labelColor: '#888'
      }
    },
    tooltip: [
      { field: 'model', type: 'nominal', title: 'Model' },
      { field: 'cost', type: 'quantitative', title: 'Cost', format: '$,.2f' },
      { field: 'percentage', type: 'quantitative', title: 'Percentage', format: '.1f' }
    ]
  },
  config: {
    background: '#1a1a1a',
    arc: { innerRadius: 50 }
  }
})

const createHeatmapSpec = (data: any[]): VisualizationSpec => ({
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  data: { values: data },
  width: 850,
  height: 150,
  mark: 'rect',
  encoding: {
    x: {
      field: 'hour',
      type: 'ordinal',
      axis: { 
        title: 'Hour of Day',
        labelColor: '#888'
      }
    },
    y: {
      field: 'day',
      type: 'ordinal',
      axis: { 
        title: 'Day',
        labelColor: '#888'
      }
    },
    color: {
      field: 'cost',
      type: 'quantitative',
      scale: {
        scheme: 'viridis'
      },
      legend: {
        title: 'Cost ($)',
        labelColor: '#888'
      }
    },
    tooltip: [
      { field: 'day', type: 'ordinal', title: 'Day' },
      { field: 'hour', type: 'ordinal', title: 'Hour' },
      { field: 'cost', type: 'quantitative', title: 'Cost', format: '$,.2f' },
      { field: 'requests', type: 'quantitative', title: 'Requests' }
    ]
  },
  config: {
    background: '#1a1a1a',
    axis: {
      domainColor: '#666',
      tickColor: '#666'
    }
  }
})

const loadData = async () => {
  try {
    // Load cost data
    const costResponse = await fetch(`/api/ai/costs?days=${currentDays.value}`)
    const costData = await costResponse.json()
    
    // Load daily breakdown
    const dailyResponse = await fetch(`/api/ai/costs/daily?days=${currentDays.value}`)
    const dailyData = await dailyResponse.json()
    
    // Load model breakdown
    const modelResponse = await fetch(`/api/ai/costs/models?days=${currentDays.value}`)
    const modelData = await modelResponse.json()
    
    // Calculate stats
    if (costData.available) {
      stats.value.totalCost = costData.total_cost || 0
      stats.value.avgDailyCost = stats.value.totalCost / currentDays.value
      stats.value.projectedMonthly = stats.value.avgDailyCost * 30
    }
    
    if (modelData.model_breakdown && modelData.model_breakdown.length > 0) {
      stats.value.topModel = modelData.model_breakdown[0].model
    }
    
    // Render charts
    if (costTrendChart.value && dailyData.daily_breakdown) {
      const chartData = dailyData.daily_breakdown.map((d: any) => ({
        date: new Date(d.date),
        cost: d.cost,
        requests: d.requests
      }))
      await embed(costTrendChart.value, createCostTrendSpec(chartData))
    }
    
    if (tokenUsageChart.value && dailyData.daily_breakdown) {
      const tokenData = dailyData.daily_breakdown.map((d: any) => ({
        date: new Date(d.date),
        input_tokens: d.input_tokens || 0,
        output_tokens: d.output_tokens || 0
      }))
      await embed(tokenUsageChart.value, createTokenUsageSpec(tokenData))
    }
    
    if (modelDistChart.value && modelData.model_breakdown) {
      await embed(modelDistChart.value, createModelDistSpec(modelData.model_breakdown))
    }
    
    // Create hourly heatmap data
    if (heatmapChart.value && currentDays.value <= 7) {
      // For 7 days or less, show hourly heatmap
      const heatmapData = generateHeatmapData(dailyData.daily_breakdown)
      await embed(heatmapChart.value, createHeatmapSpec(heatmapData))
    }
    
  } catch (error) {
    console.error('Failed to load dashboard data:', error)
  }
}

const generateHeatmapData = (dailyData: any[]) => {
  const data = []
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  
  // Generate sample data for now
  for (const day of days) {
    for (let hour = 0; hour < 24; hour++) {
      data.push({
        day,
        hour: hour.toString().padStart(2, '0'),
        cost: Math.random() * 10,
        requests: Math.floor(Math.random() * 50)
      })
    }
  }
  
  return data
}

watch(selectedTimeRange, () => {
  loadData()
})

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.cost-dashboard {
  padding: 16px;
  background: #0a0a0a;
  color: #fff;
  height: 100%;
  overflow-y: auto;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.dashboard-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.time-selector {
  display: flex;
  gap: 4px;
  background: #1a1a1a;
  padding: 4px;
  border-radius: 6px;
}

.time-btn {
  background: transparent;
  border: none;
  color: #888;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.time-btn:hover {
  background: #2a2a2a;
  color: #fff;
}

.time-btn.active {
  background: #4caf50;
  color: #000;
  font-weight: 600;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.chart-container {
  background: #1a1a1a;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid #2a2a2a;
}

.chart-container.full-width {
  grid-column: 1 / -1;
}

.chart-container h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #aaa;
}

.vega-chart {
  width: 100%;
  display: flex;
  justify-content: center;
}

.dashboard-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.stat-card {
  background: #1a1a1a;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-label {
  font-size: 12px;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #4caf50;
}

/* Vega embed styles */
:deep(.vega-embed) {
  width: 100%;
}

:deep(.vega-embed summary) {
  display: none;
}

/* Scrollbar */
.cost-dashboard::-webkit-scrollbar {
  width: 8px;
}

.cost-dashboard::-webkit-scrollbar-track {
  background: #1a1a1a;
}

.cost-dashboard::-webkit-scrollbar-thumb {
  background: #444;
  border-radius: 4px;
}

.cost-dashboard::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>