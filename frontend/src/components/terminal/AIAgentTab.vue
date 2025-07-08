<template>
  <div class="ai-agent-tab-container">
    <!-- 上部ペーン: エージェント向けターミナル群（横スクロール可能） -->
    <div class="agent-terminals-pane">
      <div class="agents-header">
        <h3>Sub Agents</h3>
        <v-btn 
          size="small" 
          icon="mdi-plus" 
          @click="addAgentTerminal"
          class="add-agent-btn"
        />
      </div>
      <div class="agents-scroll-container">
        <div 
          v-for="agent in agentTerminals" 
          :key="agent.id"
          class="agent-terminal-card"
        >
          <div class="agent-header">
            <span class="agent-name">{{ agent.name }}</span>
            <v-btn 
              size="x-small" 
              icon="mdi-close" 
              @click="removeAgentTerminal(agent.id)"
              class="close-btn"
            />
          </div>
          <div class="agent-terminal">
            <AetherTerminalComponent 
              :id="agent.terminalId"
              mode="pane"
              :sub-type="'agent'"
              @terminal-initialized="() => onAgentTerminalInitialized(agent.id)"
            />
          </div>
        </div>
        
        <!-- 新しいエージェント追加カード -->
        <div class="add-agent-card" @click="addAgentTerminal">
          <v-icon size="48" color="primary">mdi-plus-circle-outline</v-icon>
          <span>Add Agent</span>
        </div>
      </div>
    </div>

    <!-- 区切り線とリサイザー -->
    <div class="pane-divider" @mousedown="startResize">
      <div class="resize-handle"></div>
    </div>

    <!-- 下部ペーン: MainAgent専用ターミナル -->
    <div class="main-agent-pane" :style="{ height: mainAgentPaneHeight }">
      <div class="main-agent-header">
        <h3>Main Agent</h3>
        <v-chip 
          :color="mainAgentStatus === 'active' ? 'success' : 'warning'"
          size="small"
        >
          {{ mainAgentStatus }}
        </v-chip>
      </div>
      <div class="main-agent-terminal">
        <AetherTerminalComponent 
          :id="mainAgentTerminalId"
          mode="pane"
          :sub-type="'main-agent'"
          @terminal-initialized="() => onMainAgentTerminalInitialized()"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useTerminalTabStore } from '../../stores/terminalTabStore'

interface Props {
  tabId: string
}

interface AgentTerminal {
  id: string
  name: string
  terminalId: string
  status: 'active' | 'inactive' | 'error'
}

const props = defineProps<Props>()
const tabStore = useTerminalTabStore()

// State
const agentTerminals = ref<AgentTerminal[]>([])
const mainAgentTerminalId = ref('')
const mainAgentStatus = ref<'active' | 'inactive' | 'error'>('inactive')
const mainAgentPaneHeight = ref('40%')
const isResizing = ref(false)

// Computed
const nextAgentNumber = computed(() => agentTerminals.value.length + 1)

// Methods
const addAgentTerminal = () => {
  console.log('🔧 Adding new agent terminal...')
  const agentId = `agent-${props.tabId}-${Date.now()}`
  const terminalId = `terminal-${agentId}`
  
  const newAgent: AgentTerminal = {
    id: agentId,
    name: `Agent ${nextAgentNumber.value}`,
    terminalId: terminalId,
    status: 'inactive'
  }
  
  console.log('Creating agent:', newAgent)
  agentTerminals.value.push(newAgent)
  
  // Create terminal tab in store
  console.log('Creating terminal session:', terminalId)
  tabStore.createTerminalSession(terminalId, 'agent')
  console.log('✅ Agent terminal added successfully')
}

const removeAgentTerminal = (agentId: string) => {
  const index = agentTerminals.value.findIndex(agent => agent.id === agentId)
  if (index > -1) {
    const agent = agentTerminals.value[index]
    // Close terminal session
    tabStore.closeTerminalSession(agent.terminalId)
    // Remove from array
    agentTerminals.value.splice(index, 1)
  }
}

const onAgentTerminalInitialized = (agentId: string) => {
  const agent = agentTerminals.value.find(a => a.id === agentId)
  if (agent) {
    agent.status = 'active'
    console.log(`Agent ${agent.name} terminal initialized`)
  }
}

