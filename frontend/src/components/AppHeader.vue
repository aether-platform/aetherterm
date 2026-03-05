<template>
  <div class="app-header">
    <div class="header-left">
      <div class="session-info" v-if="focusedPane">
        <span class="session-name">{{ focusedPane.title }}</span>
        <span class="session-mode">{{ focusedPane.mode || focusedPane.status }}</span>
      </div>
    </div>

    <div class="header-nav">
      <router-link
        to="/tmux"
        class="nav-item"
        :class="{ active: route.path.startsWith('/tmux') }"
      >
        AetherTerm
      </router-link>
      <router-link
        to="/term/control"
        class="nav-item"
        :class="{ active: route.path === '/term/control' }"
      >
        Control Center
      </router-link>
    </div>

    <div class="header-center">
      <div class="search-bar">
        <span class="search-icon">&#x2315;</span>
        <span class="search-text">{{ currentProjectName }} — AetherTerm</span>
      </div>
    </div>

    <div class="header-right">
      <div class="divider"></div>
      <slot name="actions"></slot>
      <div
        class="connection-indicator"
        :class="{ connected: isConnected }"
        :title="isConnected ? 'Connected' : 'Disconnected'"
      >
        <span class="indicator-dot"></span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useTmuxStore } from '../stores/tmuxStore'

  const route = useRoute()
  const tmuxStore = useTmuxStore()

  const isConnected = computed(() => tmuxStore.isConnected)
  const focusedPane = computed(() => tmuxStore.activePane)
  const currentProjectName = ref('vibecoding-platform')
</script>

<style scoped>
  .app-header {
    height: 30px;
    min-height: 30px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 12px;
    background-color: transparent;
    border-bottom: 1px solid var(--border-color);
    z-index: 1000;
    flex-shrink: 0;
    color: var(--text-muted);
    font-size: 11px;
    user-select: none;
    backdrop-filter: blur(8px);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
    flex: 1;
  }

  .app-logo-container {
    display: flex;
    align-items: center;
    gap: 8px;
    opacity: 0.9;
    transition: opacity 0.2s;
  }

  .app-logo-container:hover {
    opacity: 1;
  }

  .logo-svg {
    width: 16px;
    height: 16px;
    filter: drop-shadow(0 0 4px var(--accent-glow));
  }

  .app-logo {
    font-size: 12px;
    font-weight: 700;
    color: var(--text-main);
    letter-spacing: 0.5px;
  }

  .divider {
    width: 1px;
    height: 14px;
    background-color: var(--border-color);
  }

  .session-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .session-name {
    color: var(--accent-color);
    font-weight: 600;
  }

  .session-mode {
    background-color: rgba(255, 255, 255, 0.05);
    padding: 2px 6px;
    border-radius: 4px;
    color: var(--text-muted);
    font-size: 9px;
    text-transform: uppercase;
    border: 1px solid var(--border-color);
  }

  .header-center {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1.5;
  }

  .search-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    height: 22px;
    width: 100%;
    max-width: 400px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .search-bar:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
  }

  .search-icon {
    font-size: 10px;
    color: var(--text-muted);
  }

  .search-text {
    color: var(--text-muted);
    font-size: 11px;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    justify-content: flex-end;
    flex: 1;
  }

  .mode-actions {
    display: flex;
    gap: 4px;
  }

  .mode-btn {
    background: none;
    border: 1px solid transparent;
    color: var(--text-muted);
    font-size: 10px;
    padding: 2px 8px;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .mode-btn:hover {
    color: var(--text-main);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .mode-btn.active {
    color: var(--accent-color);
    background-color: rgba(76, 175, 80, 0.1);
    border-color: rgba(76, 175, 80, 0.2);
    font-weight: 600;
  }

  .connection-indicator {
    display: flex;
    align-items: center;
    padding: 4px;
    border-radius: 4px;
    transition: background-color 0.2s;
  }

  .indicator-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #f44336;
    transition: all 0.3s;
    border: 1.5px solid rgba(0, 0, 0, 0.2);
  }

  .connection-indicator.connected .indicator-dot {
    background-color: var(--accent-color);
    box-shadow: 0 0 8px var(--accent-glow);
  }
</style>
