<template>
  <div
    v-if="show"
    class="selection-context-menu"
    :style="{ top: position.y + 'px', left: position.x + 'px' }"
    @click.stop
  >
    <div class="context-menu-header">
      <span class="selected-text-preview">{{ textPreview }}</span>
      <span class="text-length">({{ selectedText.length }} chars)</span>
    </div>
    
    <div class="menu-divider"></div>
    
    <!-- Copy Text Action -->
    <button class="menu-item" @click="copyToClipboard">
      <span class="icon">📋</span>
      <span class="label">Copy Text</span>
    </button>

    <div class="menu-divider"></div>

    <!-- Ask AI Action -->
    <button class="menu-item ai-item" @click="sendToAI">
      <span class="icon">🤖</span>
      <span class="label">Ask AI</span>
    </button>
  </div>

  <!-- Backdrop -->
  <div
    v-if="show"
    class="context-menu-backdrop"
    @click="hide"
  ></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAetherTerminalStore } from '../stores/aetherTerminalStore'

interface Props {
  show: boolean
  position: { x: number; y: number }
  selectedText: string
}

interface Emits {
  (e: 'copy'): void
  (e: 'hide'): void
  (e: 'sendToAi', text: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const terminalStore = useAetherTerminalStore()

const textPreview = computed(() => {
  const text = props.selectedText.trim()
  if (text.length <= 50) return text
  return text.substring(0, 47) + '...'
})

const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(props.selectedText)
    console.log('Text copied to clipboard:', props.selectedText)
    emit('copy')
    emit('hide')
  } catch (err) {
    console.error('Failed to copy text to clipboard:', err)
    // Fallback for older browsers
    const textArea = document.createElement('textarea')
    textArea.value = props.selectedText
    document.body.appendChild(textArea)
    textArea.select()
    document.execCommand('copy')
    document.body.removeChild(textArea)
    emit('copy')
    emit('hide')
  }
}

// Send to AI in side panel
const sendToAI = () => {
  console.log('Sending text to side panel AI:', props.selectedText)
  
  // Use Spine (AetherTerminalServiceStore) to trigger Ask AI
  terminalStore.triggerAskAI(props.selectedText)
  emit('hide')
}

const hide = () => {
  emit('hide')
}
</script>

<style scoped>
.selection-context-menu {
  position: fixed;
  z-index: 1001;
  background: #2d2d2d;
  border: 1px solid #444;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  min-width: 280px;
  max-width: 320px;
  user-select: none;
  backdrop-filter: blur(10px);
  overflow: hidden;
}

.context-menu-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  background: transparent;
}

.context-menu-header {
  padding: 12px 16px;
  background: #1e1e1e;
  border-bottom: 1px solid #444;
}

.selected-text-preview {
  display: block;
  color: #e0e0e0;
  font-size: 13px;
  font-family: monospace;
  word-break: break-all;
  line-height: 1.4;
  margin-bottom: 4px;
}

.text-length {
  color: #888;
  font-size: 11px;
}

.menu-divider {
  height: 1px;
  background: #444;
  margin: 0;
}

.menu-section {
  padding: 8px 0;
}

.section-label {
  padding: 6px 16px;
  color: #aaa;
  font-size: 11px;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.menu-item {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 10px 16px;
  background: transparent;
  border: none;
  color: #ffffff;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  text-align: left;
  position: relative;
}

.menu-item:hover {
  background: #3d3d3d;
}

.menu-item:active {
  background: #4d4d4d;
}

.menu-item .icon {
  font-size: 16px;
  width: 20px;
  flex-shrink: 0;
  text-align: center;
}

.menu-item .label {
  flex: 1;
  margin-left: 12px;
  font-weight: 500;
}

.menu-item .shortcut {
  color: #888;
  font-size: 11px;
  font-family: monospace;
  margin-left: 8px;
}

/* AI-specific styling */
.ai-item:hover {
  background: linear-gradient(135deg, #4a148c, #6a1b9a);
  color: #ffffff;
}

.ai-item:hover .icon {
  transform: scale(1.1);
}

/* Cancel item styling */
.cancel-item {
  color: #ff7979;
}

.cancel-item:hover {
  background: #2d3436;
  color: #ff6b6b;
}

/* Copy actions styling */
.menu-section:first-of-type .menu-item:hover {
  background: linear-gradient(135deg, #27ae60, #2ecc71);
}

/* Search actions styling */
.menu-section:nth-of-type(3) .menu-item:hover {
  background: linear-gradient(135deg, #3498db, #74b9ff);
}

/* Hover effects */
.menu-item:hover .icon {
  transform: translateX(2px);
}

.menu-item:hover .label {
  transform: translateX(2px);
}

/* Animation */
.selection-context-menu {
  animation: contextMenuSlideIn 0.15s ease-out;
}

@keyframes contextMenuSlideIn {
  from {
    opacity: 0;
    transform: translateY(-8px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* Responsive adjustments */
@media (max-width: 600px) {
  .selection-context-menu {
    min-width: 240px;
    max-width: 280px;
  }
  
  .menu-item {
    padding: 12px 16px;
  }
  
  .menu-item .label {
    font-size: 13px;
  }
}
</style>