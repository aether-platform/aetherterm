<template>
  <div class="monitor-section">
    <h4>Log Search & Analysis</h4>
    <div class="search-container">
      <div class="search-form">
        <v-text-field
          v-model="searchQuery"
          label="Search logs..."
          placeholder="Enter search terms or regex"
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-magnify"
          clearable
          @keydown.enter="performSearch"
        />
        
        <div class="search-options">
          <v-select
            v-model="selectedTerminal"
            :items="terminalOptions"
            label="Terminal"
            variant="outlined"
            density="compact"
            clearable
          />
          
          <v-select
            v-model="searchLimit"
            :items="limitOptions"
            label="Limit"
            variant="outlined"
            density="compact"
          />
          
          <v-btn
            color="primary"
            @click="performSearch"
            :loading="isSearching"
            :disabled="!searchQuery"
          >
            Search
          </v-btn>
        </div>
      </div>
      
      <div v-if="searchResults.length" class="search-results">
        <div class="results-header">
          <span>{{ searchResults.length }} results found</span>
          <v-btn
            size="small"
            variant="outlined"
            @click="exportResults"
          >
            Export
          </v-btn>
        </div>
        
        <div class="results-list">
          <div
            v-for="(result, index) in searchResults"
            :key="index"
            class="result-item"
          >
            <div class="result-header">
              <span class="result-timestamp">{{ formatTimestamp(result.timestamp) }}</span>
              <span class="result-terminal">{{ result.terminal_id }}</span>
              <v-chip
                size="small"
                :color="getLogTypeColor(result.log_type)"
                variant="outlined"
              >
                {{ result.log_type }}
              </v-chip>
            </div>
            <div class="result-content" v-html="highlightSearchTerm(result.content)"></div>
          </div>
        </div>
      </div>
      
      <div v-else-if="hasSearched && !isSearching" class="no-results">
        <v-icon size="48" color="info">mdi-file-search-outline</v-icon>
        <p>No results found for "{{ lastSearchQuery }}"</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface SearchResult {
  timestamp: string | number
  terminal_id: string
  log_type: string
  content: string
}

interface Props {
  terminalOptions: Array<{ title: string; value: string }>
  searchResults: SearchResult[]
  isSearching?: boolean
}

interface Emits {
  (e: 'search', params: {
    query: string
    terminal?: string
    limit: number
  }): void
  (e: 'export-results'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const searchQuery = ref('')
const selectedTerminal = ref<string>()
const searchLimit = ref(100)
const hasSearched = ref(false)
const lastSearchQuery = ref('')

const limitOptions = [
  { title: '50', value: 50 },
  { title: '100', value: 100 },
  { title: '250', value: 250 },
  { title: '500', value: 500 }
]

const formatTimestamp = (timestamp: string | number) => {
  const date = new Date(timestamp)
  return date.toLocaleString()
}

const getLogTypeColor = (type: string) => {
  switch (type) {
    case 'error': return 'error'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'default'
  }
}

const highlightSearchTerm = (content: string) => {
  if (!searchQuery.value) return content
  
  const regex = new RegExp(`(${searchQuery.value})`, 'gi')
  return content.replace(regex, '<mark>$1</mark>')
}

const performSearch = () => {
  if (!searchQuery.value) return
  
  hasSearched.value = true
  lastSearchQuery.value = searchQuery.value
  
  emit('search', {
    query: searchQuery.value,
    terminal: selectedTerminal.value,
    limit: searchLimit.value
  })
}

const exportResults = () => emit('export-results')
</script>

<style scoped lang="scss">
.monitor-section {
  margin-bottom: 24px;
  
  h4 {
    margin-bottom: 16px;
    color: var(--text-primary);
    font-weight: 600;
  }
}

.search-container {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-variant);
}

.search-form {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.search-options {
  display: grid;
  grid-template-columns: 1fr 120px auto;
  gap: 12px;
  margin-top: 12px;
}

.search-results {
  max-height: 500px;
  overflow-y: auto;
}

.results-header {
  padding: 12px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.results-list {
  padding: 8px;
}

.result-item {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--surface);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}

.result-timestamp {
  color: var(--text-secondary);
}

.result-terminal {
  font-family: monospace;
  background: var(--surface-variant);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.result-content {
  font-family: monospace;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-primary);
  word-break: break-word;
  
  :deep(mark) {
    background: var(--warning-color);
    color: var(--text-primary);
    padding: 0 2px;
    border-radius: 2px;
  }
}

.no-results {
  padding: 32px;
  text-align: center;
  color: var(--text-secondary);
  
  p {
    margin-top: 8px;
    margin-bottom: 0;
  }
}
</style>