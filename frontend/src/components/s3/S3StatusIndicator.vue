<template>
  <div v-if="s3Status.message" class="s3-status" :class="s3Status.status">
    <div class="status-indicator" :class="{ online: s3Status.aws_available }"></div>
    <span>{{ s3Status.aws_available ? 'AWS Connected' : 'AWS Disconnected' }}</span>
  </div>
</template>

<script setup lang="ts">
interface S3Status {
  status: string
  aws_available: boolean
  message: string
}

defineProps<{
  s3Status: S3Status
}>()
</script>

<style scoped>
.s3-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #2a2a2a;
  border-left: 3px solid #666;
  margin: 8px;
  font-size: 11px;
}

.s3-status.success {
  border-left-color: #4caf50;
  background: #1b5e20;
}

.s3-status.error {
  border-left-color: #f44336;
  background: #4a1b1b;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #666;
  flex-shrink: 0;
}

.status-indicator.online {
  background: #4caf50;
  box-shadow: 0 0 4px rgba(76, 175, 80, 0.5);
}
</style>