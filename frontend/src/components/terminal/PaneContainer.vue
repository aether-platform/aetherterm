<template>
  <div class="pane-container" :class="`layout-${layout}`">
    <!-- Single Pane Layout -->
    <div v-if="layout === 'single' && panes.length > 0" class="single-pane">
      <PaneHeader 
        :pane="panes[0]" 
        @split="handleSplit"
        @close="handleClose"
        @rename="handleRename"
        @clear-buffer="handleClearBuffer"
        @save-buffer="handleSaveBuffer"
        @restore-buffer="handleRestoreBuffer"
        @export-buffer="handleExportBuffer"
        @open-search="handleOpenSearch"
        @copy-selection="handleCopySelection"
        @paste-clipboard="handlePasteClipboard"
        @select-all="handleSelectAll"
      />
      <div class="pane-content">
        <TerminalStatus :session-id="panes[0].sessionId" />
        <AetherTerminalComponent 
          :id="panes[0].id" 
          mode="pane"
          :sub-type="panes[0].subType"
          @terminal-initialized="handleTerminalInitialized"
          :ref="(el) => setTerminalRef(panes[0].id, el)"
        />
      </div>
    </div>

    <!-- Horizontal Split Layout -->
    <div v-else-if="layout === 'horizontal'" class="horizontal-split">
      <div 
        v-for="(pane, index) in panes" 
        :key="pane.id"
        class="horizontal-pane"
        :style="{ width: `${pane.position.width}%` }"
      >
        <PaneHeader 
          :pane="pane" 
          @split="handleSplit"
          @close="handleClose"
          @rename="handleRename"
          @clear-buffer="handleClearBuffer"
          @save-buffer="handleSaveBuffer"
          @restore-buffer="handleRestoreBuffer"
          @export-buffer="handleExportBuffer"
        />
        <div class="pane-content">
          <TerminalStatus :session-id="pane.sessionId" />
          <AetherTerminalComponent 
            :id="pane.id" 
            mode="pane"
            :sub-type="pane.subType"
            :ref="(el) => setTerminalRef(pane.id, el)"
          />
        </div>
        <!-- Resize Handle -->
        <div 
          v-if="index < panes.length - 1"
          class="resize-handle vertical"
          @mousedown="startResize($event, index, 'horizontal')"
        ></div>
      </div>
    </div>

    <!-- Vertical Split Layout -->
    <div v-else-if="layout === 'vertical'" class="vertical-split">
      <div 
        v-for="(pane, index) in panes" 
        :key="pane.id"
        class="vertical-pane"
        :style="{ height: `${pane.position.height}%` }"
      >
        <PaneHeader 
          :pane="pane" 
          @split="handleSplit"
          @close="handleClose"
          @rename="handleRename"
          @clear-buffer="handleClearBuffer"
          @save-buffer="handleSaveBuffer"
          @restore-buffer="handleRestoreBuffer"
          @export-buffer="handleExportBuffer"
        />
        <div class="pane-content">
          <TerminalStatus :session-id="pane.sessionId" />
          <AetherTerminalComponent 
            :id="pane.id" 
            mode="pane"
            :sub-type="pane.subType"
            :ref="(el) => setTerminalRef(pane.id, el)"
          />
        </div>
        <!-- Resize Handle -->
        <div 
          v-if="index < panes.length - 1"
          class="resize-handle horizontal"
          @mousedown="startResize($event, index, 'vertical')"
        ></div>
      </div>
    </div>

    <!-- Grid Layout -->
    <div v-else-if="layout === 'grid'" class="grid-layout">
      <div 
        v-for="pane in panes" 
        :key="pane.id"
        class="grid-pane"
        :style="{
          left: `${pane.position.x}%`,
          top: `${pane.position.y}%`,
          width: `${pane.position.width}%`,
          height: `${pane.position.height}%`
        }"
      >
        <PaneHeader 
          :pane="pane" 
          @split="handleSplit"
          @close="handleClose"
          @rename="handleRename"
          @clear-buffer="handleClearBuffer"
          @save-buffer="handleSaveBuffer"
          @restore-buffer="handleRestoreBuffer"
          @export-buffer="handleExportBuffer"
        />
        <div class="pane-content">
          <TerminalStatus :session-id="pane.sessionId" />
          <AetherTerminalComponent 
            :id="pane.id" 
            mode="pane"
            :sub-type="pane.subType"
            :ref="(el) => setTerminalRef(pane.id, el)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTerminalPaneStore, type TerminalPane } from '../../stores/terminalPaneStore'
