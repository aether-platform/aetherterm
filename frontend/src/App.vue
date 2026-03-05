<script setup lang="ts">
  import 'normalize.css'
  import { computed, onMounted, onUnmounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import CommandPalette from './components/CommandPalette.vue'
  import UnifiedHeader from './components/UnifiedHeader.vue'
  import { useUIModeStore } from './stores/uiModeStore'
  import { useTmuxStore } from './stores/tmuxStore'
  import ThemeProvider from './ThemeProvider.vue'

  const route = useRoute()
  const uiModeStore = useUIModeStore()
  const tmuxStore = useTmuxStore()
  const showCommandPalette = ref(false)

  const isTmuxRoute = computed(() => route.path.startsWith('/tmux'))

  // Show header: always on non-tmux routes; on tmux route only in pilot mode
  const showHeader = computed(() => !isTmuxRoute.value || uiModeStore.isPilotMode)

  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.ctrlKey && event.key === 'p') {
      event.preventDefault()
      showCommandPalette.value = true
    }
    // Ctrl+Shift+M: toggle interaction mode
    if (event.ctrlKey && event.shiftKey && event.key === 'M') {
      event.preventDefault()
      uiModeStore.toggleInteractionMode()
    }
  }

  onMounted(() => {
    uiModeStore.loadFromStorage()
    document.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyDown)
  })
</script>

<template>
  <ThemeProvider>
    <div id="app-container">
      <UnifiedHeader v-if="showHeader" />
      <div class="app-body">
        <router-view />
      </div>

      <CommandPalette v-model:show="showCommandPalette" />

      <!-- Status Bar (hidden in tmux mode — tmux has its own) -->
      <div v-if="!isTmuxRoute" class="bottom-toolbar">
        <div class="toolbar-left">
          <span class="status-item">
            <span class="indicator" :class="tmuxStore.isConnected ? 'connected' : 'disconnected'"></span>
            {{ tmuxStore.isConnected ? 'connected' : 'disconnected' }}
          </span>
        </div>
        <div class="toolbar-center">
          <button @click="showCommandPalette = true" class="search-btn">Ctrl+P to Search</button>
        </div>
        <div class="toolbar-right">
          <span v-if="tmuxStore.activeWindow">
            {{ Object.keys(tmuxStore.activeWindow.panes).length }} Panes
          </span>
        </div>
      </div>
    </div>
  </ThemeProvider>
</template>

<style>
  :root {
    --bg-primary: #0f1117;
    --bg-secondary: #1e293b;
    --border-color: #334155;
    --accent-color: #6366f1;
    --text-main: #f1f5f9;
  }
  body {
    margin: 0;
    background: var(--bg-primary);
    color: var(--text-main);
    font-family: 'Inter', sans-serif;
    overflow: hidden;
  }
</style>

<style scoped>
  #app-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  .app-body {
    flex: 1;
    overflow: hidden;
    position: relative;
  }
  .bottom-toolbar {
    height: 24px;
    background: #000;
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    font-size: 11px;
  }
  .indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 5px;
  }
  .connected {
    background: #10b981;
  }
  .disconnected {
    background: #ef4444;
  }
  .search-btn {
    background: #1e293b;
    border: 1px solid var(--border-color);
    color: #94a3b8;
    padding: 2px 20px;
    border-radius: 4px;
    cursor: pointer;
  }
</style>
