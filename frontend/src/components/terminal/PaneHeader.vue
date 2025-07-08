<template>
  <div class="pane-header" :class="{ 'active': pane.isActive }">
    <!-- Title -->
    <div class="pane-title" @dblclick="startTitleEdit">
      <input
        v-if="isEditingTitle"
        v-model="editTitle"
        ref="titleInput"
        class="title-input"
        @blur="finishTitleEdit"
        @keyup.enter="finishTitleEdit"
        @keyup.escape="cancelTitleEdit"
      />
      <span v-else class="title-text">{{ pane.title }}</span>
    </div>

    <!-- Status Indicator -->
    <div class="status-indicator">
      <v-icon 
        :icon="statusIcon" 
        :color="statusColor" 
        size="small"
      />
    </div>

    <!-- Buffer Status -->
    <div class="buffer-status" v-if="bufferStats.totalLines > 0">
      <span class="buffer-lines">{{ bufferStats.totalLines }} lines</span>
    </div>

    <!-- Pane Actions -->
    <div class="pane-actions">
      <!-- Permission Control -->
      <TerminalPermissionControl 
        v-if="pane.sessionId"
        :session-id="pane.sessionId"
      />
      
      <!-- Search Control -->
      <v-btn
        icon
        size="x-small"
        variant="text"
        @click="openSearch"
        title="Search Terminal (Ctrl+Shift+F)"
      >
        <v-icon>mdi-magnify</v-icon>
      </v-btn>
      
      <!-- Buffer Controls -->
      <v-btn
        icon
        size="x-small"
        variant="text"
        @click="clearBuffer"
        title="Clear Buffer"
      >
        <v-icon>mdi-broom</v-icon>
      </v-btn>
      
      <!-- Split Buttons -->
      <v-btn
        icon
        size="x-small"
        variant="text"
        @click="$emit('split', pane.id, 'horizontal')"
        title="Split Horizontally"
      >
        <v-icon>mdi-view-column</v-icon>
      </v-btn>
      
      <v-btn
        icon
        size="x-small"
        variant="text"
        @click="$emit('split', pane.id, 'vertical')"
        title="Split Vertically"
      >
        <v-icon>mdi-view-agenda</v-icon>
      </v-btn>

      <!-- Dropdown Menu -->
      <v-menu>
        <template v-slot:activator="{ props: menuProps }">
          <v-btn
            icon
            size="x-small"
            variant="text"
            v-bind="menuProps"
            title="More Options"
          >
            <v-icon>mdi-dots-vertical</v-icon>
          </v-btn>
        </template>
        
        <v-list>
          <v-list-item @click="copySelection">
            <v-list-item-title>
              <v-icon start>mdi-content-copy</v-icon>
              Copy Selection
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="pasteFromClipboard">
            <v-list-item-title>
              <v-icon start>mdi-content-paste</v-icon>
              Paste
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="selectAll">
            <v-list-item-title>
              <v-icon start>mdi-select-all</v-icon>
              Select All
            </v-list-item-title>
          </v-list-item>
          
          <v-divider />
          
          <v-list-item @click="saveBuffer">
            <v-list-item-title>
              <v-icon start>mdi-content-save</v-icon>
              Save Buffer
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="restoreBuffer">
            <v-list-item-title>
              <v-icon start>mdi-restore</v-icon>
              Restore Buffer
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="exportBuffer">
            <v-list-item-title>
              <v-icon start>mdi-download</v-icon>
              Export Buffer
            </v-list-item-title>
          </v-list-item>
          
          <v-divider />
          
          <v-list-item @click="duplicatePane">
            <v-list-item-title>
              <v-icon start>mdi-content-duplicate</v-icon>
              Duplicate Pane
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="startTitleEdit">
            <v-list-item-title>
              <v-icon start>mdi-pencil</v-icon>
              Rename
            </v-list-item-title>
          </v-list-item>
          
          <v-list-item @click="showPaneInfo">
            <v-list-item-title>
              <v-icon start>mdi-information</v-icon>
              Pane Info
            </v-list-item-title>
          </v-list-item>
          
          <v-divider />
          
          <v-list-item @click="closePane" class="text-error">
            <v-list-item-title>
              <v-icon start>mdi-close</v-icon>
              Close Pane
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>

    <!-- Pane Info Dialog -->
    <v-dialog v-model="showInfoDialog" max-width="400">
      <v-card>
        <v-card-title>Pane Information</v-card-title>
        <v-card-text>
          <table class="info-table">
            <tbody>
              <tr>
                <td><strong>ID:</strong></td>
                <td>{{ pane.id }}</td>
              </tr>
              <tr>
                <td><strong>Type:</strong></td>
                <td>{{ pane.type }}</td>
              </tr>
              <tr>
                <td><strong>Sub Type:</strong></td>
                <td>{{ pane.subType || 'N/A' }}</td>
              </tr>
              <tr>
                <td><strong>Session ID:</strong></td>
                <td>{{ pane.sessionId || 'N/A' }}</td>
              </tr>
              <tr>
                <td><strong>Status:</strong></td>
                <td>{{ pane.status }}</td>
              </tr>
              <tr>
                <td><strong>Position:</strong></td>
                <td>{{ `${pane.position.x}%, ${pane.position.y}%` }}</td>
              </tr>
              <tr>
                <td><strong>Size:</strong></td>
                <td>{{ `${pane.position.width}% × ${pane.position.height}%` }}</td>
              </tr>
              <tr>
                <td><strong>Last Activity:</strong></td>
                <td>{{ formatDate(pane.lastActivity) }}</td>
              </tr>
              <tr>
                <td><strong>Buffer Lines:</strong></td>
                <td>{{ bufferStats.totalLines }} / {{ bufferStats.maxLines }}</td>
              </tr>
              <tr>
                <td><strong>Current Position:</strong></td>
                <td>{{ bufferStats.currentLine + 1 }}</td>
              </tr>
            </tbody>
          </table>
        </v-card-text>
        <div class="dialog-actions">
          <div class="spacer" />
          <v-btn @click="showInfoDialog = false">Close</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useTerminalPaneStore, type TerminalPane } from '../../stores/terminalPaneStore'
