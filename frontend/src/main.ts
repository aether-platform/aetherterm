import { createPinia } from 'pinia'
import { createApp } from 'vue'
import VueTerm from 'vue-term'
import { register } from 'vue-advanced-chat'
import App from './App.vue'
import router from './router'
import AetherTermService from './services/AetherTermService'
import { useAetherTerminalServiceStore } from './stores/aetherTerminalServiceStore'

// Register vue-advanced-chat
register()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.component('VueTerm', VueTerm)

// Initialize AetherTermService and connect it to the store
const aetherTermService = AetherTermService.getInstance()
const socket = aetherTermService.connect()

// Initialize the store with the socket connection
const terminalStore = useAetherTerminalServiceStore()
terminalStore.setSocket(socket)

// paneStore.initialize() is called in App.vue onMounted
// Single-session auto-creation is removed; paneStore handles default pane creation

app.mount('#app')
