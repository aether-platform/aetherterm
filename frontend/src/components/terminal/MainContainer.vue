<template>
  <div 
    class="main-container"
    :class="[
      `theme-${themeStore.isDarkMode ? 'dark' : 'light'}`, 
      `scheme-${themeStore.themeConfig.colorScheme}`
    ]"
    @contextmenu.prevent
  >
    <!-- Tab Bar -->
    <TerminalTabBar @open-s3-browser="openS3Browser" />

    <!-- Main Content Area -->
    <MainContentView 
      :is-terminal-paused="isTerminalPaused"
      :is-supervisor-locked="isSupervisorLocked"
      @terminal-initialized="onTerminalInitialized"
    />
    
    <!-- Connection Status Overlay -->
    <ConnectionStatusBanner />

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useAetherTerminalStore } from '../../stores/aetherTerminalStore'
import { useAetherTerminalServiceStore } from '../../stores/aetherTerminalServiceStore'
import { useThemeStore } from '../../stores/themeStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import ConnectionStatusBanner from './ConnectionStatusBanner.vue'
import TerminalTabBar from '../TabBarContainer.vue'
import MainContentView from '../MainContentView.vue'

const emit = defineEmits(['open-s3-browser'])

const aetherTerminalStore = useAetherTerminalStore()
const terminalStore = useAetherTerminalServiceStore()
const themeStore = useThemeStore()
const workspaceStore = useWorkspaceStore()

// Terminal pause state
const isTerminalPaused = ref(false)

const isSupervisorLocked = computed(() => {
  return terminalStore.isSupervisorLocked
})

// Terminal pause/resume functions
const resumeTerminal = () => {
  isTerminalPaused.value = false
}

// Expose pause function globally (can be called from other components)
const pauseTerminal = () => {
  isTerminalPaused.value = true
}

const onTerminalInitialized = () => {
  console.log('Terminal initialized in container')
}

const openS3Browser = () => {
  emit('open-s3-browser')
}

onMounted(async () => {
  console.log('MainContainer mounted')
  
  // Initialize connection using aetherTerminalStore (simpler WebSocket implementation)
  await aetherTerminalStore.connect()
  
  // Then initialize workspace system (will load from localStorage and reconnect sessions)
  await workspaceStore.initializeWorkspace()
})

// Apply theme changes reactively
watchEffect(() => {
  // Theme application is handled automatically by the theme store watchers
  // This just ensures the component is reactive to theme changes
  if (themeStore.currentColors) {
    console.log('🎨 THEME: Theme applied to terminal container:', themeStore.themeConfig.colorScheme)
  }
})

// Export functions for external use
defineExpose({
  pauseTerminal,
  resumeTerminal
})
</script>

<style scoped lang="scss">
@import '../../assets/styles/base.scss';

.main-container {
  @include terminal-container;
  position: relative;
  
  // Use CSS variables for theming
  background-color: var(--terminal-background);
  color: var(--terminal-foreground);
  font-family: var(--terminal-font-family);
  font-size: var(--terminal-font-size);
  line-height: var(--terminal-line-height);
  
  // Transition for smooth theme changes
  transition: background-color 0.3s ease, color 0.3s ease;
}

// Theme-specific adjustments
.main-container.theme-dark {
  background-color: var(--terminal-background);
  color: var(--terminal-foreground);
}

.main-container.theme-light {
  background-color: var(--terminal-background);
  color: var(--terminal-foreground);
}

// Layout adjustments when sidebar is visible
.main-container.has-sidebar {
  padding-right: 320px; // Fixed width for any sidebar
  transition: padding-right 0.3s ease;
}

// Responsive adjustments
@media (max-width: 768px) {
  .main-container.has-sidebar {
    padding-right: 0; // Remove padding on mobile
  }
}
</style>