import { useScreenBufferStore } from '../../stores/screenBufferStore'
import TerminalPermissionControl from './TerminalPermissionControl.vue'

interface Props {
  pane: TerminalPane
}

interface Emits {
  (e: 'split', paneId: string, direction: 'horizontal' | 'vertical'): void
  (e: 'close', paneId: string): void
  (e: 'rename', paneId: string, newTitle: string): void
  (e: 'clear-buffer', paneId: string): void
  (e: 'save-buffer', paneId: string): void
  (e: 'restore-buffer', paneId: string): void
  (e: 'export-buffer', paneId: string): void
  (e: 'open-search', paneId: string): void
  (e: 'copy-selection', paneId: string): void
  (e: 'paste-clipboard', paneId: string): void
  (e: 'select-all', paneId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Store
const paneStore = useTerminalPaneStore()
const screenBufferStore = useScreenBufferStore()

// Title editing
const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref<HTMLInputElement>()

// Dialog state
const showInfoDialog = ref(false)

// Computed
const statusIcon = computed(() => {
  switch (props.pane.status) {
    case 'active': return 'mdi-check-circle'
    case 'connecting': return 'mdi-loading'
    case 'disconnected': return 'mdi-close-circle'
    case 'error': return 'mdi-alert-circle'
    default: return 'mdi-help-circle'
  }
})

const statusColor = computed(() => {
  switch (props.pane.status) {
    case 'active': return 'success'
    case 'connecting': return 'warning'
    case 'disconnected': return 'error'
    case 'error': return 'error'
    default: return 'grey'
  }
})

const bufferStats = computed(() => {
  if (props.pane.sessionId) {
    return screenBufferStore.getBufferStats(props.pane.sessionId)
  }
  return { totalLines: 0, currentLine: 0, maxLines: 0 }
})

// Methods
const startTitleEdit = async () => {
  isEditingTitle.value = true
  editTitle.value = props.pane.title
  
  await nextTick()
  if (titleInput.value) {
    titleInput.value.focus()
    titleInput.value.select()
  }
}

const finishTitleEdit = () => {
  if (editTitle.value.trim() && editTitle.value !== props.pane.title) {
    emit('rename', props.pane.id, editTitle.value.trim())
  }
  isEditingTitle.value = false
}

const cancelTitleEdit = () => {
  editTitle.value = props.pane.title
  isEditingTitle.value = false
}

const duplicatePane = () => {
  console.log('🔧 PANE: Duplicating pane:', props.pane.id)
  
  // Create a new pane with similar properties
  const newPane = paneStore.createPane(
    props.pane.tabId,
    props.pane.type,
    `${props.pane.title} (Copy)`,
    props.pane.subType,
    {
      x: props.pane.position.x + 5, // Slight offset
      y: props.pane.position.y + 5,
      width: props.pane.position.width,
      height: props.pane.position.height
    }
  )
  
  console.log('🔧 PANE: Created duplicate pane:', newPane.id)
}

const closePane = () => {
  emit('close', props.pane.id)
}

const showPaneInfo = () => {
  showInfoDialog.value = true
}

const formatDate = (date: Date): string => {
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).format(date)
}

// Buffer management methods
const clearBuffer = () => {
  emit('clear-buffer', props.pane.id)
}

const saveBuffer = () => {
  emit('save-buffer', props.pane.id)
}

const restoreBuffer = () => {
  emit('restore-buffer', props.pane.id)
}

const exportBuffer = () => {
  emit('export-buffer', props.pane.id)
}

// Search and editing methods
const openSearch = () => {
  emit('open-search', props.pane.id)
}

const copySelection = () => {
  emit('copy-selection', props.pane.id)
}

const pasteFromClipboard = () => {
  emit('paste-clipboard', props.pane.id)
}

const selectAll = () => {
  emit('select-all', props.pane.id)
}
</script>

<style scoped lang="scss">
@import '../../assets/styles/base.scss';

.pane-header {
  @include flex-row;
  align-items: center;
  justify-content: space-between;
  padding: $spacing-xs $spacing-sm;
  background-color: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-primary);
  min-height: 32px;
  gap: $spacing-sm;
  
