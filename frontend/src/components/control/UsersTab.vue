<script setup lang="ts">
import { ref, computed } from 'vue'

interface AgentInfo {
  role?: string
  status?: string
  line_count?: number
  [key: string]: unknown
}

interface ServerInfo {
  server_id: string
  alive: boolean
  session_name?: string
  last_heartbeat?: number
  info?: { host?: string; port?: number | string; [key: string]: unknown }
  agents?: Record<string, AgentInfo>
}

interface UserAgentRow {
  agent_id: string
  server_id: string
  role: string
  status: string
  line_count: number
}

interface UserEntry {
  username: string
  servers: ServerInfo[]
  agents: UserAgentRow[]
  hosts: Set<string>
  lastSeen: number
  allAlive: boolean
}

const props = defineProps<{
  servers?: Record<string, ServerInfo>
}>()

const emit = defineEmits<{
  'select-server': [serverId: string]
  command: [command: Record<string, unknown>, serverId: string]
}>()

const searchQuery = ref('')
const expandedUser = ref<string | null>(null)

// Extract users from servers (same logic as backend _extract_username)
function extractUsername(serverId: string): string {
  if (serverId.includes('@')) {
    const left = serverId.split('@')[0]
    return left.includes('.') ? left.split('.').slice(1).join('.') : left
  }
  if (serverId.startsWith('user.')) return serverId.slice(5)
  if (serverId.startsWith('host.')) return serverId.slice(5)
  return serverId
}

function extractHostname(serverId: string): string {
  if (serverId.includes('@')) {
    const right = serverId.split('@')[1]
    return right.includes('.') ? right.split('.').slice(1).join('.') : right
  }
  if (serverId.startsWith('host.')) return serverId.slice(5)
  return ''
}

const users = computed<UserEntry[]>(() => {
  const map: Record<string, UserEntry> = {}
  for (const srv of Object.values(props.servers ?? {})) {
    const username = extractUsername(srv.server_id)
    const hostname = extractHostname(srv.server_id)
    if (!map[username]) {
      map[username] = {
        username,
        servers: [],
        agents: [],
        hosts: new Set(),
        lastSeen: 0,
        allAlive: true,
      }
    }
    const u = map[username]
    u.servers.push(srv)
    u.lastSeen = Math.max(u.lastSeen, srv.last_heartbeat ?? 0)
    if (!srv.alive) u.allAlive = false
    if (hostname) u.hosts.add(hostname)
    for (const [aid, info] of Object.entries(srv.agents ?? {})) {
      u.agents.push({
        agent_id: aid,
        server_id: srv.server_id,
        role: info.role ?? 'unknown',
        status: info.status ?? 'unknown',
        line_count: info.line_count ?? 0,
      })
    }
  }
  return Object.values(map).sort((a, b) => b.lastSeen - a.lastSeen)
})

