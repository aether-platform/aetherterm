<template>
  <div class="confirm-overlay" @click.self="$emit('cancel')">
    <div class="confirm-dialog">
      <p class="confirm-message">{{ message }}</p>
      <div class="confirm-actions">
        <button class="btn btn-confirm" @click="$emit('confirm')">Yes (y)</button>
        <button class="btn btn-cancel" @click="$emit('cancel')">No (n)</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onUnmounted } from 'vue'

  defineProps<{
    message: string
  }>()

  const emit = defineEmits<{
    confirm: []
    cancel: []
  }>()

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'y' || e.key === 'Enter') {
      e.preventDefault()
      emit('confirm')
    } else if (e.key === 'n' || e.key === 'Escape') {
      e.preventDefault()
      emit('cancel')
    }
  }

  onMounted(() => document.addEventListener('keydown', handleKey))
  onUnmounted(() => document.removeEventListener('keydown', handleKey))
</script>

<style scoped>
  .confirm-overlay {
    position: absolute;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .confirm-dialog {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 16px 24px;
    min-width: 280px;
  }

  .confirm-message {
    margin: 0 0 16px;
    color: #f1f5f9;
    font-size: 13px;
  }

  .confirm-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .btn {
    padding: 6px 16px;
    border: 1px solid #334155;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    background: transparent;
    color: #94a3b8;
  }

  .btn-confirm {
    background: #ef4444;
    color: white;
    border-color: #ef4444;
  }

  .btn-cancel:hover {
    background: #334155;
  }
</style>
