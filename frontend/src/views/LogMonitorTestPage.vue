<template>
  <div class="log-monitor-test-page">
    <div class="page-header">
      <h1>Terminal Log Monitor Test</h1>
      <div class="page-controls">
        <v-btn
          color="primary"
          @click="initializeTestSystem"
          :loading="isInitializing"
        >
          Initialize Test System
        </v-btn>
        <v-btn
          color="secondary"
          @click="generateTestData"
          :loading="isGenerating"
        >
          Generate Test Data
        </v-btn>
        <v-btn
          color="warning"
          @click="clearTestData"
          :loading="isClearing"
        >
          Clear Test Data
        </v-btn>
      </div>
    </div>

    <!-- Test System Status -->
    <div class="test-status-section">
      <v-card>
        <v-card-title>Test System Status</v-card-title>
        <v-card-text>
          <div class="status-grid">
            <div class="status-item">
              <span class="status-label">Log Processing System:</span>
              <span class="status-value" :class="{ active: testSystemStatus.logProcessing }">
                {{ testSystemStatus.logProcessing ? 'Running' : 'Stopped' }}
              </span>
            </div>
            <div class="status-item">
              <span class="status-label">Mock Terminals:</span>
              <span class="status-value">{{ testSystemStatus.mockTerminals }} active</span>
            </div>
            <div class="status-item">
              <span class="status-label">Generated Logs:</span>
              <span class="status-value">{{ testSystemStatus.generatedLogs }} total</span>
            </div>
            <div class="status-item">
              <span class="status-label">Test Patterns:</span>
              <span class="status-value">{{ testSystemStatus.testPatterns }} patterns</span>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- Log Monitor Panel -->
    <div class="monitor-panel-section">
      <v-card>
        <v-card-title>
          <div class="panel-title">
            <span>Terminal Log Monitor</span>
            <v-btn
              size="small"
              icon="mdi-refresh"
              @click="refreshMonitorData"
              :loading="isRefreshingMonitor"
            />
          </div>
        </v-card-title>
        <v-card-text>
          <TerminalLogMonitorPanel />
        </v-card-text>
      </v-card>
    </div>

    <!-- Test Data Generation Controls -->
    <div class="test-controls-section">
      <v-card>
        <v-card-title>Test Data Generation</v-card-title>
        <v-card-text>
          <div class="generation-controls">
            <div class="control-group">
              <h4>Simulate Terminal Activity</h4>
              <div class="control-row">
                <v-btn
                  @click="simulateNormalActivity"
                  :loading="isSimulating.normal"
                  size="small"
                >
                  Normal Activity
                </v-btn>
                <v-btn
                  @click="simulateErrorBurst"
                  :loading="isSimulating.errors"
                  size="small"
                  color="error"
                >
                  Error Burst
                </v-btn>
                <v-btn
                  @click="simulateCommandPatterns"
                  :loading="isSimulating.commands"
                  size="small"
                  color="info"
                >
                  Command Patterns
                </v-btn>
                <v-btn
                  @click="simulateHighVolume"
                  :loading="isSimulating.volume"
                  size="small"
                  color="warning"
                >
                  High Volume
                </v-btn>
              </div>
            </div>

            <div class="control-group">
              <h4>Pattern Testing</h4>
              <div class="control-row">
                <v-btn
                  @click="testErrorPatterns"
                  :loading="isTestingPatterns.errors"
                  size="small"
                >
                  Test Error Patterns
                </v-btn>
                <v-btn
                  @click="testCommandPatterns"
                  :loading="isTestingPatterns.commands"
                  size="small"
                >
                  Test Command Patterns
                </v-btn>
                <v-btn
                  @click="testSearchFunctionality"
                  :loading="isTestingPatterns.search"
                  size="small"
                >
                  Test Search
                </v-btn>
              </div>
            </div>

            <div class="control-group">
              <h4>Performance Testing</h4>
              <div class="control-row">
                <v-btn
                  @click="stressTestProcessing"
                  :loading="isStressTesting.processing"
                  size="small"
                  color="orange"
                >
                  Stress Test Processing
                </v-btn>
                <v-btn
                  @click="stressTestStorage"
                  :loading="isStressTesting.storage"
                  size="small"
                  color="orange"
                >
                  Stress Test Storage
                </v-btn>
                <v-btn
                  @click="stressTestSearch"
                  :loading="isStressTesting.search"
                  size="small"
                  color="orange"
                >
                  Stress Test Search
                </v-btn>
              </div>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- Test Results -->
    <div class="test-results-section">
      <v-card>
        <v-card-title>Test Results & Logs</v-card-title>
        <v-card-text>
          <div class="results-tabs">
            <v-tabs v-model="resultsTab">
              <v-tab value="console">Console Output</v-tab>
              <v-tab value="performance">Performance Metrics</v-tab>
              <v-tab value="errors">Errors & Warnings</v-tab>
            </v-tabs>

            <v-tabs-window v-model="resultsTab">
              <v-tabs-window-item value="console">
                <div class="console-output">
                  <div
                    v-for="(log, index) in consoleOutput"
                    :key="index"
                    class="console-line"
                    :class="`level-${log.level}`"
                  >
                    <span class="timestamp">{{ formatTimestamp(log.timestamp) }}</span>
                    <span class="level">{{ log.level.toUpperCase() }}</span>
                    <span class="message">{{ log.message }}</span>
                  </div>
                </div>
              </v-tabs-window-item>

              <v-tabs-window-item value="performance">
                <div class="performance-metrics">
                  <div class="metrics-grid">
                    <div class="metric-item">
                      <span class="metric-label">Processing Latency:</span>
                      <span class="metric-value">{{ performanceMetrics.processingLatency }}ms</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">Storage Throughput:</span>
                      <span class="metric-value">{{ performanceMetrics.storageThroughput }} logs/sec</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">Search Response Time:</span>
                      <span class="metric-value">{{ performanceMetrics.searchResponseTime }}ms</span>
                    </div>
                    <div class="metric-item">
                      <span class="metric-label">Memory Usage:</span>
                      <span class="metric-value">{{ performanceMetrics.memoryUsage }}MB</span>
                    </div>
                  </div>
                </div>
              </v-tabs-window-item>

              <v-tabs-window-item value="errors">
                <div class="error-logs">
                  <div
                    v-for="(error, index) in errorLogs"
                    :key="index"
                    class="error-item"
                    :class="`severity-${error.severity}`"
                  >
                    <div class="error-header">
                      <span class="error-timestamp">{{ formatTimestamp(error.timestamp) }}</span>
                      <span class="error-severity">{{ error.severity.toUpperCase() }}</span>
                      <span class="error-component">{{ error.component }}</span>
                    </div>
                    <div class="error-message">{{ error.message }}</div>
                    <div v-if="error.stack" class="error-stack">{{ error.stack }}</div>
                  </div>
                </div>
              </v-tabs-window-item>
            </v-tabs-window>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import TerminalLogMonitorPanel from '../components/TerminalLogMonitorPanel.vue'
