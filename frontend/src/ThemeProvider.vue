<template>
  <slot></slot>
</template>

<script setup lang="ts">
  import { onMounted } from 'vue'

  // For now, this just ensures the theme variables are available globally.
  // Later we can add dynamic theme switching (Dark/Light/High Contrast).
  onMounted(() => {
    document.documentElement.setAttribute('data-theme', 'dark')
  })
</script>

<style>
  @import './assets/theme.css';
</style>
