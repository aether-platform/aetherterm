<template>
  <div class="cost-terminal-table" ref="tableContainer">
    <div class="terminal-header">
      <span class="prompt">$</span>
      <span class="command">ccusage {{ viewMode }}</span>
      <div class="view-switcher">
        <button 
          v-for="mode in viewModes" 
          :key="mode"
          @click="viewMode = mode"
          :class="{ active: viewMode === mode }"
          class="mode-btn"
        >
          {{ mode }}
        </button>
      </div>
    </div>
    
    <div class="terminal-output">
      <!-- Daily View - ccusage style -->
      <div v-if="viewMode === 'daily' && enhancedDailyData.length > 0" class="ccusage-table">
        <div class="table-wrapper">
          <table>
            <thead>
              <tr>
                <th class="border-top">┌─────────────</th>
                <th class="border-top">┬───────────────</th>
                <th class="border-top">┬──────────</th>
                <th class="border-top">┬──────────</th>
                <th class="border-top" v-if="!compactMode">┬───────────────</th>
                <th class="border-top" v-if="!compactMode">┬──────────────</th>
                <th class="border-top">┬───────────────</th>
                <th class="border-top">┬────────────┐</th>
              </tr>
              <tr>
                <th class="header">│    Date     </th>
                <th class="header">│    Models     </th>
                <th class="header right">│   Input   </th>
                <th class="header right">│  Output   </th>
                <th class="header right" v-if="!compactMode">│ Cache Create  </th>
                <th class="header right" v-if="!compactMode">│  Cache Read   </th>
                <th class="header right">│ Total Tokens  </th>
                <th class="header right">│ Cost (USD) │</th>
              </tr>
              <tr>
                <th class="border-mid">├─────────────</th>
                <th class="border-mid">┼───────────────</th>
                <th class="border-mid">┼──────────</th>
                <th class="border-mid">┼──────────</th>
                <th class="border-mid" v-if="!compactMode">┼───────────────</th>
                <th class="border-mid" v-if="!compactMode">┼──────────────</th>
                <th class="border-mid">┼───────────────</th>
                <th class="border-mid">┼────────────┤</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="day in enhancedDailyData" :key="day.date">
                <td>│ {{ formatDate(day.date) }} </td>
                <td>│ {{ formatModels(day.models) }} </td>
                <td class="right">│ {{ formatNumber(day.input_tokens) }} </td>
                <td class="right">│ {{ formatNumber(day.output_tokens) }} </td>
                <td class="right" v-if="!compactMode">│ {{ formatNumber(day.cache_creation) }} </td>
                <td class="right" v-if="!compactMode">│ {{ formatNumber(day.cache_read) }} </td>
                <td class="right">│ {{ formatNumber(day.total_tokens) }} </td>
                <td class="right cost">│ {{ formatCost(day.cost) }} │</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td class="border-sep">├─────────────</td>
                <td class="border-sep">┼───────────────</td>
                <td class="border-sep">┼──────────</td>
                <td class="border-sep">┼──────────</td>
                <td class="border-sep" v-if="!compactMode">┼───────────────</td>
                <td class="border-sep" v-if="!compactMode">┼──────────────</td>
                <td class="border-sep">┼───────────────</td>
                <td class="border-sep">┼────────────┤</td>
              </tr>
              <tr class="total-row">
                <td>│   TOTAL     </td>
                <td>│               </td>
                <td class="right">│ {{ formatNumber(totals.input) }} </td>
                <td class="right">│ {{ formatNumber(totals.output) }} </td>
                <td class="right" v-if="!compactMode">│ {{ formatNumber(totals.cache_creation) }} </td>
                <td class="right" v-if="!compactMode">│ {{ formatNumber(totals.cache_read) }} </td>
                <td class="right">│ {{ formatNumber(totals.total) }} </td>
                <td class="right cost">│ {{ formatCost(totals.cost) }} │</td>
              </tr>
              <tr>
                <td class="border-bottom">└─────────────</td>
                <td class="border-bottom">┴───────────────</td>
                <td class="border-bottom">┴──────────</td>
                <td class="border-bottom">┴──────────</td>
                <td class="border-bottom" v-if="!compactMode">┴───────────────</td>
                <td class="border-bottom" v-if="!compactMode">┴──────────────</td>
                <td class="border-bottom">┴───────────────</td>
                <td class="border-bottom">┴────────────┘</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <div v-if="compactMode" class="compact-notice">
          💡 Terminal width &lt; 100 chars. Showing compact view. Resize for full details.
        </div>
      </div>
      
      <!-- Model View -->
      <table v-else-if="viewMode === 'model' && modelData.length > 0" class="terminal-table">
        <thead>
          <tr>
            <th>Model</th>
            <th class="right">Usage</th>
            <th class="right">Cost</th>
            <th class="right">%</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="model in modelData" :key="model.model">
            <td class="model-name">{{ formatModelName(model.model) }}</td>
            <td class="right">{{ model.requests }} req</td>
            <td class="right cost">${{ model.cost.toFixed(4) }}</td>
            <td class="right">{{ model.percentage }}%</td>
          </tr>
        </tbody>
      </table>
      
      <!-- Session View -->
      <table v-else-if="viewMode === 'session' && billingBlocks.length > 0" class="terminal-table">
        <thead>
          <tr>
            <th>Block Start</th>
            <th class="right">Duration</th>
            <th class="right">Requests</th>
            <th class="right">Cost</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="block in billingBlocks" :key="block.block_start" :class="{ active: block.active }">
            <td>{{ formatBlockTime(block.block_start) }}</td>
            <td class="right">{{ block.duration_hours }}h</td>
            <td class="right">{{ block.requests }}</td>
            <td class="right cost">${{ block.cost.toFixed(4) }}</td>
          </tr>
        </tbody>
      </table>
      
      <!-- Empty State -->
      <div v-else class="empty-state">
        <pre>No data available for {{ viewMode }} view</pre>
      </div>
    </div>
    
    <div class="terminal-footer">
      <span class="info">{{ formatFooterInfo() }}</span>
      <button @click="exportData" class="export-btn" title="Export data">
        📊
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface Props {
  dailyData?: Array<{
    date: string
    cost: number
    requests: number
    tokens?: number
  }>
  modelData?: Array<{
    model: string
    cost: number
    requests: number
    tokens?: number
    percentage?: number
  }>
}

