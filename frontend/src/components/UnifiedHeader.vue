<template>
  <div class="unified-header">
    <div class="header-left">
      <svg class="header-logo" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2L2 7L12 12L22 7L12 2Z"
          stroke="currentColor"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <path
          d="M2 17L12 22L22 17"
          stroke="currentColor"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <path
          d="M2 12L12 17L22 12"
          stroke="currentColor"
          stroke-width="2"
          stroke-linejoin="round"
        />
      </svg>
      <span class="header-title">AetherTerm</span>
    </div>

    <div class="header-center">
      <div class="segment-control">
        <button
          class="segment-btn"
          :class="{ active: uiMode.isTmuxMode }"
          @click="uiMode.setInteractionMode('tmux')"
        >
          tmux
        </button>
        <button
          class="segment-btn"
          :class="{ active: uiMode.isPilotMode }"
          @click="uiMode.setInteractionMode('pilot')"
        >
          pilot
        </button>
      </div>
    </div>

    <div class="header-right">
      <div
        class="connection-dot"
        :class="{ connected: tmuxStore.isConnected }"
        :title="tmuxStore.isConnected ? 'Connected' : 'Disconnected'"
      ></div>

      <div class="notification-badge" v-if="messagingStore.totalUnread > 0" title="Unread messages">
        {{ messagingStore.totalUnread > 9 ? '9+' : messagingStore.totalUnread }}
      </div>

      <!-- User menu dropdown -->
      <div class="user-menu-wrap">
        <button class="user-menu-btn" @click="accountMenuOpen = !accountMenuOpen">
          <div class="user-avatar-sm">D</div>
          <span class="user-menu-label">Account</span>
          <svg
            class="user-menu-chevron"
            :class="{ open: accountMenuOpen }"
            viewBox="0 0 16 16"
            fill="none"
          >
            <path d="M4 6L8 10L12 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>

        <div v-if="accountMenuOpen" class="user-menu-overlay" @click="closeAccountMenu" />
        <div v-if="accountMenuOpen" class="user-menu-dropdown">
          <button class="user-menu-item" @click="openAccount">
            <svg viewBox="0 0 16 16" fill="none" class="menu-item-icon">
              <path d="M6 3H3V13H13V10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M9 2H14V7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M14 2L7 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            Account Details
          </button>
          <button class="user-menu-item" @click="goToSettings">
            <svg viewBox="0 0 16 16" fill="none" class="menu-item-icon">
              <path d="M8 10C9.10457 10 10 9.10457 10 8C10 6.89543 9.10457 6 8 6C6.89543 6 6 6.89543 6 8C6 9.10457 6.89543 10 8 10Z" stroke="currentColor" stroke-width="1.5" />
              <path d="M13.3 9.7C13.2 10.1 13.4 10.5 13.7 10.8L13.8 10.9C14 11.1 14.1 11.4 14.1 11.7C14.1 12 14 12.3 13.8 12.5C13.6 12.7 13.3 12.8 13 12.8C12.7 12.8 12.4 12.7 12.2 12.5L12.1 12.4C11.8 12.1 11.4 11.9 11 12C10.6 12.1 10.3 12.4 10.3 12.8V13C10.3 13.6 9.9 14 9.3 14H8.7C8.1 14 7.7 13.6 7.7 13V12.9C7.7 12.4 7.3 12.1 6.9 12C6.5 11.9 6.1 12.1 5.8 12.4L5.7 12.5C5.3 12.9 4.6 12.9 4.2 12.5C4 12.3 3.9 12 3.9 11.7C3.9 11.4 4 11.1 4.2 10.9L4.3 10.8C4.6 10.5 4.8 10.1 4.7 9.7C4.6 9.3 4.3 9 3.9 9H3.7C3.1 9 2.7 8.6 2.7 8V7.4C2.7 6.8 3.1 6.4 3.7 6.4H3.8C4.3 6.4 4.6 6 4.7 5.6C4.8 5.2 4.6 4.8 4.3 4.5L4.2 4.4C3.8 4 3.8 3.3 4.2 2.9C4.6 2.5 5.3 2.5 5.7 2.9L5.8 3C6.1 3.3 6.5 3.5 6.9 3.4C7.3 3.3 7.7 3 7.7 2.5V2.3C7.7 1.7 8.1 1.3 8.7 1.3H9.3C9.9 1.3 10.3 1.7 10.3 2.3V2.4C10.3 2.9 10.6 3.2 11 3.3C11.4 3.4 11.8 3.2 12.1 2.9L12.2 2.8C12.6 2.4 13.3 2.4 13.7 2.8C14.1 3.2 14.1 3.9 13.7 4.3L13.6 4.4C13.3 4.7 13.1 5.1 13.2 5.5C13.3 5.9 13.6 6.3 14.1 6.3H14.3C14.9 6.3 15.3 6.7 15.3 7.3V7.9C15.3 8.5 14.9 8.9 14.3 8.9H14.1C13.7 9 13.4 9.3 13.3 9.7Z" stroke="currentColor" stroke-width="1.2" />
            </svg>
            Settings
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { useRouter } from 'vue-router'
  import { useUIModeStore } from '../stores/uiModeStore'
  import { useTmuxStore } from '../stores/tmuxStore'
  import { useAgentMessagingStore } from '../stores/agentMessagingStore'

  const router = useRouter()
  const uiMode = useUIModeStore()
  const tmuxStore = useTmuxStore()
  const messagingStore = useAgentMessagingStore()

  const accountMenuOpen = ref(false)

  const closeAccountMenu = () => {
    accountMenuOpen.value = false
  }

  const openAccount = () => {
    closeAccountMenu()
    window.open('/api/account', '_blank')
  }

  const goToSettings = () => {
    closeAccountMenu()
    router.push({ name: 'Settings' })
  }