import { DEFAULT_TEST_LOG_SIZE } from '@/config/constants'

// Reactive data
const isInitializing = ref(false)
const isGenerating = ref(false)
const isClearing = ref(false)
const isRefreshingMonitor = ref(false)
const resultsTab = ref('console')

const testSystemStatus = ref({
  logProcessing: false,
  mockTerminals: 0,
  generatedLogs: 0,
  testPatterns: 0
})

const isSimulating = ref({
  normal: false,
  errors: false,
  commands: false,
  volume: false
})

const isTestingPatterns = ref({
  errors: false,
  commands: false,
  search: false
})

const isStressTesting = ref({
  processing: false,
  storage: false,
  search: false
})

const consoleOutput = ref([])
const errorLogs = ref([])
const performanceMetrics = ref({
  processingLatency: 0,
  storageThroughput: 0,
  searchResponseTime: 0,
  memoryUsage: 0
})

// Methods
const initializeTestSystem = async () => {
  isInitializing.value = true
  try {
    addConsoleLog('info', 'Initializing test system...')
    
    // Initialize log processing manager
    const response = await fetch('/api/log-processing/initialize', {
      method: 'POST'
    })
    
    if (response.ok) {
      addConsoleLog('info', 'Log processing system initialized')
      testSystemStatus.value.logProcessing = true
      
      // Create mock terminals
      await createMockTerminals()
      
      addConsoleLog('success', 'Test system initialization complete')
    } else {
      throw new Error('Failed to initialize log processing system')
    }
  } catch (error) {
    addConsoleLog('error', `Initialization failed: ${error.message}`)
    addErrorLog('error', 'TestSystem', error.message, error.stack)
  } finally {
    isInitializing.value = false
  }
}

