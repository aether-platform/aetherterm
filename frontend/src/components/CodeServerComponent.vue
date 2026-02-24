<template>
  <div class="code-server-container">
    <iframe
      :src="codeServerUrl"
      class="code-server-iframe"
      frameborder="0"
      allow="clipboard-read; clipboard-write"
    ></iframe>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'

  const props = defineProps<{
    paneId: string
    sessionId: string
  }>()

  // code-server usually runs on 8080. In this environment, we'll try to reach it.
  const codeServerUrl = computed(() => {
    // In a development environment, it might be on the same host but different port
    // For production/Docker, we might need a specific path or subdomain
    return window.location.origin.replace(window.location.port, '8080')
  })
</script>

<style scoped>
  .code-server-container {
    width: 100%;
    height: 100%;
    background-color: #1e1e1e;
    overflow: hidden;
  }

  .code-server-iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
</style>
