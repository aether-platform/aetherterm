<template>
  <div class="pane-numbers-overlay">
    <div
      v-for="(paneId, index) in paneIds"
      :key="paneId"
      class="pane-number"
      :class="{ active: paneId === tmuxStore.activePaneId }"
    >
      {{ index }}
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const tmuxStore = useTmuxStore()

  const paneIds = computed(() => {
    const win = tmuxStore.activeWindow
    if (!win) return []
    return Object.keys(win.panes)
  })
</script>

<style scoped>
  .pane-numbers-overlay {
    position: absolute;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    background: rgba(0, 0, 0, 0.5);
    pointer-events: none;
  }

  .pane-number {
    font-size: 48px;
    font-weight: 700;
    color: #888;
    font-family: 'JetBrains Mono', monospace;
  }

  .pane-number.active {
    color: #4caf50;
  }
</style>
