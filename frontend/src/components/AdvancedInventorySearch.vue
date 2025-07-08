<template>
  <div class="advanced-inventory-search">
    <!-- Search Header -->
    <div class="search-header">
      <h3>Advanced Inventory Search</h3>
      <div class="search-tools">
        <button 
          @click="toggleConnectionManager"
          class="btn-connections"
          title="Manage Steampipe connections"
        >
          🔌 Connections
        </button>
        <button 
          @click="showQueryBuilder = !showQueryBuilder"
          class="btn-query"
          :class="{ active: showQueryBuilder }"
          title="SQL Query Builder"
        >
          🔍 Query Builder
        </button>
      </div>
    </div>

    <!-- Quick Filters -->
    <div class="quick-filters">
      <div class="filter-group">
        <label>Provider:</label>
        <select v-model="filters.provider" @change="onFilterChange">
          <option value="">All Providers</option>
          <option value="aws">AWS</option>
          <option value="azure">Azure</option>
          <option value="gcp">Google Cloud</option>
          <option value="kubernetes">Kubernetes</option>
        </select>
      </div>

      <div class="filter-group">
        <label>Resource Type:</label>
        <select v-model="filters.resourceType" @change="onFilterChange">
          <option value="">All Types</option>
          <option value="instance">Instances</option>
          <option value="database">Databases</option>
          <option value="storage">Storage</option>
          <option value="network">Network</option>
          <option value="container">Containers</option>
        </select>
      </div>

      <div class="filter-group">
        <label>Status:</label>
        <select v-model="filters.status" @change="onFilterChange">
          <option value="">All Status</option>
          <option value="running">Running</option>
          <option value="stopped">Stopped</option>
          <option value="error">Error</option>
          <option value="pending">Pending</option>
        </select>
      </div>

      <div class="filter-group">
        <label>Location:</label>
        <input 
          v-model="filters.location" 
          @input="onFilterChange"
          type="text" 
          placeholder="Region/Zone"
        />
      </div>

      <button @click="clearFilters" class="btn-clear-filters">Clear All</button>
    </div>

    <!-- Query Builder -->
    <div v-if="showQueryBuilder" class="query-builder">
      <div class="query-builder-header">
        <h4>SQL Query Builder</h4>
        <div class="query-actions">
          <button @click="loadPresetQuery('aws-instances')" class="btn-preset">AWS Instances</button>
          <button @click="loadPresetQuery('azure-vms')" class="btn-preset">Azure VMs</button>
          <button @click="loadPresetQuery('k8s-pods')" class="btn-preset">K8s Pods</button>
          <button @click="executeCustomQuery" :disabled="!customQuery.trim()" class="btn-execute">Execute</button>
        </div>
      </div>
      
      <div class="query-editor">
        <textarea 
          v-model="customQuery"
          placeholder="SELECT * FROM aws_ec2_instance WHERE instance_state->>'Name' = 'running' LIMIT 10;"
          rows="4"
        ></textarea>
      </div>
    </div>

    <!-- Search Results -->
    <div class="search-results">
      <!-- Loading State -->
      <div v-if="isSearching" class="loading-state">
        <div class="loading-spinner"></div>
        <span>Searching inventory...</span>
      </div>

      <!-- Error State -->
      <div v-if="searchError" class="error-state">
        <div class="error-icon">⚠️</div>
        <div class="error-message">{{ searchError }}</div>
        <button @click="retrySearch" class="btn-retry">Retry</button>
      </div>

      <!-- Results -->
      <div v-if="!isSearching && !searchError" class="results-container">
        <div class="results-header">
          <div class="results-info">
            <span class="results-count">{{ searchResults.length }} resources found</span>
            <span v-if="queryExecutionTime" class="execution-time">
              ({{ queryExecutionTime.toFixed(2) }}s)
            </span>
          </div>
          <div class="results-actions">
            <button @click="exportResults" :disabled="searchResults.length === 0" class="btn-export">
              📥 Export CSV
            </button>
            <button @click="refreshSearch" class="btn-refresh">🔄 Refresh</button>
          </div>
        </div>

        <!-- Results Table -->
        <div class="results-table-container">
          <table class="results-table">
            <thead>
              <tr>
                <th @click="sortBy('name')" class="sortable">
                  Name
                  <span class="sort-indicator" :class="getSortClass('name')">{{ getSortIcon('name') }}</span>
                </th>
                <th @click="sortBy('provider')" class="sortable">
                  Provider
                  <span class="sort-indicator" :class="getSortClass('provider')">{{ getSortIcon('provider') }}</span>
                </th>
                <th @click="sortBy('resource_type')" class="sortable">
                  Type
                  <span class="sort-indicator" :class="getSortClass('resource_type')">{{ getSortIcon('resource_type') }}</span>
                </th>
                <th @click="sortBy('status')" class="sortable">
                  Status
                  <span class="sort-indicator" :class="getSortClass('status')">{{ getSortIcon('status') }}</span>
                </th>
                <th @click="sortBy('location')" class="sortable">
                  Location
                  <span class="sort-indicator" :class="getSortClass('location')">{{ getSortIcon('location') }}</span>
                </th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr 
                v-for="item in paginatedResults" 
                :key="item.resource_id"
                class="result-row"
                @click="selectItem(item)"
                :class="{ selected: selectedItem?.resource_id === item.resource_id }"
              >
                <td class="resource-name">
                  <div class="name-content">
                    <span class="resource-icon">{{ getResourceIcon(item.resource_type) }}</span>
                    <span class="name-text">{{ item.name }}</span>
                  </div>
                </td>
                <td class="provider-cell">
                  <span class="provider-badge" :class="`provider-${item.provider}`">
                    {{ item.provider.toUpperCase() }}
                  </span>
                </td>
                <td class="type-cell">{{ formatResourceType(item.resource_type) }}</td>
                <td class="status-cell">
                  <span class="status-badge" :class="`status-${item.status.toLowerCase()}`">
                    {{ item.status }}
                  </span>
                </td>
                <td class="location-cell">{{ item.location }}</td>
                <td class="actions-cell">
                  <button 
                    @click.stop="openInTerminal(item)" 
                    class="btn-action"
                    title="Open in Terminal"
                  >
                    💻
                  </button>
                  <button 
                    @click.stop="analyzeWithAI(item)" 
                    class="btn-action"
                    title="Analyze with AI"
                  >
                    🤖
                  </button>
                  <button 
                    @click.stop="showDetails(item)" 
                    class="btn-action"
                    title="Show Details"
                  >
                    ℹ️
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="pagination">
          <button 
            @click="currentPage = 1" 
            :disabled="currentPage === 1"
            class="btn-page"
          >
            ⏮️ First
          </button>
          <button 
            @click="currentPage--" 
            :disabled="currentPage === 1"
            class="btn-page"
          >
            ⏪ Prev
          </button>
          <span class="page-info">
            Page {{ currentPage }} of {{ totalPages }}
          </span>
          <button 
            @click="currentPage++" 
            :disabled="currentPage === totalPages"
            class="btn-page"
          >
            Next ⏩
          </button>
          <button 
            @click="currentPage = totalPages" 
            :disabled="currentPage === totalPages"
            class="btn-page"
          >
            Last ⏭️
          </button>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!isSearching && !searchError && searchResults.length === 0 && hasSearched" class="empty-state">
        <div class="empty-icon">🔍</div>
        <h4>No Results Found</h4>
        <p>Try adjusting your search criteria or check your connections.</p>
      </div>
    </div>

    <!-- Connection Manager Modal -->
    <div v-if="showConnectionManager" class="modal-overlay" @click.self="showConnectionManager = false">
      <div class="modal-content-large">
        <SteampipeConnectionManager />
        <div class="modal-footer">
          <button @click="showConnectionManager = false" class="btn-close-modal">Close</button>
        </div>
      </div>
    </div>

    <!-- Item Details Modal -->
    <div v-if="showItemDetails && selectedItem" class="modal-overlay" @click.self="showItemDetails = false">
      <div class="modal-content">
        <div class="modal-header">
          <h4>{{ selectedItem.name }} Details</h4>
          <button @click="showItemDetails = false" class="btn-close">✕</button>
        </div>
        <div class="modal-body">
          <div class="detail-section">
            <h5>Basic Information</h5>
            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">Resource ID:</span>
                <span class="detail-value">{{ selectedItem.resource_id }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Name:</span>
                <span class="detail-value">{{ selectedItem.name }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Provider:</span>
                <span class="detail-value">{{ selectedItem.provider }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ selectedItem.resource_type }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Status:</span>
                <span class="detail-value">{{ selectedItem.status }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">Location:</span>
                <span class="detail-value">{{ selectedItem.location }}</span>
              </div>
            </div>
          </div>
          
          <div v-if="selectedItem.metadata && Object.keys(selectedItem.metadata).length > 0" class="detail-section">
            <h5>Metadata</h5>
            <div class="metadata-container">
              <pre>{{ JSON.stringify(selectedItem.metadata, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { inventoryApiService } from '../services/InventoryApiService'
import { useTerminalTabStore } from '../stores/terminalTabStore'
import type { InventoryItem } from '../types/inventory'
import SteampipeConnectionManager from './SteampipeConnectionManager.vue'

const tabStore = useTerminalTabStore()

// State
const searchResults = ref<InventoryItem[]>([])
const isSearching = ref(false)
const searchError = ref<string | null>(null)
const hasSearched = ref(false)
const queryExecutionTime = ref<number | null>(null)
const selectedItem = ref<InventoryItem | null>(null)
const showItemDetails = ref(false)
const showConnectionManager = ref(false)
const showQueryBuilder = ref(false)
const customQuery = ref('')

// Filters
const filters = ref({
  provider: '',
  resourceType: '',
  status: '',
  location: ''
})

// Sorting
const sortField = ref<string>('')
const sortDirection = ref<'asc' | 'desc'>('asc')

// Pagination
const currentPage = ref(1)
const itemsPerPage = 25

// Computed
const sortedResults = computed(() => {
  if (!sortField.value) return searchResults.value

  return [...searchResults.value].sort((a, b) => {
    const aVal = (a as any)[sortField.value] || ''
    const bVal = (b as any)[sortField.value] || ''
    
    const comparison = aVal.toString().localeCompare(bVal.toString())
    return sortDirection.value === 'asc' ? comparison : -comparison
  })
})

const paginatedResults = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage
  const end = start + itemsPerPage
  return sortedResults.value.slice(start, end)
})

const totalPages = computed(() => {
  return Math.ceil(searchResults.value.length / itemsPerPage)
})

// Methods
const performSearch = async () => {
  isSearching.value = true
  searchError.value = null
  hasSearched.value = true
  currentPage.value = 1
  
  const startTime = Date.now()

  try {
    const options: any = { limit: 1000 }
    
    if (filters.value.provider) options.provider = filters.value.provider
    if (filters.value.resourceType) options.resource_type = filters.value.resourceType

    const results = await inventoryApiService.getResources(options)
    
    // Apply client-side filters
    let filteredResults = results
    
    if (filters.value.status) {
      filteredResults = filteredResults.filter(item => 
        item.status.toLowerCase().includes(filters.value.status.toLowerCase())
      )
    }
    
    if (filters.value.location) {
      filteredResults = filteredResults.filter(item => 
        item.location.toLowerCase().includes(filters.value.location.toLowerCase())
      )
    }
    
    searchResults.value = filteredResults
    queryExecutionTime.value = (Date.now() - startTime) / 1000
    
  } catch (error) {
    console.error('Search failed:', error)
    searchError.value = error instanceof Error ? error.message : 'Search failed'
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
}

const executeCustomQuery = async () => {
  if (!customQuery.value.trim()) return

  isSearching.value = true
  searchError.value = null
  hasSearched.value = true
  currentPage.value = 1
  
  const startTime = Date.now()

  try {
    const response = await inventoryApiService.executeQuery({
      sql: customQuery.value
    })
    
    // Convert query results to InventoryItem format
    searchResults.value = response.data.map((row: any) => ({
      resource_id: row.id || row.resource_id || row.name || 'unknown',
      name: row.name || row.title || row.id || 'Unknown',
      provider: row.provider || 'unknown',
      resource_type: row.resource_type || row.type || 'unknown',
      status: row.status || row.state || 'unknown',
      location: row.location || row.region || row.zone || 'unknown',
      metadata: row,
      last_updated: new Date().toISOString()
    }))
    
    queryExecutionTime.value = (Date.now() - startTime) / 1000
    
  } catch (error) {
    console.error('Query execution failed:', error)
    searchError.value = error instanceof Error ? error.message : 'Query execution failed'
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
}

const loadPresetQuery = (preset: string) => {
  const presets: Record<string, string> = {
    'aws-instances': `SELECT 
  instance_id as resource_id,
  tags->>'Name' as name,
  'aws' as provider,
  'ec2_instance' as resource_type,
  instance_state->>'Name' as status,
  availability_zone as location,
  instance_type,
  public_ip_address,
  private_ip_address
FROM aws_ec2_instance 
WHERE instance_state->>'Name' != 'terminated'
LIMIT 100;`,

    'azure-vms': `SELECT 
  vm_id as resource_id,
  name,
  'azure' as provider,
  'virtual_machine' as resource_type,
  power_state as status,
  location,
  size,
  os_type
FROM azure_compute_virtual_machine 
LIMIT 100;`,

    'k8s-pods': `SELECT 
  uid as resource_id,
  name,
  'kubernetes' as provider,
  'pod' as resource_type,
  phase as status,
  namespace as location,
  node_name,
  creation_timestamp
FROM kubernetes_pod 
WHERE phase != 'Succeeded'
LIMIT 100;`
  }
  
  customQuery.value = presets[preset] || ''
}

const onFilterChange = () => {
  if (hasSearched.value) {
    performSearch()
  }
}

const clearFilters = () => {
  filters.value = {
    provider: '',
    resourceType: '',
    status: '',
    location: ''
  }
  if (hasSearched.value) {
    performSearch()
  }
}

const sortBy = (field: string) => {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDirection.value = 'asc'
  }
}

const getSortClass = (field: string) => {
  if (sortField.value !== field) return ''
  return sortDirection.value === 'asc' ? 'sort-asc' : 'sort-desc'
}

const getSortIcon = (field: string) => {
  if (sortField.value !== field) return '↕️'
  return sortDirection.value === 'asc' ? '⬆️' : '⬇️'
}

const selectItem = (item: InventoryItem) => {
  selectedItem.value = item
}

const showDetails = (item: InventoryItem) => {
  selectedItem.value = item
  showItemDetails.value = true
}

const openInTerminal = (item: InventoryItem) => {
  const tab = tabStore.createTab('terminal', `${item.name}`)
  console.log(`Opening ${item.name} in terminal`)
}

const analyzeWithAI = (item: InventoryItem) => {
  const tab = tabStore.createTab('ai-agent', `AI: ${item.name}`)
  console.log(`Analyzing ${item.name} with AI`)
}

const retrySearch = () => {
  performSearch()
}

const refreshSearch = () => {
  performSearch()
}

const exportResults = () => {
  const csv = convertToCSV(searchResults.value)
  downloadCSV(csv, 'inventory-results.csv')
}

const convertToCSV = (data: InventoryItem[]): string => {
  if (data.length === 0) return ''
  
  const headers = ['Name', 'Provider', 'Resource Type', 'Status', 'Location', 'Resource ID']
  const rows = data.map(item => [
    item.name,
    item.provider,
    item.resource_type,
    item.status,
    item.location,
    item.resource_id
  ])
  
  return [headers, ...rows].map(row => 
    row.map(cell => `"${cell}"`).join(',')
  ).join('\n')
}

const downloadCSV = (csv: string, filename: string) => {
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

const toggleConnectionManager = () => {
  showConnectionManager.value = !showConnectionManager.value
}

const getResourceIcon = (resourceType: string): string => {
  const icons: Record<string, string> = {
    ec2_instance: '🖥️',
    virtual_machine: '🖥️',
    pod: '📦',
    container: '📦',
    database: '🗄️',
    storage: '📁',
    bucket: '📁',
    network: '🌐',
    security_group: '🛡️',
    load_balancer: '⚖️'
  }
  
  for (const [key, icon] of Object.entries(icons)) {
    if (resourceType.toLowerCase().includes(key)) {
      return icon
    }
  }
  
  return '📄'
}

const formatResourceType = (resourceType: string): string => {
  return resourceType
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

// Lifecycle
onMounted(() => {
  performSearch()
})

// Watch for filter changes
watch(filters, () => {
  currentPage.value = 1
}, { deep: true })
</script>

<style scoped>
.advanced-inventory-search {
  padding: 1rem;
  max-width: 1400px;
  margin: 0 auto;
}

.search-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid #e0e0e0;
}

.search-header h3 {
  margin: 0;
  color: #333;
}

.search-tools {
  display: flex;
  gap: 0.5rem;
}

.btn-connections, .btn-query {
  padding: 0.5rem 1rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-connections:hover, .btn-query:hover {
  background: #f0f0f0;
}

.btn-query.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.quick-filters {
  display: flex;
  gap: 1rem;
  align-items: end;
  margin-bottom: 1rem;
  padding: 1rem;
  background: #f8f9fa;
  border-radius: 8px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.filter-group label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #555;
}

.filter-group select,
.filter-group input {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  min-width: 120px;
}

.btn-clear-filters {
  padding: 0.5rem 1rem;
  background: #6c757d;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  align-self: flex-end;
}

.query-builder {
  margin-bottom: 1rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
}

.query-builder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #e0e0e0;
}

.query-builder-header h4 {
  margin: 0;
}

.query-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-preset, .btn-execute {
  padding: 0.25rem 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 0.85rem;
}

.btn-execute {
  background: #28a745;
  color: white;
  border-color: #28a745;
}

.query-editor textarea {
  width: 100%;
  padding: 1rem;
  border: none;
  border-radius: 0 0 8px 8px;
  font-family: monospace;
  font-size: 0.9rem;
  resize: vertical;
}

.loading-state, .error-state, .empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 3rem;
  text-align: center;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #f3f3f3;
  border-top: 2px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.results-container {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #f8f9fa;
  border-bottom: 1px solid #e0e0e0;
}

.results-info {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.results-count {
  font-weight: 500;
}

.execution-time {
  color: #666;
  font-size: 0.9rem;
}

.results-actions {
  display: flex;
  gap: 0.5rem;
}

.btn-export, .btn-refresh {
  padding: 0.5rem 1rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 0.9rem;
}

.results-table-container {
  overflow-x: auto;
}

.results-table {
  width: 100%;
  border-collapse: collapse;
}

.results-table th,
.results-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}

.results-table th {
  background: #f8f9fa;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 10;
}

.results-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.results-table th.sortable:hover {
  background: #e9ecef;
}

.sort-indicator {
  margin-left: 0.5rem;
  font-size: 0.8rem;
}

.result-row {
  cursor: pointer;
  transition: background-color 0.2s;
}

.result-row:hover {
  background: #f8f9fa;
}

.result-row.selected {
  background: #e3f2fd;
}

.resource-name .name-content {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.provider-badge, .status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.provider-aws { background: #ff9900; color: white; }
.provider-azure { background: #0078d4; color: white; }
.provider-gcp { background: #4285f4; color: white; }
.provider-kubernetes { background: #326ce5; color: white; }

.status-running { background: #d4edda; color: #155724; }
.status-stopped { background: #f8d7da; color: #721c24; }
.status-error { background: #f8d7da; color: #721c24; }
.status-pending { background: #fff3cd; color: #856404; }

.actions-cell {
  display: flex;
  gap: 0.25rem;
}

.btn-action {
  padding: 0.25rem 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-action:hover {
  background: #f0f0f0;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: #f8f9fa;
  border-top: 1px solid #e0e0e0;
}

.btn-page {
  padding: 0.5rem 1rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}

.btn-page:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-weight: 500;
  margin: 0 1rem;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content,
.modal-content-large {
  background: white;
  border-radius: 8px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-content {
  min-width: 600px;
  max-width: 800px;
}

.modal-content-large {
  min-width: 900px;
  max-width: 1200px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #e0e0e0;
}

.modal-body {
  padding: 1rem;
}

.modal-footer {
  padding: 1rem;
  border-top: 1px solid #e0e0e0;
  text-align: right;
}

.btn-close, .btn-close-modal {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #666;
}

.btn-close-modal {
  background: #6c757d;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-size: 1rem;
}

.detail-section {
  margin-bottom: 1.5rem;
}

.detail-section h5 {
  margin: 0 0 1rem 0;
  color: #333;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 0.5rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-label {
  font-weight: 500;
  color: #666;
  font-size: 0.9rem;
}

.detail-value {
  color: #333;
  word-break: break-all;
}

.metadata-container {
  background: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 1rem;
  max-height: 300px;
  overflow-y: auto;
}

.metadata-container pre {
  margin: 0;
  font-size: 0.85rem;
  white-space: pre-wrap;
}
</style>