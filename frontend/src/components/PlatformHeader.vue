<template>
  <div class="platform-header">
    <div class="header-section left">
      <div class="platform-branding">
        <svg class="platform-logo" viewBox="0 0 24 24" fill="none">
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
        <span class="platform-name">Aether Platform</span>
      </div>
      <div class="vertical-divider"></div>
      <span class="current-label">{{ uiModeStore.interactionMode }}</span>
    </div>

    <div class="header-section right">
      <div class="user-profile">
        <div class="user-info">
          <span class="user-name">Developer</span>
          <span class="user-role">Premium Account</span>
        </div>
        <div class="user-avatar">D</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useUIModeStore } from '../stores/uiModeStore'

  const uiModeStore = useUIModeStore()
</script>

<style scoped>
  .platform-header {
    height: 44px;
    background-color: #0b0d11;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    user-select: none;
    z-index: 1500;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  .header-section {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .platform-branding {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-right: 4px;
  }

  .platform-logo {
    width: 20px;
    height: 20px;
    color: var(--accent-color);
    filter: drop-shadow(0 0 6px var(--accent-glow));
  }

  .platform-name {
    font-size: 13px;
    font-weight: 800;
    color: #fff;
    letter-spacing: 0.5px;
    background: linear-gradient(135deg, #fff 0%, #aaa 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .vertical-divider {
    width: 1px;
    height: 16px;
    background-color: var(--border-color);
    margin: 0 4px;
  }

  .current-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-main);
  }

  .user-profile {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 6px 4px 12px;
    border-radius: 24px;
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-color);
    transition: all 0.2s;
  }

  .user-profile:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.15);
  }

  .user-info {
    display: flex;
    flex-direction: column;
    text-align: right;
  }

  .user-name {
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    line-height: 1.2;
  }

  .user-role {
    font-size: 9px;
    color: var(--accent-color);
    font-weight: 600;
    opacity: 0.8;
  }

  .user-avatar {
    width: 24px;
    height: 24px;
    background-color: var(--accent-color);
    color: #fff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 800;
    box-shadow: 0 0 10px var(--accent-glow);
  }
</style>
