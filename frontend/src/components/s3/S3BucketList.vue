<template>
  <div v-if="isAuthenticated" class="bucket-section">
    <div class="section-header">
      <h4>Buckets</h4>
      <span class="bucket-count">({{ buckets.length }})</span>
    </div>
    
    <div class="bucket-list">
      <div
        v-for="bucket in buckets"
        :key="bucket.name"
        @click="$emit('selectBucket', bucket.name)"
        class="bucket-item"
        :class="{ active: selectedBucket === bucket.name }"
        :title="bucket.name"
      >
        <span class="bucket-icon">🪣</span>
        <span class="bucket-name">{{ truncateName(bucket.name, 20) }}</span>
        <span class="bucket-date">{{ formatDate(bucket.created) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Bucket {
  name: string
  created: string
}

defineProps<{
  isAuthenticated: boolean
  buckets: Bucket[]
  selectedBucket: string
}>()

defineEmits<{
  selectBucket: [bucketName: string]
}>()

const truncateName = (name: string, maxLength: number) => {
  return name.length > maxLength ? name.substring(0, maxLength) + '...' : name
}

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric' 
    })
  } catch {
    return ''
  }
}
</script>

<style scoped>
.bucket-section {
  margin: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  border-bottom: 1px solid #333;
  margin-bottom: 8px;
}

.section-header h4 {
  margin: 0;
  font-size: 12px;
  color: #fff;
  font-weight: 500;
}

.bucket-count {
  font-size: 10px;
  color: #aaa;
}

.bucket-list {
  max-height: 200px;
  overflow-y: auto;
}

.bucket-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.2s;
  border-left: 2px solid transparent;
}

.bucket-item:hover {
  background: #333;
}

.bucket-item.active {
  background: #1976d2;
  border-left-color: #2196f3;
}

.bucket-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.bucket-name {
  flex: 1;
  font-size: 11px;
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bucket-date {
  font-size: 9px;
  color: #aaa;
  flex-shrink: 0;
}

/* Scrollbar styling */
.bucket-list::-webkit-scrollbar {
  width: 4px;
}

.bucket-list::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.bucket-list::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.bucket-list::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>