import AetherTerminalComponent from './AetherTerminalComponent.vue'
import PaneHeader from './PaneHeader.vue'
import TerminalStatus from './TerminalStatus.vue'

interface Props {
  tabId: string
  layout: 'single' | 'horizontal' | 'vertical' | 'grid'
}

interface Emits {
  (e: 'layout-changed', layout: string): void
  (e: 'pane-created', pane: TerminalPane): void
  (e: 'pane-closed', paneId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Store
const paneStore = useTerminalPaneStore()

// Terminal references
const terminalRefs = ref<Map<string, any>>(new Map())

// Computed
const panes = computed(() => paneStore.getPanesByTab(props.tabId))

// Resize state
const isResizing = ref(false)
const resizeData = ref<{
  startX: number
  startY: number
  paneIndex: number
  direction: 'horizontal' | 'vertical'
} | null>(null)

// Methods
const handleSplit = (paneId: string, direction: 'horizontal' | 'vertical') => {
  console.log('🔧 PANE: Splitting pane:', paneId, 'direction:', direction)
  
  const newPane = paneStore.splitPane(paneId, direction)
  if (newPane) {
    emit('pane-created', newPane)
    
    // Update layout based on split
    const newLayout = direction === 'horizontal' ? 'horizontal' : 'vertical'
    paneStore.updatePaneLayout(props.tabId, newLayout)
    emit('layout-changed', newLayout)
  }
}

const handleClose = (paneId: string) => {
  console.log('🔧 PANE: Closing pane:', paneId)
  
  paneStore.closePane(paneId)
  emit('pane-closed', paneId)
  
  // If only one pane left, switch to single layout
  const remainingPanes = paneStore.getPanesByTab(props.tabId)
  if (remainingPanes.length <= 1) {
    paneStore.updatePaneLayout(props.tabId, 'single')
    emit('layout-changed', 'single')
  }
}

const handleRename = (paneId: string, newTitle: string) => {
  const pane = panes.value.find(p => p.id === paneId)
  if (pane) {
    pane.title = newTitle
    console.log('🔧 PANE: Renamed pane:', paneId, 'to:', newTitle)
  }
}

// Terminal reference management
const setTerminalRef = (paneId: string, el: any) => {
  if (el) {
    terminalRefs.value.set(paneId, el)
  } else {
    terminalRefs.value.delete(paneId)
  }
}

// Buffer management handlers
const handleClearBuffer = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    terminalRef.clearScreenBuffer()
    console.log('🔧 BUFFER: Cleared buffer for pane:', paneId)
  }
}

const handleSaveBuffer = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    const stateName = `save_${timestamp}`
    terminalRef.saveBufferState(stateName)
    console.log('🔧 BUFFER: Saved buffer state for pane:', paneId, 'as:', stateName)
  }
}

const handleRestoreBuffer = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    // For demo purposes, restore the most recent save
    // In a real implementation, you might want to show a dialog to select which save to restore
    console.log('🔧 BUFFER: Restore buffer for pane:', paneId)
    // This would need to be implemented based on your save/restore strategy
  }
}

