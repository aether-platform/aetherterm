<template>
  <v-container fluid class="pa-4">
    <v-card elevation="2" class="mb-4">
      <v-card-title>Workspace Session Debug Tool</v-card-title>
      <v-card-subtitle>Check if sessions are shared across browser windows</v-card-subtitle>
      
      <v-card-text>
        <v-row>
          <v-col cols="12" md="6">
            <div class="text-h6 mb-2">Window Information</div>
            <v-simple-table dense>
              <tbody>
                <tr>
                  <td>Window ID (generated)</td>
                  <td class="font-weight-bold">{{ windowId }}</td>
                </tr>
                <tr>
                  <td>Socket ID</td>
                  <td class="font-weight-bold">{{ socketId || 'Not connected' }}</td>
                </tr>
                <tr>
                  <td>Socket Connected</td>
                  <td>
                    <v-chip :color="isConnected ? 'success' : 'error'" small>
                      {{ isConnected ? 'Connected' : 'Disconnected' }}
                    </v-chip>
                  </td>
                </tr>
              </tbody>
            </v-simple-table>
          </v-col>
          
          <v-col cols="12" md="6">
            <div class="text-h6 mb-2">Current Workspace</div>
            <v-simple-table dense>
              <tbody>
                <tr>
                  <td>Workspace ID</td>
                  <td class="font-weight-bold">{{ currentWorkspace?.id || 'None' }}</td>
                </tr>
                <tr>
                  <td>Workspace Name</td>
                  <td>{{ currentWorkspace?.name || 'N/A' }}</td>
                </tr>
                <tr>
                  <td>Tab Count</td>
                  <td>{{ currentWorkspace?.tabs?.length || 0 }}</td>
                </tr>
                <tr>
                  <td>Last Accessed</td>
                  <td>{{ formatDate(currentWorkspace?.lastAccessed) }}</td>
                </tr>
              </tbody>
            </v-simple-table>
          </v-col>
        </v-row>

        <v-divider class="my-4"></v-divider>

        <div class="text-h6 mb-2">LocalStorage Data</div>
        <v-expansion-panels class="mb-4">
          <v-expansion-panel>
            <v-expansion-panel-header>
              Workspace List ({{ localStorageData.workspaceIds?.length || 0 }} workspaces)
            </v-expansion-panel-header>
            <v-expansion-panel-content>
              <pre class="overflow-auto">{{ JSON.stringify(localStorageData.workspaceIds, null, 2) }}</pre>
            </v-expansion-panel-content>
          </v-expansion-panel>
          
          <v-expansion-panel>
            <v-expansion-panel-header>
              Current Workspace ID
            </v-expansion-panel-header>
            <v-expansion-panel-content>
              <pre>{{ localStorageData.currentWorkspaceId || 'None' }}</pre>
            </v-expansion-panel-content>
          </v-expansion-panel>
          
          <v-expansion-panel>
            <v-expansion-panel-header>
              Workspace Details
            </v-expansion-panel-header>
            <v-expansion-panel-content>
              <pre class="overflow-auto">{{ JSON.stringify(localStorageData.workspaceDetails, null, 2) }}</pre>
            </v-expansion-panel-content>
          </v-expansion-panel>
        </v-expansion-panels>

        <div class="text-h6 mb-2">Active Sessions</div>
        <v-data-table
          :headers="sessionHeaders"
          :items="activeSessions"
          dense
          class="elevation-1 mb-4"
        >
          <template v-slot:item.createdAt="{ item }">
            {{ formatDate(item.createdAt) }}
          </template>
        </v-data-table>

        <div class="text-h6 mb-2">Cross-Tab Sync Messages</div>
        <v-card outlined class="pa-2 mb-4" style="max-height: 200px; overflow-y: auto;">
          <div v-for="(msg, idx) in syncMessages" :key="idx" class="mb-1">
            <v-chip x-small :color="msg.fromThisWindow ? 'primary' : 'secondary'" class="mr-2">
              {{ msg.type }}
            </v-chip>
            <span class="text-caption">{{ formatTimestamp(msg.timestamp) }}</span>
            <span v-if="msg.workspaceId" class="ml-2 text-caption">ID: {{ msg.workspaceId }}</span>
          </div>
          <div v-if="syncMessages.length === 0" class="text-caption text--secondary">
            No cross-tab messages yet. Open another window to test.
          </div>
        </v-card>

        <v-divider class="my-4"></v-divider>

        <div class="text-h6 mb-2">Development Auth Settings</div>
        <v-card outlined class="pa-3 mb-4">
          <div class="text-subtitle-2 mb-2">Simulate User Roles (Development Only)</div>
          <v-row align="center">
            <v-col cols="auto">
              <v-chip-group v-model="selectedRole" mandatory>
                <v-chip value="Anonymous" small color="grey">Anonymous</v-chip>
                <v-chip value="Viewer" small color="info">Viewer</v-chip>
                <v-chip value="Owner" small color="primary">Owner</v-chip>
                <v-chip value="Supervisor" small color="warning">Supervisor</v-chip>
              </v-chip-group>
            </v-col>
            <v-col cols="auto">
              <v-btn color="primary" small @click="applyRole">
                Apply Role
              </v-btn>
            </v-col>
            <v-col cols="auto">
              <v-btn color="secondary" small @click="clearRole">
                Clear Auth
              </v-btn>
            </v-col>
          </v-row>
          <v-alert type="info" class="mt-2" dense outlined>
            Current: {{ getCurrentAuthStatus() }}
          </v-alert>
        </v-card>

        <v-divider class="my-4"></v-divider>

        <div class="text-h6 mb-2">Actions</div>
        <v-row>
          <v-col cols="auto">
            <v-btn color="primary" @click="refreshData" :loading="loading">
              <v-icon left>mdi-refresh</v-icon>
              Refresh Data
            </v-btn>
          </v-col>
          <v-col cols="auto">
            <v-btn color="secondary" @click="createTestWorkspace">
              <v-icon left>mdi-plus</v-icon>
              Create Test Workspace
            </v-btn>
          </v-col>
          <v-col cols="auto">
            <v-btn color="info" @click="broadcastTestMessage">
              <v-icon left>mdi-broadcast</v-icon>
              Broadcast Test Message
            </v-btn>
          </v-col>
          <v-col cols="auto">
            <v-btn color="warning" @click="clearLocalStorage">
              <v-icon left>mdi-delete</v-icon>
              Clear LocalStorage
            </v-btn>
          </v-col>
        </v-row>

        <v-alert type="info" class="mt-4" outlined>
          <div class="font-weight-bold mb-2">How to test session sharing:</div>
          <ol>
            <li>Open this page in two different browser windows (not tabs)</li>
            <li>Check if both windows show the same Workspace ID</li>
            <li>Create a workspace in one window and refresh the other</li>
            <li>The workspace should appear in both windows if sharing works correctly</li>
            <li>Check the Cross-Tab Sync Messages to see if broadcasts are received</li>
          </ol>
        </v-alert>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useAetherTerminalStore } from '../stores/aetherTerminalStore'
