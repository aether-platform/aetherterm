<template>
  <div :class="spinnerClasses">
    <div class="spinner-icon">{{ icon }}</div>
    <div v-if="text" class="spinner-text">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  size?: 'small' | 'medium' | 'large'
  position?: 'inline' | 'center' | 'overlay'
  icon?: string
  text?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium',
  position: 'inline',
  icon: '⏳'
})

const spinnerClasses = computed(() => [
  'loading-spinner',
  `size-${props.size}`,
  `position-${props.position}`
])
</script>

<style scoped>
.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

/* Positions */
.position-inline {
  display: inline-flex;
}

.position-center {
  justify-content: center;
  padding: 20px;
}

.position-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 10;
}

/* Sizes */
.size-small .spinner-icon {
  font-size: 12px;
}

.size-medium .spinner-icon {
  font-size: 16px;
}

.size-large .spinner-icon {
  font-size: 24px;
}

.spinner-icon {
  animation: spin 1s linear infinite;
}

.spinner-text {
  font-size: 11px;
  color: #aaa;
  text-align: center;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>