const createMockTerminals = async () => {
  const terminalIds = ['terminal-1', 'terminal-2', 'terminal-3', 'terminal-dev', 'terminal-prod']
  
  for (const terminalId of terminalIds) {
    try {
      const response = await fetch('/api/log-processing/terminals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          terminal_id: terminalId,
          log_file_path: `/tmp/test_logs/${terminalId}.log`
        })
      })
      
      if (response.ok) {
        addConsoleLog('info', `Created mock terminal: ${terminalId}`)
        testSystemStatus.value.mockTerminals++
      }
    } catch (error) {
      addConsoleLog('warning', `Failed to create terminal ${terminalId}: ${error.message}`)
    }
  }
}

const generateTestData = async () => {
  isGenerating.value = true
  try {
    addConsoleLog('info', 'Generating test data...')
    
    // Generate various types of test logs
    await Promise.all([
      generateNormalLogs(),
      generateErrorLogs(),
      generateCommandLogs(),
      generatePatternData()
    ])
    
    addConsoleLog('success', 'Test data generation complete')
    updateTestStats()
  } catch (error) {
    addConsoleLog('error', `Test data generation failed: ${error.message}`)
    addErrorLog('error', 'DataGeneration', error.message)
  } finally {
    isGenerating.value = false
  }
}

const generateNormalLogs = async () => {
  const normalCommands = [
    'ls -la',
    'cd /home/user',
    'npm install',
    'git status',
    'python app.py',
    'docker ps',
    'cat config.json',
    'grep "error" log.txt'
  ]
  
  for (let i = 0; i < 50; i++) {
    const command = normalCommands[Math.floor(Math.random() * normalCommands.length)]
    await simulateTerminalOutput('terminal-1', command, 'INFO')
    await new Promise(resolve => setTimeout(resolve, 10))
  }
}

const generateErrorLogs = async () => {
  const errorMessages = [
    'Error: File not found: /path/to/missing/file.txt',
    'TypeError: Cannot read property "length" of undefined',
    'ConnectionError: Failed to connect to database',
    'PermissionError: Access denied to /etc/shadow',
    'SyntaxError: Unexpected token in JSON at position 42'
  ]
  
  for (const error of errorMessages) {
    await simulateTerminalOutput('terminal-2', error, 'ERROR')
    await new Promise(resolve => setTimeout(resolve, 100))
  }
}

const generateCommandLogs = async () => {
  const commands = [
    { cmd: 'sudo rm -rf /tmp/cache', risk: 'HIGH' },
    { cmd: 'chmod 777 sensitive_file.txt', risk: 'MEDIUM' },
    { cmd: 'git push origin main', risk: 'LOW' },
    { cmd: 'npm run build', risk: 'LOW' },
    { cmd: 'docker exec -it container bash', risk: 'MEDIUM' }
  ]
  
  for (const { cmd, risk } of commands) {
    await simulateTerminalOutput('terminal-3', cmd, risk === 'HIGH' ? 'WARNING' : 'INFO')
    await new Promise(resolve => setTimeout(resolve, 50))
  }
}

