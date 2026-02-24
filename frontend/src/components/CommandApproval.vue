<template>
  <div class="command-approval" :class="statusClass">
    <div class="command-header">
      <span class="command-label">Command Proposal</span>
      <span v-if="riskLevel" class="risk-badge" :class="'risk-' + riskLevel">
        {{ riskLevel }}
      </span>
    </div>

    <div class="command-code">
      <code>{{ command }}</code>
    </div>

    <!-- Target pane selector -->
    <div class="command-target" v-if="status === 'pending' && paneOptions.length > 1">
      <label>Target:</label>
      <select v-model="selectedPaneId" class="pane-select">
        <option v-for="p in paneOptions" :key="p.id" :value="p.id">
          {{ p.title }}
        </option>
      </select>
    </div>

    <!-- Action buttons -->
    <div class="command-actions" v-if="status === 'pending'">
      <button class="btn-run" @click="approve">Run</button>
      <button class="btn-reject" @click="reject">Skip</button>
    </div>

    <!-- Status display -->
    <div class="command-status" v-else>
      <span v-if="status === 'executed'" class="status-executed">Executed</span>
      <span v-if="status === 'rejected'" class="status-rejected">Skipped</span>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { useAetherTerminalServiceStore } from '../stores/aetherTerminalServiceStore'
  import { usePaneStore } from '../stores/paneStore'

  const props = defineProps<{
    command: string
    commandId: string
    riskLevel?: 'low' | 'medium' | 'high' | 'critical'
  }>()

  const emit = defineEmits<{
    executed: [commandId: string]
    rejected: [commandId: string]
  }>()

  const terminalStore = useAetherTerminalServiceStore()
  const paneStore = usePaneStore()

  const status = ref<'pending' | 'executed' | 'rejected'>('pending')
  const selectedPaneId = ref(paneStore.focusedPaneId || '')

  const paneOptions = computed(() => paneStore.paneList)

  const statusClass = computed(() => ({
    'status-pending': status.value === 'pending',
    'status-executed': status.value === 'executed',
    'status-rejected': status.value === 'rejected',
  }))

  function approve() {
    if (!terminalStore.socket) return

    terminalStore.socket.emit('ai_execute_command', {
      pane_id: selectedPaneId.value || undefined,
      command: props.command,
      command_id: props.commandId,
    })

    status.value = 'executed'
    emit('executed', props.commandId)
  }

  function reject() {
    status.value = 'rejected'
    emit('rejected', props.commandId)
  }
</script>

<style scoped>
  .command-approval {
    border: 1px solid #444;
    border-radius: 6px;
    padding: 10px;
    margin: 8px 0;
    background-color: #1a1a2e;
    transition: border-color 0.2s;
  }

  .command-approval.status-executed {
    border-color: #4caf50;
    opacity: 0.8;
  }

  .command-approval.status-rejected {
    border-color: #666;
    opacity: 0.6;
  }

  .command-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .command-label {
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .risk-badge {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 3px;
    font-weight: bold;
    text-transform: uppercase;
  }

  .risk-low { background-color: #4caf50; color: #fff; }
  .risk-medium { background-color: #ff9800; color: #fff; }
  .risk-high { background-color: #ff5722; color: #fff; }
  .risk-critical { background-color: #f44336; color: #fff; }

  .command-code {
    background-color: #0d0d1a;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 8px;
    overflow-x: auto;
  }

  .command-code code {
    color: #4caf50;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .command-target {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    font-size: 12px;
  }

  .command-target label {
    color: #888;
  }

  .pane-select {
    background-color: #1e1e1e;
    border: 1px solid #444;
    border-radius: 3px;
    color: #ccc;
    padding: 3px 6px;
    font-size: 12px;
    flex: 1;
  }

  .command-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .btn-run {
    background-color: #4caf50;
    color: white;
    border: none;
    padding: 5px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: bold;
    transition: background-color 0.15s;
  }

  .btn-run:hover {
    background-color: #45a049;
  }

  .btn-reject {
    background-color: transparent;
    color: #888;
    border: 1px solid #555;
    padding: 5px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.15s;
  }

  .btn-reject:hover {
    color: #f44336;
    border-color: #f44336;
  }

  .command-status {
    text-align: right;
    font-size: 11px;
  }

  .status-executed {
    color: #4caf50;
  }

  .status-rejected {
    color: #888;
  }
</style>
