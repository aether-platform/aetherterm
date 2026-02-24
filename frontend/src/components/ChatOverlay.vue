<template>
  <div v-if="!isMinimized" class="chat-overlay" :style="overlayStyle" ref="overlayEl">
    <!-- Draggable header -->
    <div class="overlay-header" @mousedown.prevent="startDrag">
      <div class="header-main">
        <span class="pill-icon">&#x2728;</span>
        <span class="overlay-title">Pilot Chat</span>
      </div>
      <div class="overlay-controls">
        <button
          class="overlay-btn mode-switch"
          @click="toggleMode"
          :title="isCliMode ? 'Switch to Assistant' : 'Switch to CLI Mode'"
        >
          {{ isCliMode ? '💬' : '⌨️' }}
        </button>
        <button class="overlay-btn" @click="toggleDock" title="Dock to bottom">
          <span v-if="isDocked">&#x2197;</span>
          <span v-else>&#x2199;</span>
        </button>
        <button class="overlay-btn" @click="minimize" title="Minimize (Ctrl+Space)">
          &#x2500;
        </button>
        <button class="overlay-btn overlay-close" @click="$emit('close')" title="Close">
          &#x2715;
        </button>
      </div>
    </div>

    <!-- Resize handle (bottom-right corner) -->
    <div class="resize-handle" @mousedown.prevent="startResize"></div>

    <!-- Chat content -->
    <div class="overlay-body">
      <template v-if="!isCliMode">
        <SimpleChatComponent />
      </template>
      <template v-else>
        <div class="cli-container">
          <!-- Terminal attached to AI CLI session -->
          <TerminalComponent title="AI CLI" :pane-id="'pilot_cli_pane'" mode="pilot-chat" />
        </div>
      </template>
    </div>
  </div>

  <!-- Minimized pill -->
  <div v-else class="chat-pill" @click="restore" title="Open Pilot Chat (Ctrl+Space)">
    <div class="pill-glow"></div>
    <span class="pill-icon">&#x2728;</span>
    <span class="pill-text">Pilot Chat</span>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import SimpleChatComponent from './SimpleChatComponent.vue'
  import TerminalComponent from './TerminalComponent.vue'

  const emit = defineEmits<{
    close: []
  }>()

  const STORAGE_KEY = 'aetherterm-chat-overlay'

  // State
  const isMinimized = ref(false)
  const isDocked = ref(false)
  const isCliMode = ref(false)
  const overlayEl = ref<HTMLElement | null>(null)

  // Position and size
  const posX = ref(0)
  const posY = ref(0)
  const width = ref(420)
  const height = ref(500)

  // Drag state
  let isDragging = false
  let dragOffsetX = 0
  let dragOffsetY = 0

  // Resize state
  let isResizing = false
  let resizeStartX = 0
  let resizeStartY = 0
  let resizeStartW = 0
  let resizeStartH = 0

  const overlayStyle = computed(() => {
    if (isDocked.value) {
      return {
        position: 'fixed' as const,
        bottom: '28px',
        right: '0',
        left: '0',
        top: 'auto',
        width: '100%',
        height: `${height.value}px`,
        borderRadius: '0',
      }
    }
    return {
      position: 'fixed' as const,
      left: `${posX.value}px`,
      top: `${posY.value}px`,
      width: `${width.value}px`,
      height: `${height.value}px`,
    }
  })

  function initPosition() {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      try {
        const data = JSON.parse(saved)
        posX.value = data.x ?? 0
        posY.value = data.y ?? 0
        width.value = data.w ?? 420
        height.value = data.h ?? 500
        isDocked.value = data.docked ?? false
        isMinimized.value = data.minimized ?? false
        return
      } catch {
        // ignore
      }
    }
    // Default: bottom-right above toolbar
    posX.value = window.innerWidth - width.value - 20
    posY.value = window.innerHeight - height.value - 48
  }

  function saveState() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        x: posX.value,
        y: posY.value,
        w: width.value,
        h: height.value,
        docked: isDocked.value,
        minimized: isMinimized.value,
      })
    )
  }

  // Drag handlers
  function startDrag(e: MouseEvent) {
    if (isDocked.value) return
    isDragging = true
    dragOffsetX = e.clientX - posX.value
    dragOffsetY = e.clientY - posY.value
    document.addEventListener('mousemove', onDrag)
    document.addEventListener('mouseup', stopDrag)
  }

  function onDrag(e: MouseEvent) {
    if (!isDragging) return
    posX.value = Math.max(0, Math.min(window.innerWidth - 100, e.clientX - dragOffsetX))
    posY.value = Math.max(0, Math.min(window.innerHeight - 50, e.clientY - dragOffsetY))
  }

  function stopDrag() {
    isDragging = false
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)
    saveState()
  }

  // Resize handlers
  function startResize(e: MouseEvent) {
    isResizing = true
    resizeStartX = e.clientX
    resizeStartY = e.clientY
    resizeStartW = width.value
    resizeStartH = height.value
    document.addEventListener('mousemove', onResize)
    document.addEventListener('mouseup', stopResize)
  }

  function onResize(e: MouseEvent) {
    if (!isResizing) return
    const dw = e.clientX - resizeStartX
    const dh = e.clientY - resizeStartY
    width.value = Math.max(320, resizeStartW + dw)
    height.value = Math.max(250, resizeStartH + dh)
  }

  function stopResize() {
    isResizing = false
    document.removeEventListener('mousemove', onResize)
    document.removeEventListener('mouseup', stopResize)
    saveState()
  }

  function minimize() {
    isMinimized.value = true
    saveState()
  }

  function restore() {
    isMinimized.value = false
    saveState()
  }

  function toggleDock() {
    isDocked.value = !isDocked.value
    if (isDocked.value) {
      height.value = Math.min(height.value, 350)
    }
    saveState()
  }

  function toggleMode() {
    isCliMode.value = !isCliMode.value
    saveState()
  }

  // Public method for parent to toggle
  function toggle() {
    if (isMinimized.value) {
      restore()
    } else {
      minimize()
    }
  }

  defineExpose({ toggle, isMinimized })

  onMounted(() => {
    initPosition()
  })