const generatePatternData = async () => {
  // Generate repeating patterns for pattern detection
  const patterns = [
    'Application started successfully',
    'Database connection established',
    'User authentication failed',
    'Cache cleared successfully'
  ]
  
  for (const pattern of patterns) {
    for (let i = 0; i < 10; i++) {
      await simulateTerminalOutput('terminal-dev', pattern, 'INFO')
      await new Promise(resolve => setTimeout(resolve, 20))
    }
  }
}

const simulateTerminalOutput = async (terminalId, output, level) => {
  try {
    const response = await fetch('/api/log-processing/simulate-output', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        terminal_id: terminalId,
        output: output,
        level: level,
        timestamp: new Date().toISOString()
      })
    })
    
    if (response.ok) {
      testSystemStatus.value.generatedLogs++
    }
  } catch (error) {
    console.error('Failed to simulate output:', error)
  }
}

const simulateNormalActivity = async () => {
  isSimulating.value.normal = true
  try {
    addConsoleLog('info', 'Simulating normal terminal activity...')
    await generateNormalLogs()
    addConsoleLog('success', 'Normal activity simulation complete')
  } catch (error) {
    addConsoleLog('error', `Normal activity simulation failed: ${error.message}`)
  } finally {
    isSimulating.value.normal = false
  }
}

const simulateErrorBurst = async () => {
  isSimulating.value.errors = true
  try {
    addConsoleLog('info', 'Simulating error burst...')
    await generateErrorLogs()
    addConsoleLog('success', 'Error burst simulation complete')
  } catch (error) {
    addConsoleLog('error', `Error burst simulation failed: ${error.message}`)
  } finally {
    isSimulating.value.errors = false
  }
}

const simulateCommandPatterns = async () => {
  isSimulating.value.commands = true
  try {
    addConsoleLog('info', 'Simulating command patterns...')
    await generateCommandLogs()
    addConsoleLog('success', 'Command pattern simulation complete')
  } catch (error) {
    addConsoleLog('error', `Command pattern simulation failed: ${error.message}`)
  } finally {
    isSimulating.value.commands = false
  }
}

const simulateHighVolume = async () => {
  isSimulating.value.volume = true
  try {
    addConsoleLog('info', 'Simulating high volume activity...')
    
    const promises = []
    for (let i = 0; i < 200; i++) {
      promises.push(simulateTerminalOutput(
        `terminal-${(i % 3) + 1}`,
        `High volume log entry ${i}`,
        i % 10 === 0 ? 'WARNING' : 'INFO'
      ))
    }
    
    await Promise.all(promises)
    addConsoleLog('success', 'High volume simulation complete')
  } catch (error) {
    addConsoleLog('error', `High volume simulation failed: ${error.message}`)
  } finally {
    isSimulating.value.volume = false
  }
}

const testErrorPatterns = async () => {
  isTestingPatterns.value.errors = true
  try {
    addConsoleLog('info', 'Testing error pattern detection...')
    
    const response = await fetch('/api/log-processing/test-error-patterns', {
      method: 'POST'
    })
    
    if (response.ok) {
      const result = await response.json()
      addConsoleLog('success', `Error pattern test complete: ${result.patterns_detected} patterns detected`)
    }
  } catch (error) {
    addConsoleLog('error', `Error pattern test failed: ${error.message}`)
  } finally {
    isTestingPatterns.value.errors = false
  }
}

const testCommandPatterns = async () => {
  isTestingPatterns.value.commands = true
  try {
    addConsoleLog('info', 'Testing command pattern detection...')
    
    const response = await fetch('/api/log-processing/test-command-patterns', {
      method: 'POST'
    })
    
    if (response.ok) {
      const result = await response.json()
      addConsoleLog('success', `Command pattern test complete: ${result.patterns_detected} patterns detected`)
    }
  } catch (error) {
    addConsoleLog('error', `Command pattern test failed: ${error.message}`)
  } finally {
    isTestingPatterns.value.commands = false
  }
}