</script>

<style scoped>
  .unified-header {
    height: 36px;
    min-height: 36px;
    background-color: #0b0d11;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 14px;
    user-select: none;
    z-index: 1500;
    flex-shrink: 0;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  .header-logo {
    width: 18px;
    height: 18px;
    color: var(--accent-color);
    filter: drop-shadow(0 0 6px var(--accent-glow));
  }

  .header-title {
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.5px;
    background: linear-gradient(135deg, #fff 0%, #aaa 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .header-center {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .segment-control {
    display: flex;
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    overflow: hidden;
  }

  .segment-btn {
    background: transparent;
    border: none;
    color: var(--text-muted, #64748b);
    font-size: 11px;
    font-weight: 600;
    padding: 4px 14px;
    cursor: pointer;
    transition: all 0.2s ease;
    letter-spacing: 0.3px;
  }

  .segment-btn:hover:not(.active) {
    color: var(--text-main, #f1f5f9);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .segment-btn.active {
    background-color: var(--accent-color);
    color: #fff;
    box-shadow: 0 0 8px var(--accent-glow);
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    justify-content: flex-end;
  }

  .connection-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #f44336;
    transition: all 0.3s;
    border: 1.5px solid rgba(0, 0, 0, 0.2);
  }

  .connection-dot.connected {
    background-color: var(--accent-color);
    box-shadow: 0 0 8px var(--accent-glow);
  }

  .notification-badge {
    background-color: #ef4444;
    color: #fff;
    font-size: 9px;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
    line-height: 1;
  }

  /* User menu dropdown */
  .user-menu-wrap {
    position: relative;
  }

  .user-menu-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px 3px 3px;
    cursor: pointer;
    transition: all 0.15s;
    color: var(--text-main, #f1f5f9);
  }

  .user-menu-btn:hover {
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.1);
  }

  .user-avatar-sm {
    width: 22px;
    height: 22px;
    background-color: var(--accent-color);
    color: #fff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 800;
    box-shadow: 0 0 8px var(--accent-glow);
    flex-shrink: 0;
  }

  .user-menu-label {
    font-size: 12px;
    font-weight: 600;
    color: #ccc;
  }

  .user-menu-chevron {
    width: 12px;
    height: 12px;
    color: #666;
    transition: transform 0.2s;
    flex-shrink: 0;
  }

  .user-menu-chevron.open {
    transform: rotate(180deg);
  }

  .user-menu-overlay {
    position: fixed;
    inset: 0;
    z-index: 1999;
  }

  .user-menu-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    min-width: 180px;
    background: #1a1d24;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    z-index: 2000;
    overflow: hidden;
  }

  .user-menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 10px 14px;
    background: transparent;
    border: none;
    color: #ccc;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.12s;
    text-align: left;
  }

  .user-menu-item:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
  }

  .user-menu-item + .user-menu-item {
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  .menu-item-icon {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    color: #888;
  }

  .user-menu-item:hover .menu-item-icon {
    color: #bbb;
  }
</style>