</script>

<style scoped>
  .chat-overlay {
    position: fixed;
    z-index: 900;
    display: flex;
    flex-direction: column;
    background: var(--bg-glass);
    backdrop-filter: blur(20px);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: var(--panel-shadow);
    overflow: hidden;
    transition:
      transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
      opacity 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: scale-up 0.3s cubic-bezier(0.4, 0, 0.2, 1);
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

  .overlay-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    background: rgba(0, 0, 0, 0.2);
    cursor: grab;
    user-select: none;
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .overlay-header:active {
    cursor: grabbing;
  }

  .overlay-title {
    font-size: 11px;
    font-weight: 800;
    color: var(--text-main);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .header-main {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .overlay-controls {
    display: flex;
    gap: 6px;
  }

  .overlay-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 12px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .overlay-btn:hover {
    color: var(--text-main);
    background: rgba(255, 255, 255, 0.05);
  }

  .overlay-close:hover {
    color: #f44336;
    background: rgba(244, 67, 54, 0.1);
  }

  .overlay-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  /* Make inner chat fill the overlay body */
  .overlay-body :deep(.simple-chat-container) {
    background: transparent;
  }

  .overlay-body :deep(.chat-header) {
    padding: 10px 14px;
    background: transparent;
    border-bottom: 1px solid var(--border-color);
  }

  .overlay-body :deep(.chat-header h3) {
    font-size: 12px;
    font-weight: 700;
  }

  .overlay-body :deep(.chat-input) {
    padding: 12px;
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid var(--border-color);
  }

  .overlay-body :deep(.message-input) {
    min-height: 44px;
    max-height: 100px;
    font-size: 13px;
    padding: 10px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-color);
    color: var(--text-main);
    font-family: var(--font-family);
  }

  .cli-container {
    height: 100%;
    background: #000;
  }

  .resize-handle {
    position: absolute;
    bottom: 0;
    right: 0;
    width: 20px;
    height: 20px;
    cursor: se-resize;
    z-index: 10;
  }

  .resize-handle::after {
    content: '';
    position: absolute;
    bottom: 4px;
    right: 4px;
    width: 10px;
    height: 10px;
    border-right: 2px solid var(--border-color);
    border-bottom: 2px solid var(--border-color);
    border-radius: 0 0 2px 0;
  }

  .chat-pill {
    position: fixed;
    bottom: 32px;
    right: 20px;
    z-index: 900;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 22px;
    background: var(--bg-glass);
    backdrop-filter: blur(24px);
    border: 1px solid var(--accent-color);
    border-radius: 30px;
    cursor: pointer;
    color: var(--accent-color);
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    box-shadow:
      0 10px 30px rgba(0, 0, 0, 0.6),
      0 0 15px var(--accent-glow);
    transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    user-select: none;
    overflow: hidden;
  }

  .chat-pill:hover {
    background: rgba(40, 43, 50, 0.9);
    transform: translateY(-4px) scale(1.05);
    box-shadow:
      0 15px 40px rgba(0, 0, 0, 0.7),
      0 0 25px var(--accent-glow);
  }

  .pill-glow {
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    animation: glow-swipe 3s infinite;
  }

  @keyframes glow-swipe {
    0% {
      left: -100%;
    }
    25% {
      left: 150%;
    }
    100% {
      left: 151%;
    }
  }

  .pill-icon {
    font-size: 14px;
    filter: drop-shadow(0 0 4px var(--accent-glow));
    animation: pulse 2s infinite ease-in-out;
  }

  @keyframes pulse {
    0%,
    100% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.2);
      opacity: 0.8;
    }
  }
</style>