import { WorkspacePersistenceManager } from '../stores/workspace/persistenceManager'
import { setJWTToken, removeJWTToken, getCurrentUser } from '@/utils/auth'
import { formatDate, formatTimestamp } from '@/types/common'

// Generate a unique window ID for this instance
const windowId = ref(`window_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)

// Store references
const workspaceStore = useWorkspaceStore()
const aetherStore = useAetherTerminalStore()

// State
const loading = ref(false)
const localStorageData = ref({
  workspaceIds: [] as string[],
  currentWorkspaceId: null as string | null,
  workspaceDetails: [] as any[]
})
const syncMessages = ref<any[]>([])

// Development role simulation state
const selectedRole = ref('Anonymous')

// Computed
const currentWorkspace = computed(() => workspaceStore.currentWorkspace)
const isConnected = computed(() => aetherStore.connectionState.isConnected)
const socketId = computed(() => aetherStore.getSocket()?.id || null)
const activeSessions = computed(() => {
  const sessions: any[] = []
  aetherStore.sessions.forEach((session, id) => {
    sessions.push({
      id,
      type: session.type,
      terminalId: session.terminalId,
      isActive: session.isActive,
      createdAt: session.createdAt
    })
  })
  return sessions
})

const sessionHeaders = [
  { text: 'Session ID', value: 'id' },
  { text: 'Type', value: 'type' },
  { text: 'Terminal ID', value: 'terminalId' },
  { text: 'Active', value: 'isActive' },
  { text: 'Created', value: 'createdAt' }
]

// Methods
const refreshData = async () => {
  loading.value = true
  try {
    // Load localStorage data
    const workspaceIds = JSON.parse(localStorage.getItem('aetherterm_workspaces') || '[]')
    const currentWorkspaceId = localStorage.getItem('aetherterm_current_workspace')
    
    const workspaceDetails = []
    for (const id of workspaceIds) {
      const data = localStorage.getItem(`aetherterm_workspaces_${id}`)
      if (data) {
        workspaceDetails.push(JSON.parse(data))
      }
    }
    
    localStorageData.value = {
      workspaceIds,
      currentWorkspaceId,
      workspaceDetails
    }
    
    // Ensure we're connected
    if (!isConnected.value) {
      await aetherStore.connect()
    }
  } finally {
    loading.value = false
  }
}

const createTestWorkspace = () => {
  // Workspace creation removed - using global workspace only
  console.log('Cannot create workspaces - using global workspace only')
  refreshData()
}

const broadcastTestMessage = () => {
  // Cross-tab sync removed - using server-driven sync
  console.log('Cross-tab sync has been removed. Using server-driven sync instead.')
}

const clearLocalStorage = () => {
  if (confirm('Are you sure you want to clear all workspace data from localStorage?')) {
    WorkspacePersistenceManager.clearAll()
    refreshData()
  }
}


// Development role simulation functions
const getCurrentAuthStatus = () => {
  const user = getCurrentUser()
  if (!user) {
    return 'No authentication (development mode)'
  }
  return `User: ${user.username || user.sub}, Roles: ${user.roles?.join(', ') || 'none'}`
}

const createMockJWT = (role: string) => {
  // Create a mock JWT token for development
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  
  const permissions = (() => {
    switch (role) {
      case 'Supervisor': return ['terminal:supervise', 'terminal:control']
      case 'Owner': return ['terminal:control', 'terminal:manage']
      case 'Viewer': return ['terminal:view']
      case 'Anonymous': return []
      default: return []
    }
  })()
  
  const payload = btoa(JSON.stringify({
    sub: `dev-user-${Date.now()}`,
    username: `dev-${role.toLowerCase()}`,
    email: `dev-${role.toLowerCase()}@example.com`,
    roles: role === 'none' ? [] : [role],
    permissions,
    isSupervisor: role === 'Supervisor',
    exp: Math.floor(Date.now() / 1000) + 86400, // 24 hours
    iat: Math.floor(Date.now() / 1000)
  }))
  const signature = btoa('mock-signature-for-development')
  
  return `${header}.${payload}.${signature}`
}

const applyRole = () => {
  if (selectedRole.value === 'Anonymous') {
    removeJWTToken()
    console.log('🔧 DEBUG: Applied Anonymous role (no authentication)')
  } else {
    const token = createMockJWT(selectedRole.value)
    setJWTToken(token)
    console.log(`🔧 DEBUG: Applied role: ${selectedRole.value}`)
  }
  
  // Force page reload to refresh all auth states
  window.location.reload()
}

const clearRole = () => {
  selectedRole.value = 'none'
  removeJWTToken()
  console.log('🔧 DEBUG: Cleared all authentication')
  
  // Force page reload to refresh all auth states
  window.location.reload()
}

// Cross-tab sync removed - this function is no longer needed
// Initialize current role selection
const initializeCurrentRole = () => {
  const user = getCurrentUser()
  if (!user || !user.roles || user.roles.length === 0) {
    selectedRole.value = 'none'
  } else {
    const role = user.roles[0]
    if (['Anonymous', 'Viewer', 'Owner', 'Supervisor'].includes(role)) {
      selectedRole.value = role
    } else {
      selectedRole.value = 'none'
    }
  }
}

// Lifecycle
onMounted(async () => {
  // WorkspaceDebugPage mounted
  
  // Cross-tab sync removed - using server-driven sync
  
  // Initial data load
  await refreshData()
  
  // Initialize role selection
  initializeCurrentRole()
  
  // Initialize workspace if needed
  if (!workspaceStore.hasCurrentWorkspace) {
    await workspaceStore.initializeWorkspace()
  }
})

onUnmounted(() => {
  // Cross-tab sync removed - cleanup not needed
})
</script>

<style scoped>
pre {
  font-size: 12px;
  background-color: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
}

.overflow-auto {
  overflow: auto;
  max-height: 300px;
}
</style>