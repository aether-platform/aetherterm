<template>
  <div class="monitor-section">
    <h4>System Overview</h4>
    <div class="overview-grid">
      <div class="overview-card">
        <div class="overview-header">
          <v-icon color="primary">mdi-console-line</v-icon>
          <span>Active Terminals</span>
        </div>
        <div class="overview-value">{{ statistics.active_terminals || 0 }}</div>
      </div>
      
      <div class="overview-card">
        <div class="overview-header">
          <v-icon color="info">mdi-file-document-outline</v-icon>
          <span>Total Logs</span>
        </div>
        <div class="overview-value">{{ statistics.total_logs || 0 }}</div>
      </div>
      
      <div class="overview-card">
        <div class="overview-header">
          <v-icon color="warning">mdi-alert-circle-outline</v-icon>
          <span>Error Count</span>
        </div>
        <div class="overview-value">{{ statistics.error_count || 0 }}</div>
      </div>
      
      <div class="overview-card">
        <div class="overview-header">
          <v-icon color="success">mdi-cog-outline</v-icon>
          <span>Processing Active</span>
        </div>
        <div class="overview-value">
          {{ statistics.processing_active ? 'Yes' : 'No' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  statistics: {
    active_terminals?: number
    total_logs?: number
    error_count?: number
    processing_active?: boolean
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.overview-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--surface-variant);
  text-align: center;
  transition: transform 0.2s ease;
  
  &:hover {
    transform: translateY(-2px);
  }
}

.overview-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.overview-value {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
}
</style>