const onMainAgentTerminalInitialized = () => {
  mainAgentStatus.value = 'active'
  console.log('Main agent terminal initialized')
}

// Resize functionality
const startResize = (e: MouseEvent) => {
  isResizing.value = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
  e.preventDefault()
}

const handleResize = (e: MouseEvent) => {
  if (!isResizing.value) return
  
  const container = document.querySelector('.ai-agent-tab-container') as HTMLElement
  if (!container) return
  
  const containerRect = container.getBoundingClientRect()
  const newHeight = ((containerRect.bottom - e.clientY) / containerRect.height) * 100
  
  // Constrain between 20% and 70%
  const constrainedHeight = Math.max(20, Math.min(70, newHeight))
  mainAgentPaneHeight.value = `${constrainedHeight}%`
}

const stopResize = () => {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

// Initialization
onMounted(() => {
  // Create main agent terminal
  mainAgentTerminalId.value = `main-agent-${props.tabId}`
  tabStore.createTerminalSession(mainAgentTerminalId.value, 'main-agent')
  
  // Add initial agent terminal
  addAgentTerminal()
})
</script>

<style scoped lang="scss">
@import '../../assets/styles/base.scss';

.ai-agent-tab-container {
  @include flex-column;
  flex: 1;
  overflow: hidden;
  height: 100%;
}

.agent-terminals-pane {
  flex: 1;
  @include flex-column;
  min-height: 30%;
  background: var(--v-theme-surface);
  border-bottom: 1px solid var(--v-theme-outline);
}

.agents-header {
  @include flex-row;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--v-theme-outline);
  background: var(--v-theme-surface-variant);
  
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--v-theme-on-surface);
  }
}

.agents-scroll-container {
  @include flex-row;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 12px;
  gap: 12px;
  
  &::-webkit-scrollbar {
    height: 8px;
  }
  
  &::-webkit-scrollbar-track {
    background: var(--v-theme-surface-variant);
    border-radius: 4px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: var(--v-theme-outline);
    border-radius: 4px;
    
    &:hover {
      background: var(--v-theme-primary);
    }
  }
}

.agent-terminal-card {
  @include flex-column;
  min-width: 320px;
  max-width: 400px;
  height: calc(100% - 24px);
  background: var(--v-theme-surface);
  border: 1px solid var(--v-theme-outline);
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
}

.agent-header {
  @include flex-row;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--v-theme-surface-variant);
  border-bottom: 1px solid var(--v-theme-outline);
  
  .agent-name {
    font-weight: 500;
    font-size: 12px;
    color: var(--v-theme-on-surface);
  }
  
  .close-btn {
    opacity: 0.7;
    
    &:hover {
      opacity: 1;
    }
  }
}

.agent-terminal {
  flex: 1;
  overflow: hidden;
}

.add-agent-card {
  @include flex-column;
  align-items: center;
  justify-content: center;
  min-width: 200px;
  height: calc(100% - 24px);
  background: var(--v-theme-surface-variant);
  border: 2px dashed var(--v-theme-outline);
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s ease;
  
  &:hover {
    border-color: var(--v-theme-primary);
    background: var(--v-theme-primary-container);
  }
  
  span {
    margin-top: 8px;
    font-size: 14px;
    color: var(--v-theme-on-surface-variant);
  }
}

.pane-divider {
  height: 4px;
  background: var(--v-theme-outline);
  cursor: row-resize;
  position: relative;
  
  &:hover {
    background: var(--v-theme-primary);
  }
  
  .resize-handle {
    position: absolute;
    top: -2px;
    left: 50%;
    transform: translateX(-50%);
    width: 40px;
    height: 8px;
    background: var(--v-theme-primary);
    border-radius: 4px;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  
  &:hover .resize-handle {
    opacity: 1;
  }
}

.main-agent-pane {
  @include flex-column;
  background: var(--v-theme-surface);
  min-height: 20%;
}

.main-agent-header {
  @include flex-row;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--v-theme-outline);
  background: var(--v-theme-surface-variant);
  
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--v-theme-on-surface);
  }
}

.main-agent-terminal {
  flex: 1;
  overflow: hidden;
}

// Responsive adjustments
@media (max-width: 768px) {
  .agent-terminal-card {
    min-width: 280px;
    max-width: 320px;
  }
  
  .add-agent-card {
    min-width: 160px;
  }
}
</style>