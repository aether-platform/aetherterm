<template>
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
          <v-icon :color="controlServerConnected ? 'success' : 'error'">
            {{ controlServerConnected ? 'mdi-server-network' : 'mdi-server-network-off' }}
          </v-icon>
          <span class="memory-title">Long-term Memory (ControlServer)</span>
        </div>
        <div class="memory-status">
          <div class="status-indicator" :class="{ active: controlServerConnected }">
            {{ controlServerConnected ? 'Connected' : 'Disconnected' }}
          </div>
          <div class="memory-info" v-if="controlServerConnected">
            <div class="info-item">
              <span>Stored Logs:</span>
              <span>{{ controlServerStats.total_logs || 0 }}</span>
            </div>
            <div class="info-item">
              <span>Memory Size:</span>
              <span>{{ controlServerStats.memory_size || 'N/A' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  redisConnected: boolean
  redisStats: {
    used_memory?: string
    total_keys?: number
  }
  controlServerConnected: boolean
  controlServerStats: {
    total_logs?: number
    memory_size?: string
  }
}

defineProps<Props>()
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

.memory-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.memory-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--surface-variant);
  transition: all 0.3s ease;
  
  &.connected {
    border-color: var(--success-color);
    background: var(--success-surface);
  }
  
  &.disconnected {
    border-color: var(--error-color);
    background: var(--error-surface);
  }
}

.memory-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  
  .memory-title {
    font-weight: 600;
    color: var(--text-primary);
  }
}

.memory-status {
  .status-indicator {
    font-weight: 500;
    padding: 4px 8px;
    border-radius: 4px;
    margin-bottom: 8px;
    
    &.active {
      background: var(--success-color);
      color: white;
    }
    
    &:not(.active) {
      background: var(--error-color);
      color: white;
    }
  }
}

.memory-info {
  .info-item {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
    font-size: 14px;
    
    span:first-child {
      color: var(--text-secondary);
    }
    
    span:last-child {
      font-weight: 500;
      color: var(--text-primary);
    }
  }
}
</style>