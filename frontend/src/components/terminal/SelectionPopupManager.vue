<template>
  <div style="display: none;">
    <!-- Logic-only component, no visual elements needed -->
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAetherTerminalStore } from '../../stores/aetherTerminalStore'
import { useTerminalTabStore } from '../../stores/terminalTabStore'

// Selection popup state
const showSelectionPopup = ref(false)
const popupPosition = ref({ x: 0, y: 0 })
const selectedText = ref('')

// Store references
const terminalTabStore = useTerminalTabStore()
const terminalStore = useAetherTerminalStore()

// Selection popup event handlers
const hideSelectionPopup = () => {
  showSelectionPopup.value = false
  selectedText.value = ''
}

const onCopyAction = async () => {
  const success = await copySelection()
  if (success) {
    console.log('Text copied successfully')
  } else {
    console.warn('Failed to copy text to clipboard')
  }
}

const onSendToAI = (text: string, prompt?: string) => {
  console.log('Sending text to AI:', text, 'with prompt:', prompt)
  
  // Create or switch to AI chat tab
  const aiTab = terminalTabStore.createTab('ai-agent', 'AI Analysis')
  terminalTabStore.switchToTab(aiTab.id)
  
  // Send message to AI with custom prompt or default
  const message = prompt || `Please analyze this terminal output: ${text}`
  const chatMessage = {
    type: 'user',
    message,
    timestamp: new Date(),
    source: 'terminal_selection',
    terminalOutput: text
  }
  terminalStore.sendChatMessage(chatMessage)
}

// Enhanced clipboard operations
const copySelection = async () => {
  if (selectedText.value) {
    try {
      // Use the standard clipboard API directly
      await navigator.clipboard.writeText(selectedText.value)
      console.log('Text copied to clipboard')
      return true
    } catch (error) {
      console.warn('Failed to copy to clipboard:', error)
      return false
    }
  }
  return false
}

// Expose reactive values and functions
defineExpose({
  showSelectionPopup,
  popupPosition,
  selectedText,
  hideSelectionPopup,
  onCopyAction,
  onSendToAI,
  copySelection
})
</script>