const testSearchFunctionality = async () => {
  isTestingPatterns.value.search = true
  try {
    addConsoleLog('info', 'Testing search functionality...')
    
    const testQueries = ['error', 'npm install', 'database connection', 'failed']
    
    for (const query of testQueries) {
      const response = await fetch(`/api/log-processing/search?q=${encodeURIComponent(query)}&limit=5`)
      if (response.ok) {
        const results = await response.json()
        addConsoleLog('info', `Search "${query}": ${results.length} results`)
      }
    }
    
    addConsoleLog('success', 'Search functionality test complete')
  } catch (error) {
    addConsoleLog('error', `Search test failed: ${error.message}`)
  } finally {
    isTestingPatterns.value.search = false
  }
}

const stressTestProcessing = async () => {
  isStressTesting.value.processing = true
  try {
    addConsoleLog('info', 'Starting processing stress test...')
    
    const startTime = Date.now()
    const promises = []
    
    for (let i = 0; i < 1000; i++) {
      promises.push(simulateTerminalOutput(
        `terminal-stress-${i % 5}`,
        `Stress test log ${i} with some additional content to make it longer`,
        'INFO'
      ))
    }
    
    await Promise.all(promises)
    const duration = Date.now() - startTime
    
    performanceMetrics.value.processingLatency = duration
    performanceMetrics.value.storageThroughput = Math.round(1000 / (duration / 1000))
    
    addConsoleLog('success', `Processing stress test complete: ${duration}ms for 1000 logs`)
  } catch (error) {
    addConsoleLog('error', `Processing stress test failed: ${error.message}`)
  } finally {
    isStressTesting.value.processing = false
  }
}

const stressTestStorage = async () => {
  isStressTesting.value.storage = true
  try {
    addConsoleLog('info', 'Starting storage stress test...')
    
    const response = await fetch('/api/log-processing/stress-test-storage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_size: DEFAULT_TEST_LOG_SIZE })
    })
    
    if (response.ok) {
      const result = await response.json()
      performanceMetrics.value.memoryUsage = result.memory_usage
      addConsoleLog('success', `Storage stress test complete: ${result.duration}ms`)
    }
  } catch (error) {
    addConsoleLog('error', `Storage stress test failed: ${error.message}`)
  } finally {
    isStressTesting.value.storage = false
  }
}

const stressTestSearch = async () => {
  isStressTesting.value.search = true
  try {
    addConsoleLog('info', 'Starting search stress test...')
    
    const startTime = Date.now()
    const searchPromises = []
    
    for (let i = 0; i < 100; i++) {
      searchPromises.push(
        fetch(`/api/log-processing/search?q=test${i}&limit=10`)
      )
    }
    
    await Promise.all(searchPromises)
    const duration = Date.now() - startTime
    
    performanceMetrics.value.searchResponseTime = Math.round(duration / 100)
    addConsoleLog('success', `Search stress test complete: ${duration}ms for 100 searches`)
  } catch (error) {
    addConsoleLog('error', `Search stress test failed: ${error.message}`)
  } finally {
    isStressTesting.value.search = false
  }
}

const clearTestData = async () => {
  isClearing.value = true
  try {
    addConsoleLog('info', 'Clearing test data...')
    
    const response = await fetch('/api/log-processing/clear-test-data', {
      method: 'DELETE'
    })
    
    if (response.ok) {
      testSystemStatus.value = {
        logProcessing: false,
        mockTerminals: 0,
        generatedLogs: 0,
        testPatterns: 0
      }
      consoleOutput.value = []
      errorLogs.value = []
      addConsoleLog('success', 'Test data cleared successfully')
    }
  } catch (error) {
    addConsoleLog('error', `Clear test data failed: ${error.message}`)
  } finally {
    isClearing.value = false
  }
}

