<template>
  <div class="tmux-container" tabindex="0" @keydown="handleKeyDown">
    <!-- Prefix indicator -->
    <TmuxPrefixIndicator v-if="keybindingStore.isPrefixActive" />

    <!-- Pane numbers overlay -->
    <TmuxPaneNumbers v-if="keybindingStore.showPaneNumbers" />

    <!-- Main content area -->
    <div class="tmux-main">
      <template v-if="tmuxStore.session && activeWindow">
        <!-- Zoomed pane -->
        <template v-if="tmuxStore.zoomedPaneId">
          <TmuxPane :pane-id="tmuxStore.zoomedPaneId" />
        </template>

        <!-- Normal layout -->
        <template v-else>
          <TmuxPaneLayout :layout="activeWindow.layout" />
        </template>
      </template>

      <div v-else class="tmux-loading">
        <span v-if="tmuxStore.isConnected">Loading session...</span>
        <span v-else>Connecting...</span>
      </div>
    </div>

    <!-- Status bar -->
    <TmuxStatusBar />

    <!-- Session switcher -->
    <TmuxSessionSwitcher
      v-if="showSessionSwitcher"
      @close="showSessionSwitcher = false"
    />

    <!-- Rename dialog -->
    <TmuxRenameDialog
      v-if="renameTarget"
      :target="renameTarget"
      @close="renameTarget = null"
    />

    <!-- Command line -->
    <TmuxCommandLine
      v-if="keybindingStore.showCommandLine"
      @close="keybindingStore.showCommandLine = false"
    />

    <!-- Confirm dialog -->
    <TmuxConfirmDialog
      v-if="confirmAction"
      :message="confirmAction.message"
      @confirm="confirmAction.onConfirm(); confirmAction = null"
      @cancel="confirmAction = null"
    />

    <!-- Copy mode overlay -->
    <TmuxCopyMode v-if="copyModeStore.isActive" />

    <!-- Agent notification toasts -->
    <AgentNotificationToast />
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useTmuxCopyModeStore } from '../../stores/tmuxCopyModeStore'
  import { useTmuxKeybindingStore } from '../../stores/tmuxKeybindingStore'
  import { useTmuxStore } from '../../stores/tmuxStore'
  import { useUIModeStore } from '../../stores/uiModeStore'
  import AgentNotificationToast from './AgentNotificationToast.vue'
  import TmuxCommandLine from './TmuxCommandLine.vue'
  import TmuxConfirmDialog from './TmuxConfirmDialog.vue'
  import TmuxCopyMode from './TmuxCopyMode.vue'
  import TmuxPane from './TmuxPane.vue'
  import TmuxPaneLayout from './TmuxPaneLayout.vue'
  import TmuxPaneNumbers from './TmuxPaneNumbers.vue'
  import TmuxPrefixIndicator from './TmuxPrefixIndicator.vue'
  import TmuxRenameDialog from './TmuxRenameDialog.vue'
  import TmuxSessionSwitcher from './TmuxSessionSwitcher.vue'
  import TmuxStatusBar from './TmuxStatusBar.vue'

  const tmuxStore = useTmuxStore()
  const keybindingStore = useTmuxKeybindingStore()
  const copyModeStore = useTmuxCopyModeStore()
  const uiModeStore = useUIModeStore()
  const route = useRoute()
  const router = useRouter()

  const showSessionSwitcher = ref(false)
  const renameTarget = ref<{ type: 'session' | 'window'; id: string; name: string } | null>(null)
  const confirmAction = ref<{ message: string; onConfirm: () => void } | null>(null)

  const activeWindow = computed(() => tmuxStore.activeWindow)

  function handleKeyDown(e: KeyboardEvent) {
    const action = keybindingStore.handleKey(e)
    if (!action) return

    e.preventDefault()
    e.stopPropagation()

    switch (action.type) {
      case 'split_v':
        tmuxStore.splitPane('v')
        break
      case 'split_h':
        tmuxStore.splitPane('h')
        break
      case 'close_pane':
        if (tmuxStore.activePaneId) {
          confirmAction.value = {
            message: 'Close this pane?',
            onConfirm: () => tmuxStore.closePane(tmuxStore.activePaneId),
          }
        }
        break
      case 'next_pane': {
        const win = tmuxStore.activeWindow
        if (win) {
          const paneIds = Object.keys(win.panes)
          const idx = paneIds.indexOf(win.active_pane_id)
          const nextId = paneIds[(idx + 1) % paneIds.length]
          tmuxStore.focusPane(nextId)
        }
        break
      }
      case 'focus_up':
      case 'focus_down':
      case 'focus_left':
      case 'focus_right': {
        // Simple: cycle through panes
        const win = tmuxStore.activeWindow
        if (win) {
          const paneIds = Object.keys(win.panes)
          const idx = paneIds.indexOf(win.active_pane_id)
          const dir = action.type.includes('up') || action.type.includes('left') ? -1 : 1
          const nextId = paneIds[(idx + dir + paneIds.length) % paneIds.length]
          tmuxStore.focusPane(nextId)
        }
        break
      }
      case 'zoom':
        if (tmuxStore.activePaneId) {
          tmuxStore.toggleZoom(tmuxStore.activePaneId)
        }
        break
      case 'new_window':
        tmuxStore.createWindow()
        break
      case 'next_window': {
        const wins = tmuxStore.windowList
        if (wins.length > 1) {
          const idx = wins.findIndex((w) => w.window_id === tmuxStore.session?.active_window_id)
          tmuxStore.selectWindow(wins[(idx + 1) % wins.length].window_id)
        }
        break
      }
      case 'prev_window': {
        const wins = tmuxStore.windowList
        if (wins.length > 1) {
          const idx = wins.findIndex((w) => w.window_id === tmuxStore.session?.active_window_id)
          tmuxStore.selectWindow(wins[(idx - 1 + wins.length) % wins.length].window_id)
        }
        break
      }
      case 'select_window':
        if (action.index !== undefined) {
          const wins = tmuxStore.windowList
          const win = wins.find((w) => w.window_index === action.index)
          if (win) tmuxStore.selectWindow(win.window_id)
        }
        break
      case 'copy_mode':
        if (tmuxStore.activePaneId) {
          copyModeStore.enter(tmuxStore.activePaneId)
        }
        break
      case 'detach':
        tmuxStore.detach()
        router.push('/')
        break
      case 'session_list':
        tmuxStore.requestSessionList()
        showSessionSwitcher.value = true
        break
      case 'window_list':
        showSessionSwitcher.value = true
        break
      case 'show_pane_numbers':
        keybindingStore.showPaneNumbers = true
        setTimeout(() => {
          keybindingStore.showPaneNumbers = false
        }, 2000)
        break
      case 'resize_up':
      case 'resize_down':
      case 'resize_left':
      case 'resize_right': {
        const delta = action.type.includes('up') || action.type.includes('left') ? -0.05 : 0.05
        if (tmuxStore.activePaneId) {
          tmuxStore.resizeLayout(tmuxStore.activePaneId, delta)
        }
        break
      }
      case 'command_line':
        keybindingStore.showCommandLine = true
        break
      case 'rename_window': {
        const win = tmuxStore.activeWindow
        if (win) {
          renameTarget.value = { type: 'window', id: win.window_id, name: win.name }
        }
        break
      }
      case 'rename_session':
        if (tmuxStore.session) {
          renameTarget.value = {
            type: 'session',
            id: tmuxStore.session.session_id,
            name: tmuxStore.session.name,
          }
        }
        break
      case 'toggle_mode':
        uiModeStore.toggleInteractionMode()
        break
      case 'toggle_sidebar':
        uiModeStore.toggleSidebar()
        break
      case 'show_agents':
        uiModeStore.setInteractionMode('pilot')
        uiModeStore.setSidebarTab('agents')
        break
      case 'show_tasks':
        uiModeStore.setInteractionMode('pilot')
        uiModeStore.setSidebarTab('tasks')
        break
    }
  }

  onMounted(() => {
    const sessionParam = route.params.session as string | undefined
    tmuxStore.connect(sessionParam || '_new')
  })

  onUnmounted(() => {
    tmuxStore.disconnect()
  })
</script>

<style scoped>
  .tmux-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
    background: #1e1e1e;
    outline: none;
    position: relative;
  }

  .tmux-main {
    flex: 1;
    overflow: hidden;
    position: relative;
  }

  .tmux-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #666;
    font-size: 14px;
  }
</style>
