<script setup lang="ts">
import { ref, computed } from 'vue'

interface AgentInfo {
  status?: string
  [key: string]: unknown
}

interface ServerInfo {
  server_id: string
  session_name?: string
  alive?: boolean
  info?: { host?: string; [key: string]: unknown }
  agents?: Record<string, AgentInfo>
}

const props = defineProps<{
  servers: ServerInfo[]
  selected?: string
}>()

const emit = defineEmits<{
  select: [serverId: string]
}>()

const searchQuery = ref('')

const filteredServers = computed(() => {
  const q = searchQuery.value.toLowerCase()
  if (!q) return props.servers
  return props.servers.filter((s) => {
    const haystack = [
      s.server_id,
      s.session_name || '',
      s.info?.host || '',
      ...Object.keys(s.agents || {}),
    ]
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
})

function truncate(s: string | undefined, len: number): string {
  if (!s) return ''
  return s.length > len ? s.slice(0, len) + '..' : s
}
</script>

<template>
  <div class="server-panel">
    <div class="panel-header">
      Agent Servers
      <span class="count">{{ filteredServers.length }}</span>
    </div>
    <div class="search-box">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="Search servers / users..."
      >
    </div>
    <div class="server-list">
      <div
        v-for="s in filteredServers"
        :key="s.server_id"
        class="server-item"
        :class="{ selected: selected === s.server_id }"
        @click="emit('select', s.server_id)"
      >
        <div class="srv-header">
          <div class="srv-dot" :class="s.alive ? 'alive' : 'dead'"></div>
          <div class="srv-id">{{ s.server_id }}</div>
          <div class="srv-session">{{ s.session_name || 'default' }}</div>
        </div>
        <div v-if="Object.keys(s.agents || {}).length" class="srv-agents">
          <span
            v-for="(info, aid) in s.agents"
            :key="String(aid)"
            class="agent-chip"
            :class="{ active: info.status === 'active' }"
          >{{ truncate(String(aid), 12) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.server-panel {
  width: 280px; flex-shrink: 0;
  background: #0d1117; border-right: 1px solid #30363d;
  display: flex; flex-direction: column;
}
.panel-header {
  padding: 10px 12px; font-size: 11px; font-weight: 600;
  color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 1px solid #21262d; display: flex; align-items: center; gap: 8px;
}
.count {
  background: #30363d; color: #c9d1d9; padding: 1px 6px;
  border-radius: 10px; font-size: 10px;
}
.search-box { padding: 6px 8px; border-bottom: 1px solid #21262d; }
.search-input {
  width: 100%; padding: 5px 8px; font-size: 11px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #c9d1d9;
  font-family: 'JetBrains Mono', monospace;
}
.search-input:focus { outline: none; border-color: #58a6ff; }
.search-input::placeholder { color: #484f58; }
.server-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.server-item {
  padding: 8px 12px; cursor: pointer; border-left: 3px solid transparent;
  transition: background 0.15s;
}
.server-item:hover { background: #161b22; }
.server-item.selected { background: #161b22; border-left-color: #58a6ff; }
.srv-header { display: flex; align-items: center; gap: 8px; }
.srv-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.srv-dot.alive { background: #3fb950; }
.srv-dot.dead { background: #f85149; }
.srv-id { font-size: 12px; font-weight: 500; color: #f0f6fc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.srv-session { font-size: 10px; color: #8b949e; margin-left: auto; }
.srv-agents { font-size: 11px; color: #8b949e; margin-top: 4px; padding-left: 14px; }
.agent-chip {
  display: inline-block; font-size: 10px; padding: 1px 6px;
  border-radius: 3px; margin: 1px 2px;
  background: #21262d; color: #c9d1d9;
}
.agent-chip.active { background: #0d419d; color: #a5d6ff; }
</style>
