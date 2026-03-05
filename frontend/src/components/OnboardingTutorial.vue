<template>
  <div class="onboarding-overlay">
    <div class="onboarding-card">
      <h1 class="onboarding-title">Welcome to AetherTerm</h1>
      <p class="onboarding-subtitle">Choose your preferred interaction mode</p>

      <div class="selection-section">
        <h3 class="section-title">Select Mode</h3>
        <div class="mode-options">
          <div
            class="mode-card"
            :class="{ selected: selectedMode === 'tmux' }"
            @click="selectedMode = 'tmux'"
          >
            <div class="mode-preview">
              <div class="preview-terminal">
                <div class="preview-row">
                  <span class="preview-pane">$ ls -la</span>
                  <span class="preview-divider"></span>
                  <span class="preview-pane">$ top</span>
                </div>
              </div>
            </div>
            <div class="mode-label">tmux Mode</div>
            <div class="mode-desc">Full terminal with keyboard-driven tmux controls</div>
          </div>

          <div
            class="mode-card"
            :class="{ selected: selectedMode === 'pilot' }"
            @click="selectedMode = 'pilot'"
          >
            <div class="mode-preview">
              <div class="preview-chat">
                <div class="preview-msg preview-msg-user">npm test in pane 2</div>
                <div class="preview-msg preview-msg-ai">Running npm test...</div>
                <div class="preview-cmd">[Agents] [Tasks] [Chat]</div>
              </div>
            </div>
            <div class="mode-label">Pilot Mode</div>
            <div class="mode-desc">Terminal with AI sidebar for agents, tasks, and chat</div>
          </div>
        </div>
      </div>

      <p class="onboarding-hint">You can switch modes anytime with Ctrl+Shift+M</p>

      <button class="get-started-btn" :disabled="!selectedMode" @click="start">
        Get Started
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { useUIModeStore, type InteractionMode } from '../stores/uiModeStore'

  const uiModeStore = useUIModeStore()
  const selectedMode = ref<InteractionMode>('tmux')

  const start = () => {
    if (selectedMode.value) {
      uiModeStore.setInteractionMode(selectedMode.value)
    }
  }
</script>

<style scoped>
  .onboarding-overlay {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(8px);
  }

  .onboarding-card {
    max-width: 700px;
    width: 95%;
    padding: 40px;
    background: #1e1e1e;
    border: 1px solid #444;
    border-radius: 20px;
    text-align: center;
    box-shadow: 0 16px 64px rgba(0, 0, 0, 0.6);
  }

  .selection-section {
    margin-bottom: 32px;
    text-align: left;
  }

  .section-title {
    font-size: 14px;
    font-weight: 800;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 16px;
    padding-left: 4px;
  }

  .onboarding-title {
    margin: 0 0 8px;
    font-size: 24px;
    font-weight: 700;
    color: #4caf50;
  }

  .onboarding-subtitle {
    margin: 0 0 32px;
    font-size: 15px;
    color: #aaa;
  }

  .mode-options {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
  }

  .mode-card {
    flex: 1;
    padding: 16px;
    border: 2px solid #333;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    background: #252525;
  }

  .mode-card:hover {
    border-color: #555;
    background: #2a2a2a;
  }

  .mode-card.selected {
    border-color: #4caf50;
    background: rgba(76, 175, 80, 0.08);
  }

  .mode-preview {
    height: 80px;
    margin-bottom: 12px;
    border-radius: 6px;
    overflow: hidden;
    background: #1a1a1a;
    border: 1px solid #333;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
  }

  .preview-terminal {
    width: 100%;
  }

  .preview-row {
    display: flex;
    gap: 2px;
    height: 100%;
  }

  .preview-pane {
    flex: 1;
    font-family: monospace;
    font-size: 10px;
    color: #4caf50;
    padding: 4px;
    background: #111;
    border-radius: 2px;
  }

  .preview-divider {
    width: 2px;
    background: #444;
  }

  .preview-chat {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 9px;
  }

  .preview-msg {
    padding: 3px 6px;
    border-radius: 4px;
  }

  .preview-msg-user {
    background: #333;
    color: #ccc;
    align-self: flex-end;
  }

  .preview-msg-ai {
    background: #1565c0;
    color: #e0e0e0;
    align-self: flex-start;
  }

  .preview-cmd {
    font-family: monospace;
    font-size: 9px;
    color: #a855f7;
    background: #111;
    padding: 3px 6px;
    border-radius: 3px;
    align-self: flex-start;
  }

  .mode-label {
    font-size: 15px;
    font-weight: 700;
    color: #e0e0e0;
    margin-bottom: 4px;
  }

  .mode-desc {
    font-size: 12px;
    color: #888;
    line-height: 1.4;
  }

  .onboarding-hint {
    font-size: 12px;
    color: #666;
    margin-bottom: 24px;
  }

  .get-started-btn {
    padding: 12px 40px;
    border: none;
    border-radius: 8px;
    background-color: #4caf50;
    color: #fff;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }

  .get-started-btn:hover:not(:disabled) {
    background-color: #45a049;
    transform: translateY(-1px);
  }

  .get-started-btn:disabled {
    background-color: #555;
    color: #888;
    cursor: not-allowed;
    transform: none;
  }

  @media (max-width: 500px) {
    .mode-options {
      flex-direction: column;
    }

    .onboarding-card {
      padding: 24px;
    }
  }
</style>
