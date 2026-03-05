<template>
  <div class="cmdline-bar">
    <span class="cmdline-prompt">:</span>
    <input
      ref="inputEl"
      v-model="command"
      class="cmdline-input"
      @keydown.enter="executeCommand"
      @keydown.escape="$emit('close')"
    />
  </div>
</template>

<script setup lang="ts">
  import { onMounted, ref } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const emit = defineEmits<{
    close: []
  }>()

  const tmuxStore = useTmuxStore()
  const command = ref('')
  const inputEl = ref<HTMLInputElement | null>(null)

  function executeCommand() {
    const cmd = command.value.trim()
    if (!cmd) {
      emit('close')
      return
    }

    const parts = cmd.split(/\s+/)
    const action = parts[0]

    switch (action) {
      case 'split-window':
        if (parts.includes('-h')) {
          tmuxStore.splitPane('h')
        } else {
          tmuxStore.splitPane('v')
        }
        break
      case 'new-window':
        tmuxStore.createWindow(parts[1])
        break
      case 'kill-pane':
        if (tmuxStore.activePaneId) {
          tmuxStore.closePane(tmuxStore.activePaneId)
        }
        break
      case 'kill-window':
        if (tmuxStore.activeWindow) {
          tmuxStore.closeWindow(tmuxStore.activeWindow.window_id)
        }
        break
      case 'select-layout':
        if (parts[1]) {
          tmuxStore.applyPresetLayout(parts[1])
        }
        break
      case 'rename-window':
        if (parts[1] && tmuxStore.activeWindow) {
          tmuxStore.renameWindow(tmuxStore.activeWindow.window_id, parts[1])
        }
        break
      case 'rename-session':
        if (parts[1]) {
          tmuxStore.renameSession(parts[1])
        }
        break
      case 'detach':
      case 'detach-client':
        tmuxStore.detach()
        break
      default:
        // Unknown command
        break
    }

    emit('close')
  }

  onMounted(() => {
    inputEl.value?.focus()
  })
</script>

<style scoped>
  .cmdline-bar {
    position: absolute;
    bottom: 22px;
    left: 0;
    right: 0;
    height: 22px;
    background: #005f00;
    color: #ffffff;
    display: flex;
    align-items: center;
    padding: 0 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    z-index: 100;
  }

  .cmdline-prompt {
    color: #ffff00;
    margin-right: 4px;
    font-weight: 700;
  }

  .cmdline-input {
    flex: 1;
    background: transparent;
    border: none;
    color: #ffffff;
    font-family: inherit;
    font-size: inherit;
    outline: none;
    padding: 0;
  }
</style>
