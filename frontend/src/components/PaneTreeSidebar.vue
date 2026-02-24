<template>
  <div class="pane-tree-sidebar">
    <!-- Header -->
    <div class="sidebar-header">
      <h3>Explorer</h3>
      <button class="add-btn" @click="addNewTerminal" title="New Terminal">
        <span>+</span>
      </button>
    </div>

    <!-- Sessions Section -->
    <div class="section-title" @click="toggleSessions">
      <span class="chevron" :class="{ collapsed: sessionsCollapsed }">&#x25BE;</span>
      <span>SESSIONS</span>
    </div>

    <!-- Pane List -->
    <div v-show="!sessionsCollapsed" class="pane-list">
      <div
        v-for="pane in paneStore.paneList"
        :key="pane.id"
        class="pane-item"
        :class="{ active: pane.id === paneStore.focusedPaneId }"
        @click="focusPane(pane.id)"
        @contextmenu.prevent="showContextMenu($event, pane.id)"
      >
        <span class="pane-icon" v-html="getPaneIcon(pane.mode)"></span>
        <span class="pane-name">{{ pane.title }}</span>
        <button
          class="close-pane-btn"
          @click.stop="closePane(pane.id)"
          title="Close"
          v-if="paneStore.paneCount > 1"
        >
          &#x2715;
        </button>
      </div>
    </div>

    <!-- Actions Section -->
    <div class="split-actions">
      <button class="split-btn" @click="splitVertical" title="Split Vertical (Ctrl+Shift+\\)">
        <span>&#x2503;</span>
      </button>
      <button class="split-btn" @click="splitHorizontal" title="Split Horizontal (Ctrl+Shift+-)">
        <span>&#x2501;</span>
      </button>
    </div>

    <!-- Mode switcher -->
    <div class="mode-switcher">
      <button
        v-for="mode in ['terminal', 'code-server']"
        :key="mode"
        class="sidebar-mode-btn"
        :class="{ active: currentPaneMode === mode }"
        @click="setPaneMode(mode as any)"
      >
        {{ mode === 'code-server' ? 'IDE' : 'Shell' }}
      </button>
    </div>

    <!-- Context Menu -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
    >
      <div class="context-item" @click="contextSplitV">
        <span>Split Right</span>
        <span class="shortcut">Ctrl+Shift+\\</span>
      </div>
      <div class="context-item" @click="contextSplitH">
        <span>Split Down</span>
        <span class="shortcut">Ctrl+Shift+-</span>
      </div>
      <div class="context-divider"></div>
      <div class="context-item danger" @click="contextClose" v-if="paneStore.paneCount > 1">
        <span>Close Pane</span>
        <span class="shortcut">Ctrl+Shift+W</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
  import { usePaneStore } from '../stores/paneStore'

  const paneStore = usePaneStore()
  const sessionsCollapsed = ref(false)

  const currentPaneMode = computed(() => paneStore.focusedPane?.mode || 'terminal')

  const contextMenu = reactive({
    visible: false,
    x: 0,
    y: 0,
    paneId: '',
  })

  function getPaneIcon(mode: string): string {
    switch (mode) {
      case 'terminal':
        return '&#x1F4BB;'
      case 'code-server':
        return '&#x1F4D1;'
      case 'tmux':
        return '&#x25A3;'
      case 'pilot-chat':
        return '&#x2728;'
      default:
        return '&#x1F4BB;'
    }
  }

  function addNewTerminal() {
    paneStore.addPane()
  }

  function splitVertical() {
    paneStore.addPane('vertical')
  }

  function splitHorizontal() {
    paneStore.addPane('horizontal')
  }

  function focusPane(id: string) {
    paneStore.focusPane(id)
    hideContextMenu()
  }

  function closePane(id: string) {
    paneStore.removePane(id)
  }

  function setPaneMode(mode: 'terminal' | 'code-server') {
    if (paneStore.focusedPane) {
      paneStore.focusedPane.mode = mode
    }
  }

  function toggleSessions() {
    sessionsCollapsed.value = !sessionsCollapsed.value
  }

  // Context menu
  function showContextMenu(event: MouseEvent, paneId: string) {
    contextMenu.visible = true
    contextMenu.x = event.clientX
    contextMenu.y = event.clientY
    contextMenu.paneId = paneId
  }

  function hideContextMenu() {
    contextMenu.visible = false
  }

  function contextSplitV() {
    paneStore.focusPane(contextMenu.paneId)
    paneStore.addPane('vertical')
    hideContextMenu()
  }

  function contextSplitH() {
    paneStore.focusPane(contextMenu.paneId)
    paneStore.addPane('horizontal')
    hideContextMenu()
  }

  function contextClose() {
    paneStore.removePane(contextMenu.paneId)
    hideContextMenu()
  }

  function onDocumentClick() {
    hideContextMenu()
  }

  onMounted(() => {
    document.addEventListener('click', onDocumentClick)
  })

  onUnmounted(() => {
    document.removeEventListener('click', onDocumentClick)
  })
