<template>
  <div v-if="!isAuthenticated" class="auth-status">
    <div class="status-icon">⚠️</div>
    <div class="status-text">
      <p>Authentication required</p>
      <small>Login to JupyterHub</small>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  isAuthenticated: boolean
}>()
</script>

<style scoped>
.auth-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #2a2a2a;
  border: 1px solid #444;
  border-radius: 4px;
  margin: 8px;
}

.status-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.status-text {
  flex: 1;
}

.status-text p {
  margin: 0;
  font-size: 12px;
  color: #ff9800;
  font-weight: 500;
}

.status-text small {
  color: #ccc;
  font-size: 10px;
}
</style>