const filteredUsers = computed(() => {
  const q = searchQuery.value.toLowerCase()
  if (!q) return users.value
  return users.value.filter((u) => {
    const haystack = [
      u.username,
      ...Array.from(u.hosts),
      ...u.servers.map((s) => s.server_id),
      ...u.agents.map((a) => a.agent_id),
      ...u.agents.map((a) => a.role),
    ]
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
})

function toggleExpand(username: string) {
  expandedUser.value = expandedUser.value === username ? null : username
}

function blockUser(user: UserEntry) {
  for (const srv of user.servers) {
    emit('command', { action: 'block_all' }, srv.server_id)
  }
}

function unblockUser(user: UserEntry) {
  for (const srv of user.servers) {
    emit('command', { action: 'unblock_all' }, srv.server_id)
  }
}

function relativeTime(ts: number): string {
  if (!ts) return '--'
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
</script>

<template>
  <div class="tab-content">
    <div class="toolbar">
      <div class="toolbar-left">
        <input
          v-model="searchQuery"
          class="user-search"
          placeholder="Search users / hosts / agents..."
        >
        <span class="user-count">{{ filteredUsers.length }} user{{ filteredUsers.length !== 1 ? 's' : '' }}</span>
      </div>
    </div>

    <div class="user-list">
      <div v-if="!filteredUsers.length" class="empty-state">
        <div class="icon">&#9786;</div>
        <div class="text">{{ searchQuery ? 'No matching users' : 'No users connected' }}</div>
      </div>

      <div
        v-for="user in filteredUsers"
        :key="user.username"
        class="user-card"
        :class="{ expanded: expandedUser === user.username }"
      >
        <!-- User header row -->
        <div class="user-header" @click="toggleExpand(user.username)">
          <span class="user-status" :class="{ alive: user.allAlive }"></span>
          <span class="user-name">{{ user.username }}</span>
          <span class="user-meta">
            <span class="badge">{{ user.servers.length }} server{{ user.servers.length !== 1 ? 's' : '' }}</span>
            <span class="badge">{{ user.agents.length }} agent{{ user.agents.length !== 1 ? 's' : '' }}</span>
            <span v-for="h in user.hosts" :key="h" class="badge host">{{ h }}</span>
          </span>
          <span class="user-seen">{{ relativeTime(user.lastSeen) }}</span>
          <div class="user-actions" @click.stop>
            <button class="btn xs danger" @click="blockUser(user)" title="Block all">Block</button>
            <button class="btn xs" @click="unblockUser(user)" title="Unblock all">Unblock</button>
          </div>
          <span class="expand-icon" v-html="expandedUser === user.username ? '&#9660;' : '&#9654;'"></span>
        </div>

        <!-- Expanded detail -->
        <div v-if="expandedUser === user.username" class="user-detail">
          <!-- Servers -->
          <div class="detail-section">
            <div class="section-label">Servers</div>
            <div
              v-for="srv in user.servers"
              :key="srv.server_id"
              class="server-row"
              @click="emit('select-server', srv.server_id)"
            >
              <span class="srv-dot" :class="srv.alive ? 'alive' : 'dead'"></span>
              <span class="srv-name">{{ srv.server_id }}</span>
              <span class="srv-session">{{ srv.session_name || 'default' }}</span>
              <span class="srv-host">{{ srv.info?.host || '' }}:{{ srv.info?.port || '' }}</span>
            </div>
          </div>

          <!-- Agents -->
          <div v-if="user.agents.length" class="detail-section">
            <div class="section-label">Agents</div>
            <div
              v-for="a in user.agents"
              :key="`${a.server_id}/${a.agent_id}`"
              class="agent-row"
            >
              <span class="agent-dot" :class="a.status || 'unknown'"></span>
              <span class="agent-name">{{ a.agent_id }}</span>
              <span class="role-badge">{{ a.role || 'unknown' }}</span>
              <span class="agent-server">{{ a.server_id }}</span>
              <span class="agent-lines">{{ a.line_count || 0 }} lines</span>
            </div>
          </div>
        </div>
      </div>
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
.user-search {
  padding: 5px 8px; font-size: 11px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #c9d1d9;
  font-family: 'JetBrains Mono', monospace;
  width: 260px;
}
.user-search:focus { outline: none; border-color: #58a6ff; }
.user-search::placeholder { color: #484f58; }
.user-count { font-size: 12px; color: #8b949e; }

.user-list { flex: 1; overflow-y: auto; padding: 4px 0; }

.user-card {
  border-bottom: 1px solid #21262d;
  transition: background 0.1s;
}
.user-card:hover { background: #161b2288; }
.user-card.expanded { background: #161b22; }

.user-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; cursor: pointer;
}
.user-status {
  width: 8px; height: 8px; border-radius: 50%;
  background: #f85149; flex-shrink: 0;
}
.user-status.alive { background: #3fb950; }
.user-name {
  font-size: 13px; font-weight: 600; color: #f0f6fc;
  font-family: 'JetBrains Mono', monospace;
  min-width: 120px;
}
.user-meta { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
.badge {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  background: #21262d; color: #8b949e;
}
.badge.host { background: #0d419d22; color: #a5d6ff; }
.user-seen { font-size: 10px; color: #6e7681; min-width: 60px; text-align: right; }
.user-actions { display: flex; gap: 4px; }
.expand-icon { font-size: 10px; color: #484f58; width: 12px; text-align: center; }

.user-detail {
  padding: 0 12px 10px 28px;
}
.detail-section { margin-bottom: 8px; }
.section-label {
  font-size: 10px; color: #8b949e; text-transform: uppercase;
  letter-spacing: 0.5px; margin-bottom: 4px; padding: 2px 0;
  border-bottom: 1px solid #21262d;
}

.server-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 8px; border-radius: 4px;
  cursor: pointer; font-size: 11px;
}
.server-row:hover { background: #21262d; }
.srv-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.srv-dot.alive { background: #3fb950; }
.srv-dot.dead { background: #f85149; }
.srv-name { color: #f0f6fc; font-weight: 500; font-family: 'JetBrains Mono', monospace; }
.srv-session { color: #8b949e; }
.srv-host { color: #6e7681; margin-left: auto; font-family: monospace; }

.agent-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 8px; font-size: 11px;
}
.agent-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #484f58; flex-shrink: 0;
}
.agent-dot.active { background: #3fb950; }
.agent-name { color: #f0f6fc; font-family: 'JetBrains Mono', monospace; font-weight: 500; }
.role-badge {
  font-size: 10px; padding: 1px 5px; border-radius: 3px;
  background: #21262d; color: #8b949e;
}
.agent-server { color: #6e7681; font-size: 10px; }
.agent-lines { color: #6e7681; font-size: 10px; margin-left: auto; font-family: monospace; }

.btn {
  padding: 4px 10px; font-size: 11px; border: 1px solid #30363d;
  border-radius: 4px; background: #21262d; color: #c9d1d9;
  cursor: pointer; white-space: nowrap;
}
.btn:hover { border-color: #58a6ff; color: #58a6ff; }
.btn.xs { font-size: 10px; padding: 2px 6px; }
.btn.danger { border-color: #f85149; color: #f85149; }
.btn.danger:hover { background: #f8514922; }

.empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 8px; color: #484f58; padding: 40px;
}
.empty-state .icon { font-size: 32px; }
.empty-state .text { font-size: 13px; }
</style>