const refreshMonitorData = async () => {
  isRefreshingMonitor.value = true
  try {
    // The TerminalLogMonitorPanel will refresh itself
    await new Promise(resolve => setTimeout(resolve, 1000))
    addConsoleLog('info', 'Monitor data refreshed')
  } catch (error) {
    addConsoleLog('error', `Monitor refresh failed: ${error.message}`)
  } finally {
    isRefreshingMonitor.value = false
  }
}

const updateTestStats = async () => {
  try {
    const response = await fetch('/api/log-processing/statistics')
    if (response.ok) {
      const stats = await response.json()
      testSystemStatus.value.testPatterns = stats.pattern_analysis?.vector_storage?.total_documents || 0
    }
  } catch (error) {
    console.error('Failed to update test stats:', error)
  }
}

// Helper functions
const addConsoleLog = (level, message) => {
  consoleOutput.value.push({
    timestamp: new Date(),
    level,
    message
  })
  
  // Keep only last 100 logs
  if (consoleOutput.value.length > 100) {
    consoleOutput.value = consoleOutput.value.slice(-100)
  }
}

const addErrorLog = (severity, component, message, stack = null) => {
  errorLogs.value.push({
    timestamp: new Date(),
    severity,
    component,
    message,
    stack
  })
  
  // Keep only last 50 errors
  if (errorLogs.value.length > 50) {
    errorLogs.value = errorLogs.value.slice(-50)
  }
}

const formatTimestamp = (timestamp) => {
  return new Date(timestamp).toLocaleString()
}

// Lifecycle
onMounted(() => {
  addConsoleLog('info', 'Log Monitor Test Page loaded')
})

onUnmounted(() => {
  // Cleanup any running tests
})
</script>

<style scoped>
.log-monitor-test-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid #e0e0e0;
}

.page-header h1 {
  margin: 0;
  color: #333;
}

.page-controls {
  display: flex;
  gap: 12px;
}

.test-status-section,
.monitor-panel-section,
.test-controls-section,
.test-results-section {
  margin-bottom: 24px;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.status-label {
  font-weight: 500;
  color: #666;
}

.status-value {
  font-weight: 600;
  color: #333;
}

.status-value.active {
  color: #4caf50;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.generation-controls {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.control-group h4 {
  margin: 0 0 12px 0;
  color: #333;
  font-size: 1.1em;
}

.control-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.console-output {
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
  padding: 16px;
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.console-line {
  margin-bottom: 4px;
  display: flex;
  gap: 12px;
}

.console-line.level-info {
  color: #4fc3f7;
}

.console-line.level-success {
  color: #81c784;
}

.console-line.level-warning {
  color: #ffb74d;
}

.console-line.level-error {
  color: #e57373;
}

.timestamp {
  color: #888;
  min-width: 100px;
}

.level {
  min-width: 60px;
  font-weight: 600;
}

.message {
  flex: 1;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 4px;
}

.metric-label {
  font-weight: 500;
  color: #666;
}

.metric-value {
  font-weight: 600;
  color: #333;
}

.error-logs {
  max-height: 300px;
  overflow-y: auto;
}

.error-item {
  border: 1px solid #ddd;
  border-radius: 4px;
  margin-bottom: 8px;
  padding: 12px;
}

.error-item.severity-error {
  border-left: 4px solid #f44336;
}

.error-item.severity-warning {
  border-left: 4px solid #ff9800;
}

.error-header {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 0.9em;
}

.error-timestamp {
  color: #666;
}

.error-severity {
  font-weight: 600;
  color: #f44336;
}

.error-component {
  font-weight: 500;
  color: #333;
}

.error-message {
  font-weight: 500;
  margin-bottom: 4px;
}

.error-stack {
  font-family: 'Courier New', monospace;
  font-size: 0.8em;
  color: #666;
  background: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
}
</style>