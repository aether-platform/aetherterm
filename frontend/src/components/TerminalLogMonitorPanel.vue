<template>
  <div class="terminal-log-monitor-panel">
    <div class="panel-header">
      <h3>Terminal Log Monitor</h3>
      <div class="refresh-controls">
        <v-btn
          size="small"
          icon="mdi-refresh"
          @click="refreshStatistics"
          :loading="isLoading"
        />
        <v-switch
          v-model="autoRefresh"
          label="Auto Refresh"
          density="compact"
          hide-details
        />
      </div>
    </div>

    <!-- Memory Status -->
    <div class="monitor-section">
      <h4>Memory Systems</h4>
      <div class="memory-status-grid">
        <div class="memory-card redis-memory" :class="{ 'connected': redisConnected, 'disconnected': !redisConnected }">
          <div class="memory-header">
            <v-icon :color="redisConnected ? 'success' : 'error'">
              {{ redisConnected ? 'mdi-database-check' : 'mdi-database-remove' }}
            </v-icon>
            <span class="memory-title">Short-term Memory (Redis)</span>
          </div>
          <div class="memory-status">
            <div class="status-indicator" :class="{ active: redisConnected }">
              {{ redisConnected ? 'Connected' : 'Disconnected' }}
            </div>
            <div class="memory-info" v-if="redisConnected">
              <div class="info-item">
                <span>Used Memory:</span>
                <span>{{ redisStats.used_memory || 'N/A' }}</span>
              </div>
              <div class="info-item">
                <span>Keys:</span>
                <span>{{ redisStats.total_keys || 0 }}</span>
              </div>
            </div>
          </div>
        </div>
        
        <div class="memory-card controlserver-memory" :class="{ 'connected': controlServerConnected, 'disconnected': !controlServerConnected }">
          <div class="memory-header">
            <v-icon :color="controlServerConnected ? 'success' : 'warning'">
              {{ controlServerConnected ? 'mdi-server-network' : 'mdi-server-network-off' }}
            </v-icon>
            <span class="memory-title">Long-term Memory (ControlServer)</span>
          </div>
          <div class="memory-status">
            <div class="status-indicator" :class="{ active: controlServerConnected }">
              {{ controlServerConnected ? 'Connected' : 'Unavailable' }}
            </div>
            <div class="memory-info" v-if="controlServerConnected">
              <div class="info-item">
                <span>Vector Store:</span>
                <span>{{ controlServerStats.vector_documents || 0 }} docs</span>
              </div>
              <div class="info-item">
                <span>Summaries:</span>
                <span>{{ controlServerStats.log_summaries || 0 }}</span>
              </div>
            </div>
            <div class="memory-warning" v-else>
              <v-icon color="warning" size="small">mdi-alert</v-icon>
              <span>Limited functionality without ControlServer</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- System Overview -->
    <div class="monitor-section">
      <h4>System Overview</h4>
      <div class="overview-grid">
        <div class="metric-card">
          <div class="metric-value">{{ systemStats.activeTerminals?.count || 0 }}</div>
          <div class="metric-label">Active Terminals</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ totalLogVolume }}</div>
          <div class="metric-label">Total Log Volume</div>
        </div>
        <div class="metric-card">
          <div class="metric-value">{{ systemStats.pattern_analysis?.vector_storage?.total_documents || 0 }}</div>
          <div class="metric-label">Stored Patterns</div>
        </div>
        <div class="metric-card">
          <div class="metric-value" :class="processingStatusClass">
            {{ systemStats.system_status?.processing_active ? 'Active' : 'Inactive' }}
          </div>
          <div class="metric-label">Processing Status</div>
        </div>
      </div>
    </div>

    <!-- Unprocessed Logs Status -->
    <div class="monitor-section">
      <h4>Unprocessed Logs</h4>
      <div class="unprocessed-grid">
        <div class="unprocessed-card">
          <div class="unprocessed-header">
            <span class="stage-icon">📥</span>
            <span class="stage-name">Redis Queue</span>
          </div>
          <div class="unprocessed-value" :class="getQueueStatusClass('redis')">
            {{ processingQueue.redis_pending || 0 }}
          </div>
          <div class="unprocessed-label">Pending logs in Redis buffer</div>
        </div>

        <div class="unprocessed-card">
          <div class="unprocessed-header">
            <span class="stage-icon">⚙️</span>
            <span class="stage-name">SQL Processing</span>
          </div>
          <div class="unprocessed-value" :class="getQueueStatusClass('sql')">
            {{ processingQueue.sql_pending || 0 }}
          </div>
          <div class="unprocessed-label">Waiting for SQL processing</div>
        </div>

        <div class="unprocessed-card">
          <div class="unprocessed-header">
            <span class="stage-icon">🧠</span>
            <span class="stage-name">Vector Processing</span>
          </div>
          <div class="unprocessed-value" :class="getQueueStatusClass('vector')">
            {{ processingQueue.vector_pending || 0 }}
          </div>
          <div class="unprocessed-label">Awaiting pattern extraction</div>
        </div>

        <div class="unprocessed-card total">
          <div class="unprocessed-header">
            <span class="stage-icon">📊</span>
            <span class="stage-name">Total Unprocessed</span>
          </div>
          <div class="unprocessed-value total-value">
            {{ totalUnprocessed }}
          </div>
          <div class="unprocessed-label">{{ processingQueue.processing_rate || 0 }} logs/min processing rate</div>
        </div>
      </div>
    </div>

    <!-- Pattern Ranking -->
    <div class="monitor-section">
      <h4>Pattern Analysis & Ranking</h4>
      <div class="pattern-ranking">
        <div class="ranking-tabs">
          <v-tabs v-model="patternTab" density="compact">
            <v-tab value="matches">Top Matches</v-tab>
            <v-tab value="errors">Error Patterns</v-tab>
            <v-tab value="commands">Command Patterns</v-tab>
          </v-tabs>
        </div>

        <v-tabs-window v-model="patternTab">
          <!-- Top Matches Tab -->
          <v-tabs-window-item value="matches">
            <div class="pattern-list">
              <div class="pattern-header-row">
                <span class="pattern-col-rank">#</span>
                <span class="pattern-col-type">Type</span>
                <span class="pattern-col-matches">Matches (24h)</span>
                <span class="pattern-col-trend">Trend</span>
                <span class="pattern-col-content">Pattern</span>
              </div>
              <div
                v-for="(pattern, index) in topMatchingPatterns"
                :key="pattern.id"
                class="pattern-ranking-item"
                :class="{ 'high-activity': pattern.matches > 50 }"
              >
                <span class="pattern-rank">{{ index + 1 }}</span>
                <span class="pattern-type" :class="`type-${pattern.type.toLowerCase()}`">
                  {{ pattern.type }}
                </span>
                <span class="pattern-matches">
                  <span class="matches-number">{{ pattern.matches }}</span>
                  <span class="matches-frequency">{{ pattern.frequency }}x total</span>
                </span>
                <span class="pattern-trend">
                  <div class="trend-indicator" :class="pattern.trend">
                    {{ getTrendIcon(pattern.trend) }}
                  </div>
                </span>
                <span class="pattern-content">
                  {{ truncateText(pattern.content, 80) }}
                </span>
              </div>
            </div>
          </v-tabs-window-item>

          <!-- Error Patterns Tab -->
          <v-tabs-window-item value="errors">
            <div class="error-pattern-summary">
              <div class="error-stats-grid">
                <div class="error-stat-card">
                  <div class="stat-value error">{{ errorPatternStats.total_error_patterns || 0 }}</div>
                  <div class="stat-label">Error Patterns</div>
                </div>
                <div class="error-stat-card">
                  <div class="stat-value warning">{{ errorPatternStats.total_warning_patterns || 0 }}</div>
                  <div class="stat-label">Warning Patterns</div>
                </div>
                <div class="error-stat-card">
                  <div class="stat-value critical">{{ errorPatternStats.critical_errors || 0 }}</div>
                  <div class="stat-label">Critical Errors (24h)</div>
                </div>
                <div class="error-stat-card">
                  <div class="stat-value total">{{ errorPatternStats.total_error_matches || 0 }}</div>
                  <div class="stat-label">Total Error Matches</div>
                </div>
              </div>
              
              <div class="error-pattern-list">
                <div
                  v-for="errorPattern in topErrorPatterns"
                  :key="errorPattern.id"
                  class="error-pattern-item"
                  :class="`severity-${errorPattern.severity_level}`"
                >
                  <div class="error-pattern-header">
                    <span class="error-level" :class="`level-${errorPattern.error_level.toLowerCase()}`">
                      {{ errorPattern.error_level }}
                    </span>
                    <span class="error-matches">{{ errorPattern.matches_24h }} matches today</span>
                    <span class="error-severity">
                      Severity: {{ (errorPattern.severity_score * 10).toFixed(1) }}/10
                    </span>
                  </div>
                  <div class="error-pattern-content">
                    {{ truncateText(errorPattern.content, 120) }}
                  </div>
                  <div class="error-pattern-details">
                    <span class="detail-item">Terminals: {{ errorPattern.terminal_count }}</span>
                    <span class="detail-item">Total: {{ errorPattern.total_frequency }}x</span>
                    <span class="detail-item">First: {{ formatTimestamp(errorPattern.first_seen) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </v-tabs-window-item>

          <!-- Command Patterns Tab -->
          <v-tabs-window-item value="commands">
            <div class="command-pattern-list">
              <div
                v-for="commandPattern in topCommandPatterns"
                :key="commandPattern.id"
                class="command-pattern-item"
                :class="{ 'high-risk': commandPattern.risk_score > 0.7 }"
              >
                <div class="command-pattern-header">
                  <span class="command-type">{{ commandPattern.command_type || 'GENERAL' }}</span>
                  <span class="command-frequency">{{ commandPattern.frequency }}x executed</span>
                  <span class="command-success-rate" :class="getSuccessRateClass(commandPattern.success_rate)">
                    {{ (commandPattern.success_rate * 100).toFixed(1) }}% success
                  </span>
                </div>
                <div class="command-content">
                  <code>{{ truncateText(commandPattern.content, 100) }}</code>
                </div>
                <div class="command-stats">
                  <span class="stat-item">Errors: {{ commandPattern.error_count }}</span>
                  <span class="stat-item">Risk: {{ (commandPattern.risk_score * 10).toFixed(1) }}/10</span>
                  <span class="stat-item">Last: {{ formatTimestamp(commandPattern.last_seen) }}</span>
                </div>
              </div>
            </div>
          </v-tabs-window-item>
        </v-tabs-window>
      </div>
    </div>

    <!-- Terminal Statistics -->
    <div class="monitor-section">
      <h4>Terminal Activity</h4>
      <div class="terminal-list">
        <div
          v-for="terminalId in systemStats.activeTerminals?.terminal_ids || []"
          :key="terminalId"
          class="terminal-item"
          @click="selectTerminal(terminalId)"
          :class="{ selected: selectedTerminal === terminalId }"
        >
          <div class="terminal-header">
            <div class="terminal-id">{{ terminalId }}</div>
            <div class="terminal-status" :class="getTerminalStatusClass(terminalId)">
              <span class="status-dot"></span>
              Active
            </div>
          </div>
          
          <div class="terminal-metrics">
            <div class="metric">
              <span class="metric-name">Logs:</span>
              <span class="metric-value">{{ getTerminalLogCount(terminalId) }}</span>
            </div>
            <div class="metric">
              <span class="metric-name">Bytes:</span>
              <span class="metric-value">{{ formatBytes(getTerminalByteCount(terminalId)) }}</span>
            </div>
            <div class="metric">
              <span class="metric-name">Errors:</span>
              <span class="metric-value error">{{ getTerminalErrorCount(terminalId) }}</span>
            </div>
            <div class="metric">
              <span class="metric-name">Last Update:</span>
              <span class="metric-value">{{ formatTimestamp(getTerminalLastUpdate(terminalId)) }}</span>
            </div>
          </div>

          <!-- Log Volume Chart -->
          <div class="log-volume-chart">
            <div class="chart-title">Recent Activity (1h)</div>
            <div class="volume-bars">
              <div
                v-for="(volume, index) in getTerminalVolumeHistory(terminalId)"
                :key="index"
                class="volume-bar"
                :style="{ height: `${Math.min(volume / 100, 100)}%` }"
                :title="`${volume} logs`"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Selected Terminal Details -->
    <div v-if="selectedTerminal" class="monitor-section">
      <h4>Terminal Details: {{ selectedTerminal }}</h4>
      <div class="terminal-details">
        <div class="detail-tabs">
          <v-tabs v-model="activeTab" density="compact">
            <v-tab value="recent">Recent Logs</v-tab>
            <v-tab value="errors">Errors</v-tab>
            <v-tab value="patterns">Patterns</v-tab>
          </v-tabs>
        </div>

        <v-tabs-window v-model="activeTab">
          <!-- Recent Logs Tab -->
          <v-tabs-window-item value="recent">
            <div class="log-entries">
              <div
                v-for="log in recentLogs"
                :key="log.timestamp"
                class="log-entry"
                :class="getLogLevelClass(log.error_level)"
              >
                <div class="log-header">
                  <span class="log-timestamp">{{ formatTimestamp(log.timestamp) }}</span>
                  <span class="log-level">{{ log.error_level }}</span>
                  <span class="log-type">{{ log.log_type }}</span>
                </div>
                <div class="log-content">
                  <div v-if="log.command" class="log-command">$ {{ log.command }}</div>
                  <div class="log-output">{{ truncateText(log.output_text, 200) }}</div>
                </div>
              </div>
            </div>
          </v-tabs-window-item>

          <!-- Errors Tab -->
          <v-tabs-window-item value="errors">
            <div class="error-summary">
              <div
                v-for="error in terminalErrors"
                :key="error.id"
                class="error-item"
              >
                <div class="error-header">
                  <span class="error-level" :class="getLogLevelClass(error.error_level)">
                    {{ error.error_level }}
                  </span>
                  <span class="error-count">{{ error.count }}x</span>
                  <span class="error-time">{{ formatTimestamp(error.last_seen) }}</span>
                </div>
                <div class="error-message">{{ truncateText(error.output_text, 150) }}</div>
              </div>
            </div>
          </v-tabs-window-item>

          <!-- Patterns Tab -->
          <v-tabs-window-item value="patterns">
            <div class="pattern-analysis">
              <div
                v-for="pattern in terminalPatterns"
                :key="pattern.id"
                class="pattern-item"
              >
                <div class="pattern-header">
                  <span class="pattern-type">{{ pattern.pattern_type }}</span>
                  <span class="pattern-frequency">{{ pattern.frequency }}x</span>
                  <span class="pattern-score">Score: {{ pattern.severity_score?.toFixed(2) }}</span>
                </div>
                <div class="pattern-content">{{ truncateText(pattern.content, 100) }}</div>
              </div>
            </div>
          </v-tabs-window-item>
        </v-tabs-window>
      </div>
    </div>

    <!-- Log Search Interface -->
    <div class="monitor-section">
      <h4>Log Search & Analysis</h4>
      <div class="search-interface">
        <div class="search-controls">
          <div class="search-input-group">
            <v-text-field
              v-model="searchQuery"
              label="Search logs, patterns, or commands"
              prepend-inner-icon="mdi-magnify"
              variant="outlined"
              density="compact"
              @keyup.enter="performSearch"
              clearable
            />
            <v-btn
              color="primary"
              @click="performSearch"
              :loading="isSearching"
              size="large"
            >
              Search
            </v-btn>
          </div>

          <div class="search-filters">
            <v-select
              v-model="searchFilters.dataSource"
              :items="searchDataSources"
              label="Data Source"
              variant="outlined"
              density="compact"
              style="max-width: 200px;"
            />
            <v-select
              v-model="searchFilters.terminalId"
              :items="terminalSelectItems"
              label="Terminal"
              variant="outlined"
              density="compact"
              style="max-width: 200px;"
              clearable
            />
            <v-select
              v-model="searchFilters.logLevel"
              :items="logLevelItems"
              label="Log Level"
              variant="outlined"
              density="compact"
              style="max-width: 150px;"
              clearable
            />
            <v-select
              v-model="searchFilters.timeRange"
              :items="timeRangeItems"
              label="Time Range"
              variant="outlined"
              density="compact"
              style="max-width: 150px;"
            />
          </div>
        </div>

        <!-- Search Results -->
        <div v-if="searchResults.length > 0 || hasSearched" class="search-results">
          <div class="results-header">
            <h5>Search Results ({{ searchResults.length }})</h5>
            <div class="results-controls">
              <v-btn
                size="small"
                variant="outlined"
                @click="showTimelineView = !showTimelineView"
                :color="showTimelineView ? 'primary' : 'default'"
              >
                {{ showTimelineView ? 'List View' : 'Timeline View' }}
              </v-btn>
            </div>
          </div>

          <!-- Timeline View -->
          <div v-if="showTimelineView" class="timeline-view">
            <div class="timeline-container">
              <div class="timeline-line"></div>
              <div
                v-for="(timeGroup, date) in groupedTimelineResults"
                :key="date"
                class="timeline-day-group"
              >
                <div class="timeline-date-header">
                  <h6>{{ formatDate(date) }}</h6>
                  <span class="date-count">{{ timeGroup.length }} events</span>
                </div>
                <div class="timeline-events">
                  <div
                    v-for="result in timeGroup"
                    :key="`timeline-${result.source}-${result.id}`"
                    class="timeline-event"
                    :class="getTimelineEventClass(result)"
                  >
                    <div class="timeline-marker" :class="getTimelineMarkerClass(result)"></div>
                    <div class="timeline-content">
                      <div class="timeline-header">
                        <span class="timeline-time">{{ formatTime(result.timestamp) }}</span>
                        <span class="timeline-terminal">{{ result.terminal_id }}</span>
                        <span class="timeline-type" :class="`type-${result.source}`">{{ result.source }}</span>
                        <span v-if="result.error_level" class="timeline-level" :class="getLogLevelClass(result.error_level)">
                          {{ result.error_level }}
                        </span>
                      </div>
                      <div class="timeline-body">
                        <div v-if="result.command" class="timeline-command">
                          <code>{{ truncateText(result.command, 60) }}</code>
                        </div>
                        <div class="timeline-text">
                          {{ truncateText(result.content || result.output_text || result.raw_output, 100) }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- List View -->
          <div v-else class="list-view">
            <div class="results-tabs">
              <v-tabs v-model="searchResultsTab" density="compact">
                <v-tab value="recent">Recent Logs ({{ searchResults.filter(r => r.source === 'recent').length }})</v-tab>
                <v-tab value="structured">Structured ({{ searchResults.filter(r => r.source === 'structured').length }})</v-tab>
                <v-tab value="patterns">Patterns ({{ searchResults.filter(r => r.source === 'patterns').length }})</v-tab>
              </v-tabs>
            </div>

            <v-tabs-window v-model="searchResultsTab">
              <!-- Recent Logs Results -->
              <v-tabs-window-item value="recent">
                <div class="search-result-list">
                  <div
                    v-for="result in searchResults.filter(r => r.source === 'recent')"
                    :key="`recent-${result.id}`"
                    class="search-result-item"
                  >
                    <div class="result-header">
                      <span class="result-terminal">{{ result.terminal_id }}</span>
                      <span class="result-timestamp">{{ formatTimestamp(result.timestamp) }}</span>
                      <span class="result-type">{{ result.raw_output ? 'Raw Output' : 'Processed Log' }}</span>
                    </div>
                    <div class="result-content">
                      <div v-html="highlightSearchTerms(result.content || result.raw_output, searchQuery)"></div>
                    </div>
                  </div>
                </div>
              </v-tabs-window-item>

              <!-- Structured Logs Results -->
              <v-tabs-window-item value="structured">
                <div class="search-result-list">
                  <div
                    v-for="result in searchResults.filter(r => r.source === 'structured')"
                    :key="`structured-${result.id}`"
                    class="search-result-item structured"
                    :class="getLogLevelClass(result.error_level)"
                  >
                    <div class="result-header">
                      <span class="result-terminal">{{ result.terminal_id }}</span>
                      <span class="result-timestamp">{{ formatTimestamp(result.timestamp) }}</span>
                      <span class="result-level" :class="getLogLevelClass(result.error_level)">
                        {{ result.error_level }}
                      </span>
                      <span class="result-type">{{ result.log_type }}</span>
                    </div>
                    <div class="result-content">
                      <div v-if="result.command" class="result-command">
                        <strong>Command:</strong> 
                        <code v-html="highlightSearchTerms(result.command, searchQuery)"></code>
                      </div>
                      <div class="result-output">
                        <div v-html="highlightSearchTerms(result.output_text, searchQuery)"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </v-tabs-window-item>

              <!-- Pattern Results -->
              <v-tabs-window-item value="patterns">
                <div class="search-result-list">
                  <div
                    v-for="result in searchResults.filter(r => r.source === 'patterns')"
                    :key="`pattern-${result.id}`"
                    class="search-result-item pattern"
                  >
                    <div class="result-header">
                      <span class="result-type pattern-type" :class="`type-${result.pattern_type?.toLowerCase()}`">
                        {{ result.pattern_type || 'UNKNOWN' }}
                      </span>
                      <span class="result-frequency">{{ result.frequency }}x occurrences</span>
                      <span class="result-similarity">{{ (result.similarity * 100).toFixed(1) }}% match</span>
                      <span class="result-terminals">{{ result.terminal_count || 0 }} terminals</span>
                    </div>
                    <div class="result-content">
                      <div v-html="highlightSearchTerms(result.content, searchQuery)"></div>
                    </div>
                    <div class="pattern-metadata">
                      <span v-if="result.severity_score" class="metadata-item">
                        Severity: {{ (result.severity_score * 10).toFixed(1) }}/10
                      </span>
                      <span v-if="result.risk_score" class="metadata-item">
                        Risk: {{ (result.risk_score * 10).toFixed(1) }}/10
                      </span>
                      <span v-if="result.first_seen" class="metadata-item">
                        First seen: {{ formatTimestamp(result.first_seen) }}
                      </span>
                    </div>
                  </div>
                </div>
              </v-tabs-window-item>
            </v-tabs-window>
          </div>
        </div>

        <!-- No Results State -->
        <div v-else-if="hasSearched && searchResults.length === 0" class="no-results">
          <div class="no-results-icon">🔍</div>
          <div class="no-results-text">
            <h6>No results found</h6>
            <p>Try adjusting your search query or filters</p>
          </div>
        </div>

        <!-- Search Help -->
        <div v-else class="search-help">
          <h6>Search across all log data</h6>
          <div class="search-tips">
            <div class="tip-section">
              <strong>Data Sources:</strong>
              <ul>
                <li><strong>Recent Logs:</strong> Raw terminal output from Redis buffer</li>
                <li><strong>Structured:</strong> Processed logs with command/output separation</li>
                <li><strong>Patterns:</strong> Extracted patterns from Vector DB</li>
              </ul>
            </div>
            <div class="tip-section">
              <strong>Search Tips:</strong>
              <ul>
                <li>Use quotes for exact phrases: "error message"</li>
                <li>Search for error types, commands, or file names</li>
                <li>Combine filters to narrow down results</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Processing Status -->
    <div class="monitor-section">
      <h4>Processing Pipeline</h4>
      <div class="pipeline-status">
        <div class="pipeline-stage" :class="{ active: systemStats.system_status?.processing_active }">
          <div class="stage-icon">📥</div>
          <div class="stage-name">Log Capture</div>
          <div class="stage-status">Redis Buffer</div>
        </div>
        <div class="pipeline-arrow">→</div>
        <div class="pipeline-stage" :class="{ active: systemStats.system_status?.processing_active }">
          <div class="stage-icon">⚙️</div>
          <div class="stage-name">Processing</div>
          <div class="stage-status">SQL Storage</div>
        </div>
        <div class="pipeline-arrow">→</div>
        <div class="pipeline-stage" :class="{ active: systemStats.system_status?.processing_active }">
          <div class="stage-icon">🧠</div>
          <div class="stage-name">Pattern Analysis</div>
          <div class="stage-status">Vector DB</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAetherTerminalStore } from '../stores/aetherTerminalStore'

const terminalStore = useAetherTerminalStore()

// Reactive data
const isLoading = ref(false)
const autoRefresh = ref(true)
const selectedTerminal = ref(null)
const isConnectedToWebSocket = ref(false)
const activeTab = ref('recent')
const systemStats = ref({})
const terminalStatistics = ref({})
const recentLogs = ref([])
const terminalErrors = ref([])
const terminalPatterns = ref([])
const processingQueue = ref({})
const patternTab = ref('matches')
const topMatchingPatterns = ref([])
const topErrorPatterns = ref([])
const topCommandPatterns = ref([])
const errorPatternStats = ref({})

// Memory system status
const redisConnected = ref(false)
const controlServerConnected = ref(false)
const redisStats = ref({})
const controlServerStats = ref({})

// Auto refresh interval
let refreshInterval = null

// Computed properties
const totalLogVolume = computed(() => {
  const terminals = terminalStatistics.value
  let total = 0
  Object.values(terminals).forEach(stats => {
    total += stats.total_entries || 0
  })
  return total.toLocaleString()
})

const processingStatusClass = computed(() => ({
  'status-active': systemStats.value.system_status?.processing_active,
  'status-inactive': !systemStats.value.system_status?.processing_active
}))

const totalUnprocessed = computed(() => {
  const redis = processingQueue.value.redis_pending || 0
  const sql = processingQueue.value.sql_pending || 0
  const vector = processingQueue.value.vector_pending || 0
  return redis + sql + vector
})

// Methods
const refreshStatistics = async () => {
  if (isLoading.value) return
  
  isLoading.value = true
  try {
    // Get system statistics
    try {
      const systemStatsResponse = await fetch('/api/log-processing/statistics')
      if (systemStatsResponse.ok) {
        systemStats.value = await systemStatsResponse.json()
      } else {
        console.warn('System statistics not available, using mock data')
        systemStats.value = getMockSystemStats()
      }
    } catch (error) {
      console.warn('System statistics API not available, using mock data')
      systemStats.value = getMockSystemStats()
    }

    // Get individual terminal statistics
    const activeTerminals = systemStats.value.activeTerminals?.terminal_ids || []
    if (activeTerminals.length > 0) {
      const terminalStatsPromises = activeTerminals.map(async (terminalId) => {
        try {
          const response = await fetch(`/api/log-processing/terminal/${terminalId}/statistics`)
          if (response.ok) {
            const stats = await response.json()
            return { [terminalId]: stats }
          }
        } catch (error) {
          console.warn(`Failed to get statistics for terminal ${terminalId}, using mock data`)
        }
        return { [terminalId]: getMockTerminalStats(terminalId) }
      })

      const terminalStatsResults = await Promise.all(terminalStatsPromises)
      terminalStatistics.value = Object.assign({}, ...terminalStatsResults)
    } else {
      // Use mock data when no active terminals
      terminalStatistics.value = getMockAllTerminalStats()
    }

    // Get processing queue status
    try {
      processingQueue.value = await getMockProcessingQueue()
    } catch (error) {
      console.warn('Processing queue not available, using mock data')
      processingQueue.value = getMockProcessingQueue()
    }

    // Get pattern rankings
    await refreshPatternRankings()

    // Refresh selected terminal details if needed
    if (selectedTerminal.value) {
      await refreshTerminalDetails(selectedTerminal.value)
    }

  } catch (error) {
    console.error('Failed to refresh statistics:', error)
    // Use mock data as fallback
    systemStats.value = getMockSystemStats()
    terminalStatistics.value = getMockAllTerminalStats()
    processingQueue.value = getMockProcessingQueue()
  } finally {
    isLoading.value = false
  }
}

const selectTerminal = async (terminalId) => {
  selectedTerminal.value = terminalId
  await refreshTerminalDetails(terminalId)
}

const refreshTerminalDetails = async (terminalId) => {
  try {
    // Get recent logs
    const logsResponse = await fetch(`/api/log-processing/terminal/${terminalId}/logs?limit=20`)
    if (logsResponse.ok) {
      recentLogs.value = await logsResponse.json()
    }

    // Get errors
    const errorsResponse = await fetch(`/api/log-processing/terminal/${terminalId}/errors`)
    if (errorsResponse.ok) {
      terminalErrors.value = await errorsResponse.json()
    }

    // Get patterns
    const patternsResponse = await fetch(`/api/log-processing/terminal/${terminalId}/patterns`)
    if (patternsResponse.ok) {
      terminalPatterns.value = await patternsResponse.json()
    }

  } catch (error) {
    console.error(`Failed to refresh details for terminal ${terminalId}:`, error)
  }
}

// Helper methods
const getTerminalLogCount = (terminalId) => {
  return terminalStatistics.value[terminalId]?.total_entries || 0
}

const getTerminalByteCount = (terminalId) => {
  return terminalStatistics.value[terminalId]?.total_bytes || 0
}

const getTerminalErrorCount = (terminalId) => {
  // This would need to be added to the statistics endpoint
  return 0
}

const getTerminalLastUpdate = (terminalId) => {
  return terminalStatistics.value[terminalId]?.last_update || null
}

const getTerminalStatusClass = (terminalId) => {
  const stats = terminalStatistics.value[terminalId]
  return {
    'status-active': stats && stats.last_update,
    'status-inactive': !stats || !stats.last_update
  }
}

const getTerminalVolumeHistory = (terminalId) => {
  // Mock data - in real implementation, this would come from the backend
  return Array.from({ length: 24 }, () => Math.floor(Math.random() * 100))
}

const formatBytes = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'N/A'
  return new Date(timestamp).toLocaleString()
}

const truncateText = (text, maxLength) => {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

const getLogLevelClass = (level) => {
  return {
    'log-error': level === 'ERROR',
    'log-warning': level === 'WARNING',
    'log-info': level === 'INFO',
    'log-debug': level === 'DEBUG'
  }
}

// Mock data functions
const getMockSystemStats = () => ({
  activeTerminals: {
    count: 3,
    terminal_ids: ['terminal-1', 'terminal-2', 'terminal-dev']
  },
  pattern_analysis: {
    vector_storage: {
      total_documents: 247
    }
  },
  system_status: {
    processing_active: true,
    background_tasks: 2
  }
})

const getMockTerminalStats = (terminalId) => ({
  total_entries: Math.floor(Math.random() * 1000) + 100,
  total_bytes: Math.floor(Math.random() * 1000000) + 50000,
  last_update: new Date().toISOString()
})

const getMockAllTerminalStats = () => ({
  'terminal-1': getMockTerminalStats('terminal-1'),
  'terminal-2': getMockTerminalStats('terminal-2'),
  'terminal-dev': getMockTerminalStats('terminal-dev')
})

const getMockProcessingQueue = () => ({
  redis_pending: Math.floor(Math.random() * 50),
  sql_pending: Math.floor(Math.random() * 20),
  vector_pending: Math.floor(Math.random() * 10),
  processing_rate: Math.floor(Math.random() * 100) + 50
})

const refreshPatternRankings = async () => {
  // Mock pattern data
  topMatchingPatterns.value = [
    {
      id: '1',
      type: 'ERROR',
      matches: 45,
      frequency: 78,
      trend: 'up',
      content: 'FileNotFoundError: [Errno 2] No such file or directory'
    },
    {
      id: '2', 
      type: 'COMMAND',
      matches: 32,
      frequency: 156,
      trend: 'stable',
      content: 'npm install express'
    },
    {
      id: '3',
      type: 'WARNING',
      matches: 28,
      frequency: 43,
      trend: 'down',
      content: 'DeprecationWarning: Use of deprecated function'
    }
  ]

  topErrorPatterns.value = [
    {
      id: '1',
      error_level: 'ERROR',
      matches_24h: 15,
      severity_score: 0.8,
      content: 'Connection timeout to database server',
      terminal_count: 2,
      total_frequency: 45,
      first_seen: new Date(Date.now() - 86400000).toISOString()
    }
  ]

  topCommandPatterns.value = [
    {
      id: '1',
      command_type: 'NPM',
      frequency: 25,
      success_rate: 0.92,
      content: 'npm run build',
      error_count: 2,
      risk_score: 0.1,
      last_seen: new Date().toISOString()
    }
  ]

  errorPatternStats.value = {
    total_error_patterns: 12,
    total_warning_patterns: 8,
    critical_errors: 3,
    total_error_matches: 67
  }
}

const getQueueStatusClass = (queueType) => {
  const value = processingQueue.value[`${queueType}_pending`] || 0
  if (value > 100) return 'queue-high'
  if (value > 50) return 'queue-medium'
  return 'queue-normal'
}

const getTrendIcon = (trend) => {
  switch(trend) {
    case 'up': return '↗️'
    case 'down': return '↘️'
    default: return '→'
  }
}

const getSuccessRateClass = (rate) => ({
  'success-high': rate > 0.9,
  'success-medium': rate > 0.7,
  'success-low': rate <= 0.7
})

// Helper methods for search functionality  
const searchQuery = ref('')
const searchFilters = ref({
  dataSource: 'all',
  terminalId: null,
  logLevel: null,
  timeRange: '24h'
})
const searchResults = ref([])
const searchResultsTab = ref('recent')
const hasSearched = ref(false)
const isSearching = ref(false)
const showTimelineView = ref(false)

const searchDataSources = [
  { title: 'All Sources', value: 'all' },
  { title: 'Recent Logs', value: 'recent' },
  { title: 'Structured Logs', value: 'structured' },
  { title: 'Patterns', value: 'patterns' }
]

const terminalSelectItems = computed(() => [
  { title: 'All Terminals', value: null },
  ...Object.keys(terminalStatistics.value).map(id => ({
    title: id,
    value: id
  }))
])

const logLevelItems = [
  { title: 'All Levels', value: null },
  { title: 'ERROR', value: 'ERROR' },
  { title: 'WARNING', value: 'WARNING' },
  { title: 'INFO', value: 'INFO' },
  { title: 'DEBUG', value: 'DEBUG' }
]

const timeRangeItems = [
  { title: 'Last Hour', value: '1h' },
  { title: 'Last 24 Hours', value: '24h' },
  { title: 'Last 7 Days', value: '7d' },
  { title: 'Last 30 Days', value: '30d' }
]

const performSearch = async () => {
  if (!searchQuery.value.trim()) return
  
  isSearching.value = true
  hasSearched.value = true
  
  try {
    // Mock search results
    searchResults.value = [
      {
        id: '1',
        source: 'recent',
        terminal_id: 'terminal-1',
        timestamp: new Date().toISOString(),
        raw_output: `Error: ${searchQuery.value} not found in system logs`,
        content: `Error: ${searchQuery.value} not found in system logs`
      },
      {
        id: '2', 
        source: 'structured',
        terminal_id: 'terminal-2',
        timestamp: new Date(Date.now() - 3600000).toISOString(),
        log_type: 'COMMAND',
        error_level: 'INFO',
        command: `search ${searchQuery.value}`,
        output_text: `Searching for ${searchQuery.value}...`
      }
    ]
    
    if (searchQuery.value.toLowerCase().includes('error')) {
      searchResults.value.push({
        id: '3',
        source: 'patterns',
        pattern_type: 'ERROR',
        frequency: 15,
        similarity: 0.85,
        content: `Pattern match for error: ${searchQuery.value}`,
        terminal_count: 2,
        severity_score: 0.7
      })
    }
    
  } catch (error) {
    console.error('Search failed:', error)
  } finally {
    isSearching.value = false
  }
}

const groupedTimelineResults = computed(() => {
  const grouped = {}
  searchResults.value.forEach(result => {
    const date = new Date(result.timestamp).toDateString()
    if (!grouped[date]) {
      grouped[date] = []
    }
    grouped[date].push(result)
  })
  return grouped
})

const highlightSearchTerms = (text, query) => {
  if (!text || !query) return text
  const regex = new RegExp(`(${query})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}

const getTimelineEventClass = (result) => {
  return {
    'timeline-error': result.error_level === 'ERROR',
    'timeline-warning': result.error_level === 'WARNING',
    'timeline-pattern': result.source === 'patterns'
  }
}

const getTimelineMarkerClass = (result) => {
  return {
    'marker-error': result.error_level === 'ERROR',
    'marker-warning': result.error_level === 'WARNING', 
    'marker-pattern': result.source === 'patterns'
  }
}

const formatDate = (dateString) => {
  return new Date(dateString).toLocaleDateString()
}

const formatTime = (timestamp) => {
  return new Date(timestamp).toLocaleTimeString()
}

// WebSocket management
const setupWebSocketConnection = () => {
  if (!terminalStore.service || !terminalStore.service.socket) {
    console.warn('Socket.IO not available for log monitoring')
    return
  }

  const socket = terminalStore.service.socket

  // Subscribe to log monitoring events
  socket.on('log_system_stats', (data) => {
    systemStats.value = data.stats
  })

  socket.on('log_terminal_stats', (data) => {
    if (data.terminal_id && data.stats) {
      terminalStatistics.value[data.terminal_id] = data.stats
    }
  })

  socket.on('log_monitor_subscribed', (data) => {
    console.log('Subscribed to log monitoring:', data)
    isConnectedToWebSocket.value = true
  })

  socket.on('log_monitor_error', (data) => {
    console.error('Log monitor error:', data.error)
    isConnectedToWebSocket.value = false
  })

  socket.on('log_search_results', (data) => {
    if (data.query === searchQuery.value) {
      searchResults.value = data.results
    }
  })

  // Subscribe to log monitoring for all terminals
  socket.emit('log_monitor_subscribe', { terminal_id: 'all' })
  
  isConnectedToWebSocket.value = true
}

const cleanupWebSocketConnection = () => {
  if (!terminalStore.service || !terminalStore.service.socket) {
    return
  }

  const socket = terminalStore.service.socket

  // Unsubscribe from log monitoring
  socket.emit('log_monitor_unsubscribe', { terminal_id: 'all' })

  // Remove event listeners
  socket.off('log_system_stats')
  socket.off('log_terminal_stats')
  socket.off('log_monitor_subscribed')
  socket.off('log_monitor_error')
  socket.off('log_search_results')

  isConnectedToWebSocket.value = false
}


// Lifecycle
onMounted(() => {
  refreshStatistics()
  
  // Setup WebSocket connection
  setupWebSocketConnection()
  
  // Only use polling if WebSocket is not connected
  if (autoRefresh.value && !isConnectedToWebSocket.value) {
    refreshInterval = setInterval(refreshStatistics, 10000) // Refresh every 10 seconds
  }
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
  
  // Cleanup WebSocket connection
  cleanupWebSocketConnection()
})

// Watch auto refresh setting
watch(autoRefresh, (newValue) => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
  
  // Only use polling if WebSocket is not connected
  if (newValue && !isConnectedToWebSocket.value) {
    refreshInterval = setInterval(refreshStatistics, 10000)
  }
})

// Watch WebSocket connection status
watch(isConnectedToWebSocket, (isConnected) => {
  if (isConnected && refreshInterval) {
    // Stop polling when WebSocket is connected
    clearInterval(refreshInterval)
    refreshInterval = null
  } else if (!isConnected && autoRefresh.value) {
    // Start polling when WebSocket is disconnected
    refreshInterval = setInterval(refreshStatistics, 10000)
  }
})
</script>

<style scoped>
.terminal-log-monitor-panel {
  padding: 16px;
  background: #f5f5f5;
  border-radius: 8px;
  height: 100%;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid #e0e0e0;
}

.panel-header h3 {
  margin: 0;
  color: #333;
  font-weight: 600;
}

.refresh-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.monitor-section {
  margin-bottom: 24px;
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.monitor-section h4 {
  margin: 0 0 16px 0;
  color: #333;
  font-weight: 600;
  font-size: 1.1em;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.metric-card {
  text-align: center;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e9ecef;
}

.metric-value {
  font-size: 1.8em;
  font-weight: bold;
  color: #333;
  margin-bottom: 4px;
}

.metric-value.status-active {
  color: #28a745;
}

.metric-value.status-inactive {
  color: #dc3545;
}

.metric-label {
  font-size: 0.85em;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.terminal-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.terminal-item {
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fafafa;
}

.terminal-item:hover {
  background: #f0f0f0;
  border-color: #007bff;
}

.terminal-item.selected {
  background: #e3f2fd;
  border-color: #2196f3;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.terminal-id {
  font-weight: 600;
  color: #333;
}

.terminal-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85em;
}

.terminal-status.status-active {
  color: #28a745;
}

.terminal-status.status-inactive {
  color: #dc3545;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.terminal-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.metric {
  display: flex;
  justify-content: space-between;
  font-size: 0.85em;
}

.metric-name {
  color: #666;
}

.metric-value {
  font-weight: 500;
}

.metric-value.error {
  color: #dc3545;
}

.log-volume-chart {
  margin-top: 12px;
}

.chart-title {
  font-size: 0.8em;
  color: #666;
  margin-bottom: 6px;
}

.volume-bars {
  display: flex;
  align-items: flex-end;
  height: 40px;
  gap: 1px;
  background: #f0f0f0;
  border-radius: 3px;
  padding: 2px;
}

.volume-bar {
  flex: 1;
  background: #007bff;
  min-height: 2px;
  border-radius: 1px;
  opacity: 0.7;
  transition: opacity 0.2s ease;
}

.volume-bar:hover {
  opacity: 1;
}

.terminal-details {
  margin-top: 16px;
}

.log-entries {
  max-height: 300px;
  overflow-y: auto;
}

.log-entry {
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-bottom: 8px;
  padding: 8px;
  background: white;
}

.log-entry.log-error {
  border-left: 4px solid #dc3545;
}

.log-entry.log-warning {
  border-left: 4px solid #ffc107;
}

.log-entry.log-info {
  border-left: 4px solid #28a745;
}

.log-entry.log-debug {
  border-left: 4px solid #6c757d;
}

.log-header {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  font-size: 0.85em;
}

.log-timestamp {
  color: #666;
}

.log-level,
.log-type {
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f8f9fa;
}

.log-command {
  font-family: monospace;
  background: #f8f9fa;
  padding: 4px 8px;
  border-radius: 3px;
  margin-bottom: 4px;
  font-weight: 500;
}

.log-output {
  font-family: monospace;
  font-size: 0.9em;
  white-space: pre-wrap;
  color: #333;
}

.error-summary,
.pattern-analysis {
  max-height: 300px;
  overflow-y: auto;
}

.error-item,
.pattern-item {
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-bottom: 8px;
  padding: 8px;
  background: white;
}

.error-header,
.pattern-header {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  font-size: 0.85em;
  align-items: center;
}

.error-level {
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.error-level.log-error {
  background: #f8d7da;
  color: #721c24;
}

.error-level.log-warning {
  background: #fff3cd;
  color: #856404;
}

.error-count,
.pattern-frequency,
.pattern-score {
  font-weight: 500;
  color: #666;
}

.error-message,
.pattern-content {
  font-family: monospace;
  font-size: 0.9em;
  color: #333;
}

/* Queue status colors */
.queue-normal {
  color: #4caf50;
}

.queue-medium {
  color: #ff9800;
}

.queue-high {
  color: #f44336;
}

/* Success rate colors */
.success-high {
  color: #4caf50;
}

.success-medium {
  color: #ff9800;
}

.success-low {
  color: #f44336;
}

/* Timeline styles */
.timeline-view {
  max-height: 400px;
  overflow-y: auto;
}

.timeline-container {
  position: relative;
  padding-left: 40px;
}

.timeline-line {
  position: absolute;
  left: 20px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #e0e0e0;
}

.timeline-day-group {
  margin-bottom: 24px;
}

.timeline-date-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
}

.timeline-date-header h6 {
  margin: 0;
  color: #333;
}

.date-count {
  font-size: 0.85em;
  color: #666;
}

.timeline-event {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}

.timeline-marker {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #2196f3;
  margin-right: 12px;
  margin-top: 4px;
  position: relative;
  z-index: 1;
}

.timeline-marker.marker-error {
  background: #f44336;
}

.timeline-marker.marker-warning {
  background: #ff9800;
}

.timeline-marker.marker-pattern {
  background: #9c27b0;
}

.timeline-content {
  flex: 1;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 8px 12px;
}

.timeline-header {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  font-size: 0.85em;
}

.timeline-time {
  font-weight: 500;
  color: #333;
}

.timeline-terminal {
  color: #666;
}

.timeline-type {
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f0f0f0;
}

.timeline-type.type-recent {
  background: #e3f2fd;
  color: #1976d2;
}

.timeline-type.type-structured {
  background: #f3e5f5;
  color: #7b1fa2;
}

.timeline-type.type-patterns {
  background: #fff3e0;
  color: #f57c00;
}

.timeline-level {
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 3px;
}

.timeline-command {
  font-family: monospace;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 3px;
  margin-bottom: 4px;
  font-size: 0.9em;
}

.timeline-text {
  font-size: 0.9em;
  color: #333;
}

mark {
  background: #ffeb3b;
  padding: 1px 2px;
  border-radius: 2px;
}

.pipeline-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px;
}

.pipeline-stage {
  text-align: center;
  padding: 12px;
  border-radius: 8px;
  background: #f8f9fa;
  border: 2px solid #e9ecef;
  min-width: 120px;
  opacity: 0.5;
  transition: all 0.3s ease;
}

.pipeline-stage.active {
  opacity: 1;
  border-color: #28a745;
  background: #d4edda;
}

.stage-icon {
  font-size: 1.5em;
  margin-bottom: 4px;
}

.stage-name {
  font-weight: 600;
  margin-bottom: 2px;
}

.stage-status {
  font-size: 0.8em;
  color: #666;
}

.pipeline-arrow {
  font-size: 1.2em;
  color: #666;
}

/* Unprocessed Logs Styles */
.unprocessed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.unprocessed-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  transition: all 0.2s ease;
}

.unprocessed-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

.unprocessed-card.total {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
}

.unprocessed-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 12px;
}

.stage-icon {
  font-size: 1.2em;
}

.stage-name {
  font-weight: 600;
  font-size: 0.9em;
}

.unprocessed-value {
  font-size: 2.2em;
  font-weight: bold;
  margin-bottom: 8px;
  transition: color 0.2s ease;
}

.unprocessed-value.total-value {
  color: white;
}

.unprocessed-label {
  font-size: 0.8em;
  color: #666;
  line-height: 1.2;
}

.unprocessed-card.total .unprocessed-label {
  color: rgba(255, 255, 255, 0.9);
}

/* Pattern Ranking Improvements */
.pattern-ranking {
  background: white;
  border-radius: 8px;
  overflow: hidden;
}

.ranking-tabs {
  border-bottom: 1px solid #e0e0e0;
}

.pattern-list {
  max-height: 400px;
  overflow-y: auto;
}

.pattern-header-row {
  display: grid;
  grid-template-columns: 40px 80px 120px 80px 1fr;
  gap: 12px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 2px solid #e0e0e0;
  font-weight: 600;
  font-size: 0.85em;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.pattern-ranking-item {
  display: grid;
  grid-template-columns: 40px 80px 120px 80px 1fr;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  align-items: center;
  transition: background-color 0.2s ease;
}

.pattern-ranking-item:hover {
  background: #f8f9fa;
}

.pattern-ranking-item.high-activity {
  background: #fff3e0;
  border-left: 4px solid #ff9800;
}

.pattern-rank {
  font-weight: bold;
  color: #666;
  text-align: center;
}

.pattern-type {
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  text-align: center;
  font-size: 0.8em;
  text-transform: uppercase;
}

.pattern-type.type-error {
  background: #ffebee;
  color: #c62828;
}

.pattern-type.type-command {
  background: #e8f5e8;
  color: #2e7d32;
}

.pattern-type.type-warning {
  background: #fff8e1;
  color: #f57c00;
}

.pattern-matches {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.matches-number {
  font-weight: bold;
  font-size: 1.1em;
  color: #333;
}

.matches-frequency {
  font-size: 0.8em;
  color: #666;
}

.pattern-trend {
  text-align: center;
}

.trend-indicator {
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: bold;
}

.trend-indicator.up {
  background: #e8f5e8;
  color: #2e7d32;
}

.trend-indicator.down {
  background: #ffebee;
  color: #c62828;
}

.trend-indicator.stable {
  background: #f5f5f5;
  color: #666;
}

.pattern-content {
  font-family: monospace;
  font-size: 0.9em;
  color: #333;
  background: #f8f9fa;
  padding: 6px 8px;
  border-radius: 4px;
  line-height: 1.3;
}

/* Error Pattern Summary Improvements */
.error-pattern-summary {
  max-height: 500px;
  overflow-y: auto;
}

.error-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.error-stat-card {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 12px;
  text-align: center;
}

.stat-value {
  font-size: 1.8em;
  font-weight: bold;
  margin-bottom: 4px;
}

.stat-value.error {
  color: #dc3545;
}

.stat-value.warning {
  color: #ffc107;
}

.stat-value.critical {
  color: #6f42c1;
}

.stat-value.total {
  color: #28a745;
}

.stat-label {
  font-size: 0.8em;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.error-pattern-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.error-pattern-item {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 12px;
  transition: all 0.2s ease;
}

.error-pattern-item:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.error-pattern-item.severity-high {
  border-left: 4px solid #dc3545;
}

.error-pattern-item.severity-medium {
  border-left: 4px solid #ffc107;
}

.error-pattern-item.severity-low {
  border-left: 4px solid #28a745;
}

.error-pattern-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.error-level {
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.8em;
  text-transform: uppercase;
}

.error-level.level-error {
  background: #ffebee;
  color: #c62828;
}

.error-level.level-warning {
  background: #fff8e1;
  color: #f57c00;
}

.error-level.level-critical {
  background: #f3e5f5;
  color: #7b1fa2;
}

.error-matches,
.error-severity {
  font-size: 0.85em;
  color: #666;
  font-weight: 500;
}

.error-pattern-content {
  font-family: monospace;
  font-size: 0.9em;
  color: #333;
  background: #f8f9fa;
  padding: 8px 10px;
  border-radius: 4px;
  margin-bottom: 8px;
  line-height: 1.4;
}

.error-pattern-details {
  display: flex;
  gap: 16px;
  font-size: 0.8em;
  color: #666;
  flex-wrap: wrap;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Command Pattern Improvements */
.command-pattern-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
}

.command-pattern-item {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 12px;
  transition: all 0.2s ease;
}

.command-pattern-item:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.command-pattern-item.high-risk {
  border-left: 4px solid #ff6b6b;
  background: #fff5f5;
}

.command-pattern-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.command-type {
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.8em;
  text-transform: uppercase;
  background: #e3f2fd;
  color: #1976d2;
}

.command-frequency {
  font-size: 0.85em;
  color: #666;
  font-weight: 500;
}

.command-success-rate {
  font-size: 0.85em;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
}

.command-success-rate.success-high {
  background: #e8f5e8;
  color: #2e7d32;
}

.command-success-rate.success-medium {
  background: #fff8e1;
  color: #f57c00;
}

.command-success-rate.success-low {
  background: #ffebee;
  color: #c62828;
}

.command-content {
  background: #f8f9fa;
  padding: 8px 10px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.command-content code {
  font-family: monospace;
  font-size: 0.9em;
  color: #333;
  line-height: 1.4;
}

.command-stats {
  display: flex;
  gap: 16px;
  font-size: 0.8em;
  color: #666;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Search Interface Improvements */
.search-interface {
  background: white;
  border-radius: 8px;
  padding: 16px;
}

.search-controls {
  margin-bottom: 20px;
}

.search-input-group {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: flex-end;
}

.search-input-group .v-text-field {
  flex: 1;
}

.search-filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.search-results {
  margin-top: 20px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.results-header h5 {
  margin: 0;
  color: #333;
  font-weight: 600;
}

.results-controls {
  display: flex;
  gap: 8px;
}

.search-result-list {
  max-height: 400px;
  overflow-y: auto;
}

.search-result-item {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}

.search-result-item:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.result-header {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 0.85em;
  flex-wrap: wrap;
  align-items: center;
}

.result-terminal,
.result-timestamp,
.result-type,
.result-level,
.result-frequency,
.result-similarity,
.result-terminals {
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 3px;
  background: #f0f0f0;
}

.result-content {
  font-family: monospace;
  font-size: 0.9em;
  color: #333;
  background: #f8f9fa;
  padding: 8px 10px;
  border-radius: 4px;
  line-height: 1.4;
  margin-bottom: 8px;
}

.result-command {
  margin-bottom: 6px;
}

.result-command strong {
  color: #666;
  font-weight: 600;
}

.pattern-metadata {
  display: flex;
  gap: 12px;
  font-size: 0.8em;
  color: #666;
  flex-wrap: wrap;
}

.metadata-item {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
}

/* No Results and Help Styles */
.no-results {
  text-align: center;
  padding: 40px 20px;
  color: #666;
}

.no-results-icon {
  font-size: 3em;
  margin-bottom: 16px;
  opacity: 0.5;
}

.no-results-text h6 {
  margin: 0 0 8px 0;
  color: #333;
}

.no-results-text p {
  margin: 0;
  color: #666;
}

.search-help {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
}

.search-help h6 {
  margin: 0 0 16px 0;
  color: #333;
  font-weight: 600;
}

.search-tips {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
}

.tip-section {
  background: white;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
}

.tip-section strong {
  color: #333;
  display: block;
  margin-bottom: 8px;
}

.tip-section ul {
  margin: 0;
  padding-left: 16px;
}

.tip-section li {
  margin-bottom: 4px;
  font-size: 0.9em;
  color: #666;
  line-height: 1.4;
}
</style>