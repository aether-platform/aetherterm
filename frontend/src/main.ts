import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'
import AetherTermService from './services/AetherTermService'
import { useAetherTerminalServiceStore } from './stores/aetherTerminalServiceStore'
import { useWorkspaceStore } from './stores/workspaceStore'
import { useThemeStore } from './stores/themeStore'
import { initializeTelemetry } from './utils/telemetry'

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

// Initialize AetherTermService and connect it to the store
const aetherTermService = AetherTermService.getInstance()
const socket = aetherTermService.connect()

// Initialize the store with the socket connection
const terminalStore = useAetherTerminalServiceStore()
terminalStore.setSocket(socket)

// Initialize workspace system
const workspaceStore = useWorkspaceStore()

// Initialize theme system
const themeStore = useThemeStore()

// Setup application initialization
const initializeApp = async () => {
  try {
    console.log('🚀 APP: Initializing application...')
    
    // Initialize theme system first (before any UI rendering)
    console.log('🎨 THEME: Loading theme configuration...')
    await themeStore.loadThemeConfig()
    console.log('🎨 THEME: Theme system initialized successfully')
    
    // Connect to service
    const connected = await terminalStore.connect()
    if (!connected) {
      console.error('🚀 APP: Failed to connect to terminal service')
      throw new Error('Failed to connect to terminal service')
    }
    
    // Initialize workspace system (this will resume last workspace or create default)
    await workspaceStore.initializeWorkspace()
    
    console.log('🚀 APP: Application initialized successfully')
  } catch (error) {
    console.error('🚀 APP: Failed to initialize application:', error)
    // Don't create default workspace - let the server handle it
  }
}

// Initialize after mounting
app.mount('#app')

// Initialize application after Vue is mounted
setTimeout(() => {
  initializeApp()
}, 100)
