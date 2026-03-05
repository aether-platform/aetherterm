<template>
  <div class="settings-page">
    <button class="settings-back" @click="router.push({ name: 'Home' })">
      <svg viewBox="0 0 16 16" fill="none" class="back-icon">
        <path d="M10 12L6 8L10 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      Back
    </button>

    <h1 class="settings-title">Settings</h1>

    <div class="settings-section">
      <p class="settings-placeholder">Settings page — coming soon.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useRouter } from 'vue-router'

  const router = useRouter()
</script>

<style scoped>
  .settings-page {
    padding: 32px 40px;
    color: #e0e0e0;
    max-width: 720px;
    margin: 0 auto;
    min-height: 100%;
    overflow-y: auto;
  }

  .settings-back {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #aaa;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
    margin-bottom: 24px;
  }

  .settings-back:hover {
    background: rgba(255, 255, 255, 0.06);
    color: #ddd;
    border-color: rgba(255, 255, 255, 0.2);
  }

  .back-icon {
    width: 14px;
    height: 14px;
  }

  .settings-title {
    font-size: 24px;
    font-weight: 700;
    margin: 0 0 24px;
    color: #fff;
  }

  .settings-section {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 24px;
  }

  .settings-placeholder {
    margin: 0;
    color: #666;
    font-size: 14px;
  }
</style>
