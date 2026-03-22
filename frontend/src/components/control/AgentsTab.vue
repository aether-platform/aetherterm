<script setup lang="ts">
import { ref, computed } from 'vue'

interface AgentInfo {
  role?: string
  status?: string
  line_count?: number
  session_id?: string
  pane_id?: string
}

interface ServerInfo {
  server_id: string
  alive: boolean
  agents?: Record<string, AgentInfo>
}

interface AgentRow {
  server_id: string
  agent_id: string
  role: string
  status: string
  line_count: number
  session_id: string
  pane_id: string
  alive: boolean
}

const props = defineProps<{
  server?: ServerInfo | null
  servers?: Record<string, ServerInfo>
  viewMode?: string
}>()

const emit = defineEmits<{
  command: [command: Record<string, unknown>, serverId: string]
  'switch-tab': [tab: string, agentId: string]
}>()

const selected = ref<Set<string>>(new Set())
const agentSearch = ref('')

const effectiveViewMode = computed(() => props.viewMode ?? 'maintainer')

// Maintainer mode: all agents across all servers
// Developer mode: agents of the selected server only
const agentRows = computed<AgentRow[]>(() => {
  const rows: AgentRow[] = []
  if (effectiveViewMode.value === 'maintainer') {
    for (const srv of Object.values(props.servers ?? {})) {
      for (const [aid, info] of Object.entries(srv.agents ?? {})) {
        rows.push({
          server_id: srv.server_id,
          agent_id: aid,
          role: info.role ?? 'unknown',
          status: info.status ?? 'unknown',
          line_count: info.line_count ?? 0,
          session_id: info.session_id ?? '',
          pane_id: info.pane_id ?? '',
          alive: srv.alive,
        })
      }
    }
  } else {
    if (props.server?.agents) {
      for (const [aid, info] of Object.entries(props.server.agents)) {
        rows.push({
          server_id: props.server.server_id,
          agent_id: aid,
          role: info.role ?? 'unknown',
          status: info.status ?? 'unknown',
          line_count: info.line_count ?? 0,
          session_id: info.session_id ?? '',
          pane_id: info.pane_id ?? '',
          alive: props.server.alive,
        })
      }
    }
  }
  return rows
})

const filteredAgentRows = computed(() => {
  const q = agentSearch.value.toLowerCase()
  if (!q) return agentRows.value
  return agentRows.value.filter((r) => {
    const haystack = `${r.agent_id} ${r.role} ${r.server_id} ${r.status}`.toLowerCase()
    return haystack.includes(q)
  })
})

const hasSelected = computed(() => selected.value.size > 0)