  &.active {
    background-color: var(--color-primary-light);
    border-bottom-color: var(--color-primary);
  }
}

.pane-title {
  flex: 1;
  min-width: 0; // Allow text to truncate
}

.title-text {
  font-size: $font-size-sm;
  font-weight: $font-weight-medium;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  
  &:hover {
    color: var(--color-primary);
  }
}

.title-input {
  width: 100%;
  padding: 2px 4px;
  font-size: $font-size-sm;
  font-weight: $font-weight-medium;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--color-primary);
  border-radius: 2px;
  color: var(--color-text-primary);
  outline: none;
  
  &:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 1px var(--color-primary);
  }
}

.status-indicator {
  @include flex-center;
  min-width: 20px;
}

.buffer-status {
  @include flex-center;
  font-size: $font-size-xs;
  color: var(--color-text-secondary);
  padding: 0 $spacing-xs;
  
  .buffer-lines {
    background-color: var(--color-bg-tertiary);
    border: 1px solid var(--color-border-secondary);
    border-radius: 4px;
    padding: 2px 6px;
    min-width: 50px;
    text-align: center;
  }
}

.pane-actions {
  @include flex-row;
  align-items: center;
  gap: 2px;
}

// Vuetify overrides
:deep(.v-btn) {
  min-width: auto !important;
}

:deep(.v-list-item-title) {
  @include flex-row;
  align-items: center;
  gap: $spacing-xs;
}

.info-table {
  width: 100%;
  border-collapse: collapse;
  background-color: transparent;
  
  tbody tr td {
    padding: 8px 12px;
    font-size: $font-size-sm;
    border-bottom: 1px solid var(--color-border-primary);
    vertical-align: top;
    
    &:first-child {
      width: 40%;
      text-align: right;
      padding-right: 16px;
      font-weight: $font-weight-medium;
    }
  }
}

.dialog-actions {
  display: flex;
  align-items: center;
  padding: 16px 24px;
  border-top: 1px solid var(--color-border-primary);
  
  .spacer {
    flex: 1;
  }
}
</style>