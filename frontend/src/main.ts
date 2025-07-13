import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'
import { useAetherTerminalStore } from './stores/aetherTerminalStore'
import { useWorkspaceStore } from './stores/workspaceStore'
import { useThemeStore } from './stores/themeStore'
import { initializeTelemetry } from './utils/telemetry'
import { logger } from './utils/logger'

// Initialize telemetry (currently disabled)
const telemetryConfig = {
  serviceName: 'aetherterm-frontend',
  environment: import.meta.env.MODE || 'development',
  enableConsole: import.meta.env.DEV
}

initializeTelemetry(telemetryConfig)


const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(vuetify)

// Initialize the store (handles socket creation internally)
const terminalStore = useAetherTerminalStore()

// Initialize workspace system
const workspaceStore = useWorkspaceStore()

// Initialize theme system
const themeStore = useThemeStore()

// Setup application initialization
const initializeApp = async () => {
  try {
    logger.info('Initializing application...')
    
    // Initialize theme system first (before any UI rendering)
    logger.info('Loading theme configuration...')
    await themeStore.loadThemeConfig()
    logger.info('Theme system initialized successfully')
    
    // Connect to service
    const connected = await terminalStore.connect()
    if (!connected) {
      logger.error('Failed to connect to terminal service')
      throw new Error('Failed to connect to terminal service')
    }
    
    // Initialize workspace system (this will resume last workspace or create default)
    await workspaceStore.initializeWorkspace()
    
    logger.info('Application initialized successfully')
  } catch (error) {
    logger.error('Failed to initialize application:', error)
    // Don't create default workspace - let the server handle it
  }
}

// Initialize after mounting
app.mount('#app')

// Initialize application after Vue is mounted
setTimeout(() => {
  initializeApp()
}, 100)