const props = withDefaults(defineProps<Props>(), {
  dailyData: () => [],
  modelData: () => []
})

const emit = defineEmits<{
  export: [format: string]
}>()

const tableContainer = ref<HTMLElement>()
const viewMode = ref<'daily' | 'model' | 'session'>('daily')
const viewModes = ['daily', 'model', 'session'] as const
const billingBlocks = ref<Array<any>>([])
const terminalWidth = ref(80)

// Computed
const totalRequests = computed(() => 
  props.dailyData.reduce((sum, day) => sum + day.requests, 0)
)

const totalTokens = computed(() => 
  props.dailyData.reduce((sum, day) => sum + (day.tokens || 0), 0)
)

const totalCost = computed(() => 
  props.dailyData.reduce((sum, day) => sum + day.cost, 0)
)

// Methods
const loadBillingBlocks = async () => {
  try {
    const response = await fetch('/api/ai/costs/blocks?hours=24')
    const data = await response.json()
    billingBlocks.value = data.billing_blocks || []
  } catch (error) {
    console.error('Failed to load billing blocks:', error)
  }
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', { 
    month: 'short', 
    day: '2-digit',
    year: terminalWidth.value > 60 ? 'numeric' : '2-digit'
  })
}

const formatTokens = (tokens: number) => {
  if (tokens > 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`
  } else if (tokens > 1_000) {
    return `${(tokens / 1_000).toFixed(1)}K`
  }
  return tokens.toString()
}

const formatModelName = (model: string) => {
  // Shorten model names for narrow terminals
  if (terminalWidth.value < 60) {
    return model.replace('claude-3-', 'c3-')
      .replace('claude-3-5-', 'c3.5-')
      .replace('-20240229', '')
      .replace('-20241022', '')
      .replace('-20240307', '')
  }
  return model
}

const formatBlockTime = (isoString: string) => {
  const date = new Date(isoString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

const formatFooterInfo = () => {
  const mode = viewMode.value
  if (mode === 'daily') {
    return `${props.dailyData.length} days | $${totalCost.value.toFixed(2)} total`
  } else if (mode === 'model') {
    return `${props.modelData.length} models | $${totalCost.value.toFixed(2)} total`
  } else {
    return `${billingBlocks.value.length} blocks | 5-hour billing windows`
  }
}

const exportData = () => {
  emit('export', 'json')
}

const updateTerminalWidth = () => {
  if (tableContainer.value) {
    const width = tableContainer.value.offsetWidth
    // Estimate character width (assuming ~8px per character)
    terminalWidth.value = Math.floor(width / 8)
  }
}

onMounted(() => {
  loadBillingBlocks()
  updateTerminalWidth()
  window.addEventListener('resize', updateTerminalWidth)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateTerminalWidth)
})
</script>

<style scoped>
.cost-terminal-table {
  background: #000;
  color: #0f0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  border-radius: 4px;
  overflow: hidden;
  margin: 8px;
}

.terminal-header {
  background: #111;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid #333;
}

.prompt {
  color: #0f0;
  font-weight: bold;
}

.command {
  color: #fff;
  flex: 1;
}

.view-switcher {
  display: flex;
  gap: 4px;
}

.mode-btn {
  background: #222;
  border: 1px solid #444;
  color: #888;
  padding: 2px 8px;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}

.mode-btn:hover {
  background: #333;
  color: #aaa;
}

.mode-btn.active {
  background: #0f0;
  color: #000;
  border-color: #0f0;
}

.terminal-output {
  padding: 12px;
  min-height: 200px;
  max-height: 400px;
  overflow-y: auto;
}

.terminal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.terminal-table th {
  text-align: left;
  padding: 4px 8px;
  border-bottom: 1px solid #0f0;
  color: #0f0;
  font-weight: normal;
  text-transform: uppercase;
}

.terminal-table td {
  padding: 4px 8px;
  border-bottom: 1px solid #222;
}

.terminal-table tbody tr:hover {
  background: #111;
}

.terminal-table .right {
  text-align: right;
}

.terminal-table .cost {
  color: #ff0;
  font-weight: bold;
}

.terminal-table .model-name {
  color: #0ff;
}

.terminal-table tr.active {
  background: #1a1a1a;
}

.terminal-table tr.active td {
  color: #fff;
}

.total-row {
  border-top: 2px solid #0f0;
  font-weight: bold;
}

.total-row td {
  padding-top: 8px;
  border-bottom: none;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #666;
}

.empty-state pre {
  margin: 0;
  font-family: inherit;
}

.terminal-footer {
  background: #111;
  padding: 8px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid #333;
  font-size: 10px;
}

.info {
  color: #888;
}

.export-btn {
  background: transparent;
  border: 1px solid #444;
  padding: 2px 6px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.export-btn:hover {
  background: #222;
  border-color: #666;
}

/* Scrollbar styling */
.terminal-output::-webkit-scrollbar {
  width: 8px;
}

.terminal-output::-webkit-scrollbar-track {
  background: #111;
}

.terminal-output::-webkit-scrollbar-thumb {
  background: #0f0;
  border-radius: 4px;
}

.terminal-output::-webkit-scrollbar-thumb:hover {
  background: #0f0;
  opacity: 0.8;
}

/* Responsive adjustments */
@media (max-width: 600px) {
  .terminal-table {
    font-size: 10px;
  }
  
  .terminal-table th,
  .terminal-table td {
    padding: 2px 4px;
  }
}
</style>