</script>

<style scoped>
  .pane-tree-sidebar {
    width: 200px;
    min-width: 200px;
    background-color: var(--bg-primary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    color: var(--text-muted);
    font-size: 11px;
    user-select: none;
    backdrop-filter: blur(10px);
  }

  .sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background-color: rgba(0, 0, 0, 0.1);
  }

  .sidebar-header h3 {
    margin: 0;
    font-size: 11px;
    color: var(--text-main);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }

  .add-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    width: 20px;
    height: 20px;
    cursor: pointer;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .add-btn:hover {
    color: var(--accent-color);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .section-title {
    padding: 6px 12px;
    font-size: 10px;
    font-weight: 800;
    color: var(--text-main);
    opacity: 0.6;
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    background-color: rgba(255, 255, 255, 0.02);
  }

  .section-title:hover {
    opacity: 1;
  }

  .chevron {
    transition: transform 0.2s;
    font-size: 8px;
  }

  .chevron.collapsed {
    transform: rotate(-90deg);
  }

  .pane-list {
    flex: 1;
    overflow-y: auto;
    padding: 2px 0;
  }

  .pane-item {
    display: flex;
    align-items: center;
    padding: 6px 16px;
    cursor: pointer;
    gap: 10px;
    transition: all 0.1s;
    border-left: 2px solid transparent;
  }

  .pane-item:hover {
    background-color: rgba(255, 255, 255, 0.03);
    color: var(--text-main);
  }

  .pane-item.active {
    background-color: rgba(76, 175, 80, 0.1);
    border-left: 2px solid var(--accent-color);
    color: var(--accent-color);
  }

  .pane-icon {
    font-size: 14px;
    width: 16px;
    display: flex;
    justify-content: center;
  }

  .pane-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }

  .close-pane-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 10px;
    padding: 4px;
    border-radius: 4px;
    opacity: 0;
    transition:
      opacity 0.2s,
      background-color 0.2s;
  }

  .pane-item:hover .close-pane-btn {
    opacity: 1;
  }

  .close-pane-btn:hover {
    color: #f44336;
    background-color: rgba(244, 67, 54, 0.1);
  }

  .split-actions {
    display: flex;
    gap: 2px;
    padding: 8px;
    background-color: rgba(0, 0, 0, 0.1);
    border-top: 1px solid var(--border-color);
  }

  .split-btn {
    flex: 1;
    background: none;
    border: 1px solid transparent;
    color: var(--text-muted);
    padding: 6px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 10px;
    display: flex;
    justify-content: center;
    transition: all 0.2s;
  }

  .split-btn:hover {
    background-color: rgba(255, 255, 255, 0.05);
    color: var(--text-main);
  }

  .mode-switcher {
    display: flex;
    padding: 4px;
    background-color: rgba(0, 0, 0, 0.1);
    gap: 2px;
  }

  .sidebar-mode-btn {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-muted);
    padding: 6px 2px;
    cursor: pointer;
    font-size: 10px;
    font-weight: 600;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .sidebar-mode-btn:hover {
    color: var(--text-main);
    background-color: rgba(255, 255, 255, 0.05);
  }

  .sidebar-mode-btn.active {
    background-color: var(--accent-color);
    color: white;
    filter: drop-shadow(0 0 4px var(--accent-glow));
  }

  /* Context Menu */
  .context-menu {
    position: fixed;
    background-color: var(--bg-glass);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: var(--panel-shadow);
    z-index: 9999;
    min-width: 180px;
    padding: 6px;
    backdrop-filter: blur(12px);
    animation: scale-up 0.1s ease-out;
  }

  @keyframes scale-up {
    from {
      transform: scale(0.95);
      opacity: 0;
    }
    to {
      transform: scale(1);
      opacity: 1;
    }
  }

  .context-item {
    padding: 8px 12px;
    cursor: pointer;
    font-size: 11px;
    border-radius: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--text-main);
    gap: 12px;
  }

  .context-item:hover {
    background-color: rgba(76, 175, 80, 0.15);
    color: var(--accent-color);
  }

  .context-item.danger:hover {
    background-color: rgba(244, 67, 54, 0.1);
    color: #f44336;
  }

  .shortcut {
    font-size: 9px;
    color: var(--text-muted);
    opacity: 0.6;
  }

  .context-divider {
    height: 1px;
    background-color: var(--border-color);
    margin: 4px 6px;
  }

  /* Scrollbar */
  .pane-list::-webkit-scrollbar {
    width: 4px;
  }
  .pane-list::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 10px;
  }
</style>
