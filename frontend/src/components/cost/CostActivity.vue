<template>
  <div v-if="dailyData.length > 0" class="recent-activity">
    <h4>Recent Activity</h4>
    <div class="activity-list">
      <div 
        v-for="day in dailyData.slice(0, 5)" 
        :key="day.date"
        class="activity-item"
      >
        <div class="activity-date">{{ formatDate(day.date) }}</div>
        <div class="activity-cost">${{ day.cost.toFixed(4) }}</div>
        <div class="activity-requests">{{ day.requests }} req</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface DailyData {
  date: string
  cost: number
  requests: number
}

defineProps<{
  dailyData: DailyData[]
}>()

const formatDate = (dateStr: string) => {
  try {
    const date = new Date(dateStr)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    
    if (date.toDateString() === today.toDateString()) {
      return 'Today'
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday'
    } else {
      return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric' 
      })
    }
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
.recent-activity {
  margin: 8px;
}

.recent-activity h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #fff;
  font-weight: 500;
  padding-bottom: 4px;
  border-bottom: 1px solid #333;
}

.activity-list {
  max-height: 150px;
  overflow-y: auto;
}

.activity-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  background: #2a2a2a;
  border-radius: 3px;
  margin-bottom: 4px;
  transition: all 0.2s ease;
  font-size: 10px;
}

.activity-item:hover {
  background: #333;
  transform: translateY(-1px);
}

.activity-date {
  color: #ccc;
  font-weight: 500;
}

.activity-cost {
  color: #ffeb3b;
  font-weight: bold;
  text-align: right;
}

.activity-requests {
  color: #aaa;
  font-size: 9px;
  text-align: right;
}

/* Scrollbar styling */
.activity-list::-webkit-scrollbar {
  width: 4px;
}

.activity-list::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.activity-list::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.activity-list::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>