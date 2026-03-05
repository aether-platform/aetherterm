<template>
  <div v-if="copyModeStore.isActive" class="copy-mode-overlay" @keydown="handleKey">
    <div class="copy-mode-header">
      <span class="mode-label">[Copy mode]</span>
      <span v-if="copyModeStore.searchActive" class="search-bar">
        {{ copyModeStore.searchDirection === 'forward' ? '/' : '?' }}{{ copyModeStore.searchQuery }}
      </span>
      <span class="cursor-pos">
        L{{ copyModeStore.cursorLine }} C{{ copyModeStore.cursorCol }}
      </span>
      <span class="hint">q to exit, v to select, y to copy, / to search</span>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useTmuxCopyModeStore } from '../../stores/tmuxCopyModeStore'

  const copyModeStore = useTmuxCopyModeStore()

  function handleKey(e: KeyboardEvent) {
    const action = copyModeStore.handleKey(e.key)
    if (action) {
      e.preventDefault()
      e.stopPropagation()

      if (action === 'copy') {
        // In a real implementation, we'd extract the selected text
        // from the terminal scrollback buffer
        copyModeStore.exit()
      }
    }
  }
</script>

<style scoped>
  .copy-mode-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 60;
    pointer-events: none;
  }

  .copy-mode-header {
    background: rgba(99, 102, 241, 0.85);
    color: white;
    padding: 4px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .mode-label {
    font-weight: 700;
    color: #ffff00;
  }

  .search-bar {
    background: rgba(0, 0, 0, 0.3);
    padding: 1px 6px;
    border-radius: 2px;
  }

  .cursor-pos {
    opacity: 0.7;
  }

  .hint {
    margin-left: auto;
    opacity: 0.6;
    font-size: 10px;
  }
</style>
