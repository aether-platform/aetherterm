<template>
  <div class="chat-first-layout">
    <!-- Main chat area -->
    <div class="chat-area">
      <SimpleChatComponent />
    </div>

    <!-- Resizable divider -->
    <div
      class="panel-divider"
      @mousedown.prevent="startDividerDrag"
    >
      <div class="divider-handle"></div>
    </div>

    <!-- Collapsible terminal panel -->
    <div class="terminal-panel" :style="panelStyle">
      <div class="panel-header" @click="uiModeStore.toggleTerminalPanel()">
        <div class="panel-header-left">
          <span class="panel-title">Terminal</span>
          <span class="session-count">{{ paneStore.paneCount }} session{{ paneStore.paneCount !== 1 ? 's' : '' }}</span>
        </div>
        <button class="panel-toggle-btn" :title="uiModeStore.isTerminalPanelCollapsed ? 'Expand' : 'Collapse'">
          <span v-if="uiModeStore.isTerminalPanelCollapsed">&#9650;</span>
          <span v-else>&#9660;</span>
        </button>
      </div>
      <div v-show="!uiModeStore.isTerminalPanelCollapsed" class="panel-content">
        <PaneLayout :node="paneStore.layout" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import SimpleChatComponent from './SimpleChatComponent.vue'
  import PaneLayout from './PaneLayout.vue'
  import { useUIModeStore } from '../stores/uiModeStore'
  import { usePaneStore } from '../stores/paneStore'

  const uiModeStore = useUIModeStore()
  const paneStore = usePaneStore()

  const panelStyle = computed(() => {
    if (uiModeStore.isTerminalPanelCollapsed) {
      return { height: '32px', minHeight: '32px' }
    }
    return {
      height: `${uiModeStore.terminalPanelHeight}px`,
      minHeight: '100px',
    }
  })

  function startDividerDrag(event: MouseEvent) {
    if (uiModeStore.isTerminalPanelCollapsed) return

    const startY = event.clientY
    const startHeight = uiModeStore.terminalPanelHeight

    const onMove = (e: MouseEvent) => {
      // Dragging up = increasing panel height
      const delta = startY - e.clientY
      uiModeStore.setTerminalPanelHeight(startHeight + delta)
    }

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'
  }
</script>

<style scoped>
  .chat-first-layout {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .chat-area {
    flex: 1;
    min-height: 200px;
    overflow: hidden;
  }

  .panel-divider {
    height: 4px;
    flex-shrink: 0;
    background-color: #333;
    cursor: row-resize;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.15s;
    z-index: 5;
  }

  .panel-divider:hover {
    background-color: #4caf50;
  }

  .divider-handle {
    width: 30px;
    height: 2px;
    background-color: #666;
    border-radius: 1px;
  }

  .panel-divider:hover .divider-handle {
    background-color: #fff;
  }

  .terminal-panel {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background-color: #1e1e1e;
    border-top: 1px solid #333;
    overflow: hidden;
  }

  .panel-header {
    height: 32px;
    min-height: 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 10px;
    background-color: #252525;
    border-bottom: 1px solid #333;
    cursor: pointer;
    user-select: none;
    flex-shrink: 0;
  }

  .panel-header:hover {
    background-color: #2a2a2a;
  }

  .panel-header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .panel-title {
    font-size: 12px;
    font-weight: 600;
    color: #ccc;
  }

  .session-count {
    font-size: 10px;
    color: #888;
    padding: 1px 6px;
    background-color: #333;
    border-radius: 3px;
  }

  .panel-toggle-btn {
    background: none;
    border: none;
    color: #888;
    font-size: 10px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 3px;
  }

  .panel-toggle-btn:hover {
    color: #fff;
    background-color: #444;
  }

  .panel-content {
    flex: 1;
    overflow: hidden;
    display: flex;
  }
</style>
