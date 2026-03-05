<template>
  <div class="switcher-overlay" @click.self="$emit('close')">
    <div class="switcher-dialog">
      <div class="switcher-header">
        <span>Sessions & Windows</span>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="switcher-content">
        <!-- Current session windows -->
        <div v-if="tmuxStore.session" class="section">
          <div class="section-title">
            {{ tmuxStore.session.name }} (current)
          </div>
          <div
            v-for="win in tmuxStore.windowList"
            :key="win.window_id"
            class="item"
            :class="{ active: win.window_id === tmuxStore.session?.active_window_id }"
            @click="selectWindow(win.window_id)"
          >
            <span class="item-index">{{ win.window_index }}:</span>
            <span class="item-name">{{ win.name }}</span>
            <span class="item-panes">({{ Object.keys(win.panes).length }} panes)</span>
          </div>
        </div>

        <!-- Other sessions -->
        <div v-if="tmuxStore.sessionList.length > 0" class="section">
          <div class="section-title">Other Sessions</div>
          <div
            v-for="sess in otherSessions"
            :key="sess.session_id"
            class="item"
            @click="attachSession(sess.session_id)"
          >
            <span class="item-name">{{ sess.name }}</span>
            <span class="item-panes">
              ({{ Object.keys(sess.windows || {}).length }} windows)
            </span>
          </div>
          <div v-if="otherSessions.length === 0" class="empty">
            No other sessions
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const emit = defineEmits<{
    close: []
  }>()

  const tmuxStore = useTmuxStore()

  const otherSessions = computed(() => {
    return tmuxStore.sessionList.filter(
      (s) => s.session_id !== tmuxStore.session?.session_id
    )
  })

  function selectWindow(windowId: string) {
    tmuxStore.selectWindow(windowId)
    emit('close')
  }

  function attachSession(sessionId: string) {
    tmuxStore.disconnect()
    tmuxStore.connect(sessionId)
    emit('close')
  }

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Escape' || e.key === 'q') {
      e.preventDefault()
      emit('close')
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKey)
    tmuxStore.requestSessionList()
  })

  onUnmounted(() => document.removeEventListener('keydown', handleKey))
</script>

<style scoped>
  .switcher-overlay {
    position: absolute;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .switcher-dialog {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    width: 400px;
    max-height: 60%;
    display: flex;
    flex-direction: column;
  }

  .switcher-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #334155;
    font-size: 13px;
    font-weight: 600;
    color: #f1f5f9;
  }

  .close-btn {
    background: none;
    border: none;
    color: #94a3b8;
    font-size: 18px;
    cursor: pointer;
  }

  .switcher-content {
    overflow-y: auto;
    padding: 8px 0;
  }

  .section {
    margin-bottom: 8px;
  }

  .section-title {
    padding: 4px 14px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
  }

  .item {
    padding: 6px 14px;
    cursor: pointer;
    display: flex;
    gap: 6px;
    font-size: 12px;
    color: #cbd5e1;
  }

  .item:hover {
    background: #334155;
  }

  .item.active {
    background: #1e3a5f;
    color: #60a5fa;
  }

  .item-index {
    color: #64748b;
    font-family: monospace;
  }

  .item-panes {
    color: #64748b;
    margin-left: auto;
    font-size: 11px;
  }

  .empty {
    padding: 8px 14px;
    color: #475569;
    font-size: 12px;
    font-style: italic;
  }
</style>