const handleExportBuffer = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    const bufferContent = terminalRef.exportBuffer('text')
    const blob = new Blob([bufferContent], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `terminal_buffer_${paneId}_${new Date().toISOString()}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    console.log('🔧 BUFFER: Exported buffer for pane:', paneId)
  }
}

// Search and editing handlers
const handleOpenSearch = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    terminalRef.openSearch()
    console.log('🔍 SEARCH: Opened search for pane:', paneId)
  }
}

const handleCopySelection = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    terminalRef.copySelection()
    console.log('📋 COPY: Copied selection for pane:', paneId)
  }
}

const handlePasteClipboard = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    terminalRef.pasteFromClipboard()
    console.log('📋 PASTE: Pasted clipboard for pane:', paneId)
  }
}

const handleSelectAll = (paneId: string) => {
  const terminalRef = terminalRefs.value.get(paneId)
  if (terminalRef) {
    terminalRef.selectAll()
    console.log('🔘 SELECT: Selected all for pane:', paneId)
  }
}

const handleTerminalInitialized = () => {
  console.log('🔧 PANE: Terminal initialized for pane')
}

const startResize = (event: MouseEvent, paneIndex: number, direction: 'horizontal' | 'vertical') => {
  event.preventDefault()
  
  isResizing.value = true
  resizeData.value = {
    startX: event.clientX,
    startY: event.clientY,
    paneIndex,
    direction
  }
  
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
}

const handleResize = (event: MouseEvent) => {
  if (!isResizing.value || !resizeData.value) return
  
  const { startX, startY, paneIndex, direction } = resizeData.value
  const containerRect = document.querySelector('.pane-container')?.getBoundingClientRect()
  
  if (!containerRect) return
  
  const currentPanes = panes.value
  if (paneIndex >= currentPanes.length - 1) return
  
  if (direction === 'horizontal') {
    const deltaX = event.clientX - startX
    const deltaPercent = (deltaX / containerRect.width) * 100
    
    // Update current and next pane widths
    const currentPane = currentPanes[paneIndex]
    const nextPane = currentPanes[paneIndex + 1]
    
    const newCurrentWidth = Math.max(10, Math.min(90, currentPane.position.width + deltaPercent))
    const newNextWidth = Math.max(10, Math.min(90, nextPane.position.width - deltaPercent))
    
    currentPane.position.width = newCurrentWidth
    nextPane.position.width = newNextWidth
    
    resizeData.value.startX = event.clientX
  } else {
    const deltaY = event.clientY - startY
    const deltaPercent = (deltaY / containerRect.height) * 100
    
    // Update current and next pane heights
    const currentPane = currentPanes[paneIndex]
    const nextPane = currentPanes[paneIndex + 1]
    
    const newCurrentHeight = Math.max(10, Math.min(90, currentPane.position.height + deltaPercent))
    const newNextHeight = Math.max(10, Math.min(90, nextPane.position.height - deltaPercent))
    
    currentPane.position.height = newCurrentHeight
    nextPane.position.height = newNextHeight
    
    resizeData.value.startY = event.clientY
  }
}

const stopResize = () => {
  isResizing.value = false
  resizeData.value = null
  
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

onMounted(() => {
  // Initialize with a default pane if none exist
  const existingPanes = paneStore.getPanesByTab(props.tabId)
  if (existingPanes.length === 0) {
    const defaultPane = paneStore.createPane(props.tabId, 'terminal', 'Terminal 1', 'pure')
    emit('pane-created', defaultPane)
  }
})

onUnmounted(() => {
  // Clean up event listeners
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
})
</script>

<style scoped lang="scss">
@import '../../assets/styles/base.scss';

.pane-container {
  @include flex-column;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
}

.single-pane {
  @include flex-column;
  height: 100%;
  width: 100%;
}

.horizontal-split {
  @include flex-row;
  height: 100%;
  width: 100%;
}

.horizontal-pane {
  @include flex-column;
  height: 100%;
  position: relative;
  min-width: 10%;
}

.vertical-split {
  @include flex-column;
  height: 100%;
  width: 100%;
}

.vertical-pane {
  @include flex-column;
  width: 100%;
  position: relative;
  min-height: 10%;
}

.grid-layout {
  position: relative;
  height: 100%;
  width: 100%;
}

.grid-pane {
  position: absolute;
  @include flex-column;
  min-width: 10%;
  min-height: 10%;
  border: 1px solid var(--color-border-primary);
  background-color: var(--color-bg-primary);
}

.pane-content {
  flex: 1;
  overflow: hidden;
}

.resize-handle {
  position: absolute;
  background-color: var(--color-border-primary);
  z-index: 10;
  
  &:hover {
    background-color: var(--color-primary);
  }
  
  &.vertical {
    width: 4px;
    height: 100%;
    right: -2px;
    top: 0;
    cursor: col-resize;
  }
  
  &.horizontal {
    width: 100%;
    height: 4px;
    bottom: -2px;
    left: 0;
    cursor: row-resize;
  }
}

// Layout-specific styles
.layout-single .single-pane {
  border: none;
}

.layout-horizontal .horizontal-pane:not(:last-child) {
  border-right: 1px solid var(--color-border-primary);
}

.layout-vertical .vertical-pane:not(:last-child) {
  border-bottom: 1px solid var(--color-border-primary);
}

.layout-grid .grid-pane {
  border: 2px solid var(--color-border-primary);
  
  &:hover {
    border-color: var(--color-primary);
  }
}
</style>