function toggleSelect(key: string) {
  const s = new Set(selected.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  selected.value = s
}

function selectAll() {
  if (selected.value.size === agentRows.value.length) {
    selected.value = new Set()
  } else {
    selected.value = new Set(agentRows.value.map((r) => `${r.server_id}/${r.agent_id}`))
  }
}

function blockSelected() {
  for (const key of selected.value) {
    const [serverId, agentId] = key.split('/', 2)
    emit('command', { action: 'block', agent_id: agentId }, serverId)
  }
}

function unblockSelected() {
  for (const key of selected.value) {
    const [serverId, agentId] = key.split('/', 2)
    emit('command', { action: 'unblock', agent_id: agentId }, serverId)
  }
}

function pauseSelected() {
  const serverIds = new Set<string>()
  for (const key of selected.value) {
    serverIds.add(key.split('/')[0])
  }
  for (const sid of serverIds) {
    emit('command', { action: 'pause_all' }, sid)
  }
}

function openTerminal(row: AgentRow) {
  emit('switch-tab', 'command', row.agent_id)
}

function roleIcon(role: string): string {
  const map: Record<string, string> = {
    parent: '&#9670;',
    coder: '&#9998;',
    reviewer: '&#9745;',
    tester: '&#9881;',
    architect: '&#9632;',
    shell: '&#9654;',
  }
  return map[role] || '&#9671;'
}
</script>

<template>
  <div class="tab-content">
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="toolbar-left">
        <input
          v-model="agentSearch"
          class="agent-search"
          placeholder="Search agents..."
        >
        <span class="agent-count">{{ filteredAgentRows.length }} agent{{ filteredAgentRows.length !== 1 ? 's' : '' }}</span>
        <span v-if="hasSelected" class="sel-count">({{ selected.size }} selected)</span>
      </div>
      <div class="toolbar-right">
        <button class="btn sm" @click="selectAll">
          {{ selected.size === agentRows.length ? 'Deselect All' : 'Select All' }}
        </button>
        <button class="btn sm danger" :disabled="!hasSelected" @click="blockSelected">Block</button>
        <button class="btn sm" :disabled="!hasSelected" @click="unblockSelected">Unblock</button>
        <button class="btn sm danger" :disabled="!hasSelected" @click="pauseSelected">Pause</button>
      </div>
    </div>

    <!-- Agent Table -->
    <div class="table-wrap">
      <div v-if="!filteredAgentRows.length" class="empty-state">
        <div class="icon">&#9671;</div>
        <div class="text">{{ agentSearch ? 'No matching agents' : effectiveViewMode === 'maintainer' ? 'No agents across any server' : 'Select an AgentServer to view agents' }}</div>
      </div>
      <table v-else class="agent-table">
        <thead>
          <tr>
            <th class="col-check">
              <input type="checkbox" :checked="selected.size === agentRows.length && agentRows.length > 0" @change="selectAll">
            </th>
            <th class="col-status"></th>
            <th>Agent</th>
            <th>Role</th>
            <th v-if="effectiveViewMode === 'maintainer'">Server</th>
            <th class="col-lines">Lines</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredAgentRows"
            :key="`${row.server_id}/${row.agent_id}`"
            :class="{ selected: selected.has(`${row.server_id}/${row.agent_id}`) }"
            @click="toggleSelect(`${row.server_id}/${row.agent_id}`)"
          >
            <td class="col-check" @click.stop>
              <input
                type="checkbox"
                :checked="selected.has(`${row.server_id}/${row.agent_id}`)"
                @change="toggleSelect(`${row.server_id}/${row.agent_id}`)"
              >
            </td>
            <td class="col-status">
              <span class="status-dot" :class="row.status"></span>
            </td>
            <td class="col-agent">
              <span class="agent-icon" v-html="roleIcon(row.role)"></span>
              <span class="agent-name">{{ row.agent_id }}</span>
            </td>
            <td><span class="role-badge">{{ row.role }}</span></td>
            <td v-if="effectiveViewMode === 'maintainer'">
              <span class="server-badge" :class="{ alive: row.alive }">{{ row.server_id }}</span>
            </td>
            <td class="col-lines">{{ row.line_count }}</td>
            <td class="col-actions" @click.stop>
              <button class="btn xs" @click="openTerminal(row)" :disabled="!row.session_id" title="Open Terminal">
                &#9638;
              </button>
              <button class="btn xs danger" @click="emit('command', { action: 'block', agent_id: row.agent_id }, row.server_id)">
                Block
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.tab-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-bottom: 1px solid #21262d;
  background: #161b22; flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; }
.toolbar-right { display: flex; align-items: center; gap: 4px; }
.agent-search {
  padding: 4px 8px; font-size: 11px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #c9d1d9;
  font-family: 'JetBrains Mono', monospace;
  width: 180px;
}
.agent-search:focus { outline: none; border-color: #58a6ff; }
.agent-search::placeholder { color: #484f58; }
.agent-count { font-size: 12px; color: #8b949e; }
.sel-count { font-size: 11px; color: #58a6ff; }

.table-wrap { flex: 1; overflow-y: auto; }

.agent-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.agent-table th {
  text-align: left; padding: 6px 10px;
  font-size: 10px; color: #8b949e;
  text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 1px solid #21262d;
  background: #0d1117; position: sticky; top: 0; z-index: 1;
}
.agent-table td {
  padding: 8px 10px; border-bottom: 1px solid #21262d08;
  color: #c9d1d9;
}
.agent-table tr { cursor: pointer; transition: background 0.1s; }
.agent-table tr:hover { background: #161b22; }
.agent-table tr.selected { background: #0d419d22; }

.col-check { width: 32px; text-align: center; }
.col-check input { cursor: pointer; }
.col-status { width: 24px; }
.col-lines { width: 60px; text-align: right; color: #8b949e; font-family: monospace; }
.col-actions { width: 100px; }

.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #484f58;
}
.status-dot.active { background: #3fb950; }

.col-agent { display: flex; align-items: center; gap: 6px; }
.agent-icon { color: #58a6ff; font-size: 14px; }
.agent-name { font-weight: 500; color: #f0f6fc; font-family: 'JetBrains Mono', monospace; }

.role-badge {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  background: #21262d; color: #8b949e;
}
.server-badge {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  background: #21262d; color: #6e7681;
}
.server-badge.alive { color: #3fb950; background: #0d419d22; }

.btn {
  padding: 4px 10px; font-size: 11px; border: 1px solid #30363d;
  border-radius: 4px; background: #21262d; color: #c9d1d9;
  cursor: pointer; white-space: nowrap;
}
.btn:hover { border-color: #58a6ff; color: #58a6ff; }
.btn:disabled { opacity: 0.4; cursor: default; }
.btn:disabled:hover { border-color: #30363d; color: #c9d1d9; }
.btn.danger { border-color: #f85149; color: #f85149; }
.btn.danger:hover { background: #f8514922; }
.btn.sm { font-size: 10px; padding: 3px 8px; }
.btn.xs { font-size: 10px; padding: 2px 6px; }

.empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 8px; color: #484f58; padding: 40px;
}
.empty-state .icon { font-size: 32px; }
.empty-state .text { font-size: 13px; }
</style>
