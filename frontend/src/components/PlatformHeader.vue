<template>
  <div class="platform-header">
    <div class="platform-left">
      <div class="platform-switcher">
        <div
          class="platform-item"
          :class="{ active: currentPlatform === 'ide' }"
          @click="switchPlatform('ide')"
        >
          <span class="platform-icon">💎</span>
          <span class="platform-label">Aether IDE</span>
        </div>
        <div
          class="platform-item"
          :class="{ active: currentPlatform === 'term' }"
          @click="switchPlatform('term')"
        >
          <span class="platform-icon">⚡</span>
          <span class="platform-label">Aether Term</span>
        </div>
      </div>
    </div>
    <div class="platform-right">
      <div class="user-profile">
        <span class="user-name">Developer</span>
        <div class="user-avatar">D</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'

  const currentPlatform = ref('term') // Default for this app

  const switchPlatform = (platform: 'ide' | 'term') => {
    currentPlatform.value = platform
    if (platform === 'ide') {
      // Logic to switch to IDE (e.g., redirect or change app state)
      console.log('Switching to Aether IDE')
    }
  }
</script>

<style scoped>
  .platform-header {
    height: 36px;
    background-color: #050608;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    user-select: none;
    z-index: 1100;
  }

  .platform-left {
    display: flex;
    align-items: center;
  }

  .platform-switcher {
    display: flex;
    gap: 4px;
    background-color: rgba(255, 255, 255, 0.03);
    padding: 3px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
  }

  .platform-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    color: var(--text-muted);
  }

  .platform-item:hover {
    color: var(--text-main);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .platform-item.active {
    color: #fff;
    background-color: var(--accent-color);
    box-shadow: 0 2px 10px var(--accent-glow);
  }

  .platform-icon {
    font-size: 14px;
  }

  .platform-label {
    font-size: 11px;
    font-weight: 700;
  }

  .platform-right {
    display: flex;
    align-items: center;
  }

  .user-profile {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 8px;
    border-radius: 20px;
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-color);
  }

  .user-name {
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
  }

  .user-avatar {
    width: 20px;
    height: 20px;
    background-color: var(--accent-color);
    color: #fff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 800;
  }
</style>
