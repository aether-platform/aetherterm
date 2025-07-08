<template>
  <!-- Logic-only component, no visual elements -->
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAetherTerminalServiceStore } from '../../stores/aetherTerminalServiceStore'
import { useTerminalTabStore } from '../../stores/terminalTabStore'

interface QueuedCommand {
  id: string
  command: string
  timestamp: Date
  executed: boolean
  tabId: string
}

interface Props {
  activeTab: any
}

const props = defineProps<Props>()

// Command queue state
const commandQueue = ref<QueuedCommand[]>([])
const isExecutingQueue = ref(false)
const terminalReady = ref(false)

// Store references
const terminalTabStore = useTerminalTabStore()
const terminalStore = useAetherTerminalServiceStore()

// Watch for terminal readiness to execute queued commands
watch(terminalReady, (isReady) => {
  if (isReady && !isExecutingQueue.value) {
    executeQueuedCommands()
  }
})

// Watch for session readiness
watch(() => terminalStore.session.id, (sessionId) => {
  if (sessionId && !terminalReady.value) {
    setTimeout(() => {
      if (!terminalReady.value) {
        terminalReady.value = true
      }
    }, 200)
  }
})

// Watch for active tab changes to handle inventory terminal initialization
watch(() => props.activeTab, (newTab, oldTab) => {
  if (newTab && newTab.id !== oldTab?.id) {
    // Reset terminal state for new tab
    terminalReady.value = false
    commandQueue.value = []
    
    // Queue commands for inventory terminals immediately
    if (newTab.subType === 'inventory' && newTab.serverContext) {
      queueInventoryCommands(newTab)
    }
  }
})

// Queue inventory commands for execution when terminal is ready
const queueInventoryCommands = (tab: typeof props.activeTab) => {
  if (!tab || tab.subType !== 'inventory' || !tab.serverContext) return
  
  // Clear existing queue for this tab
  commandQueue.value = commandQueue.value.filter(cmd => cmd.tabId !== tab.id)
  
  // Get pre-execution commands from store
  const storeCommands = terminalTabStore.getTabCommands(tab.id)
  
  // Add to local queue
  storeCommands.forEach((storeCommand) => {
    commandQueue.value.push({
      id: `${tab.id}-${storeCommand.id}`,
      command: storeCommand.command,
      timestamp: new Date(),
      executed: false,
      tabId: tab.id
    })
  })
  
  // Try to execute immediately if terminal is ready
  if (terminalReady.value) {
    executeQueuedCommands()
  }
}

// Execute all queued commands for the current tab
const executeQueuedCommands = async () => {
  if (!props.activeTab || isExecutingQueue.value) return
  
  const tabCommands = commandQueue.value.filter(
    cmd => cmd.tabId === props.activeTab!.id && !cmd.executed
  )
  
  if (tabCommands.length === 0) return
  
  isExecutingQueue.value = true
  
  try {
    // Wait for terminal session to be fully ready
    if (!terminalStore.session.id) {
      await waitForSession()
    }
    
    // Add small delay to ensure terminal is fully initialized
    await new Promise(resolve => setTimeout(resolve, 300))
    
    for (const command of tabCommands) {
      if (terminalStore.session.id) {
        await executeCommandWithDelay(command.command)
        command.executed = true
      }
    }
    
    // Mark commands as executed in the store
    if (props.activeTab.id) {
      terminalTabStore.markCommandsExecuted(props.activeTab.id)
    }
  } catch (error) {
    console.error('Error executing queued commands:', error)
  } finally {
    isExecutingQueue.value = false
    
    // Clean up executed commands
    commandQueue.value = commandQueue.value.filter(cmd => !cmd.executed)
  }
}

// Wait for terminal session to be ready
const waitForSession = (): Promise<void> => {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Terminal session timeout'))
    }, 10000) // 10 second timeout
    
    const checkSession = () => {
      if (terminalStore.session.id) {
        clearTimeout(timeout)
        resolve()
      } else {
        setTimeout(checkSession, 100)
      }
    }
    
    checkSession()
  })
}

// Execute a single command with appropriate delay
const executeCommandWithDelay = (command: string): Promise<void> => {
  return new Promise((resolve) => {
    terminalStore.sendInput(command)
    // Wait between commands to ensure proper execution
    const delay = command.includes('ssh ') ? 1000 : 300
    setTimeout(resolve, delay)
  })
}

// Computed properties for status
const getStatusClass = () => {
  if (!terminalStore.session.id) return 'connecting'
  if (isExecutingQueue.value) return 'executing'
  if (terminalReady.value) return 'ready'
  return 'waiting'
}

const getStatusText = () => {
  if (!terminalStore.session.id) return 'Connecting to terminal...'
  if (isExecutingQueue.value) return 'Executing commands...'
  if (terminalReady.value && commandQueue.value.length > 0) return 'Ready to execute'
  if (terminalReady.value) return 'Terminal ready'
  return 'Waiting for terminal...'
}

const getProgressPercentage = () => {
  if (commandQueue.value.length === 0) return 0
  const executed = commandQueue.value.filter(c => c.executed).length
  return Math.round((executed / commandQueue.value.length) * 100)
}

// Expose reactive values and functions
defineExpose({
  commandQueue,
  isExecutingQueue,
  terminalReady,
  queueInventoryCommands,
  executeQueuedCommands,
  getStatusClass,
  getStatusText,
  getProgressPercentage
})
</script>