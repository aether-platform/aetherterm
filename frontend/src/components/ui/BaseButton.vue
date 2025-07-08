<template>
  <button 
    :class="buttonClasses" 
    :disabled="disabled"
    @click="$emit('click')"
    :title="title"
  >
    <slot></slot>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  variant?: 'primary' | 'secondary' | 'icon' | 'danger'
  size?: 'small' | 'medium' | 'large'
  disabled?: boolean
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'medium',
  disabled: false
})

defineEmits<{
  click: []
}>()

const buttonClasses = computed(() => [
  'base-button',
  `variant-${props.variant}`,
  `size-${props.size}`,
  {
    'disabled': props.disabled
  }
])
</script>

<style scoped>
.base-button {
  border: none;
  border-radius: 3px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

/* Variants */
.variant-primary {
  background: #4caf50;
  color: white;
}

.variant-primary:hover:not(.disabled) {
  background: #45a049;
  transform: translateY(-1px);
}

.variant-secondary {
  background: #2a2a2a;
  color: #ccc;
  border: 1px solid #444;
}

.variant-secondary:hover:not(.disabled) {
  background: #333;
  color: white;
  border-color: #4caf50;
}

.variant-icon {
  background: none;
  color: #ccc;
  padding: 4px;
}

.variant-icon:hover:not(.disabled) {
  background: #333;
  color: white;
}

.variant-danger {
  background: #f44336;
  color: white;
}

.variant-danger:hover:not(.disabled) {
  background: #d32f2f;
}

/* Sizes */
.size-small {
  padding: 4px 8px;
  font-size: 10px;
}

.size-medium {
  padding: 6px 12px;
  font-size: 12px;
}

.size-large {
  padding: 8px 16px;
  font-size: 14px;
}

/* Icon variant sizing */
.variant-icon.size-small {
  width: 20px;
  height: 20px;
  padding: 2px;
}

.variant-icon.size-medium {
  width: 24px;
  height: 24px;
  padding: 4px;
}

.variant-icon.size-large {
  width: 32px;
  height: 32px;
  padding: 6px;
}

/* Disabled state */
.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
}
</style>