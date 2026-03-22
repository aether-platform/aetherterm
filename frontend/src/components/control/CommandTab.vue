<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'

interface AgentInfo {
  role?: string
  status?: string
  line_count?: number
  session_id?: string
  pane_id?: string
  [key: string]: unknown
}

interface ServerInfo {
  server_id: string
  agents?: Record<string, AgentInfo>
  [key: string]: unknown
}

interface AgentOption {
  agent_id: string
  role?: string
  status?: string
  line_count?: number
  session_id?: string
  pane_id?: string
}

const THEME = {
  background: '#0d1117',
  foreground: '#c9d1d9',
  cursor: '#58a6ff',
  selectionBackground: '#264f78',
  black: '#484f58',
  red: '#ff7b72',
  green: '#3fb950',
  yellow: '#d29922',
  blue: '#58a6ff',
  magenta: '#bc8cff',
  cyan: '#39d353',
  white: '#f0f6fc',
}

const props = defineProps<{
  server?: ServerInfo | null
}>()

const emit = defineEmits<{
  command: [command: Record<string, unknown>]
}>()

const termRef = ref<HTMLElement | null>(null)
const selectedAgent = ref('')
const injectInput = ref('')

// Terminal proxy state
const terminalActive = ref(false)
let term: Terminal | null = null
let fitAddon: FitAddon | null = null
let ws: WebSocket | null = null

const agents = computed<AgentOption[]>(() => {
  if (!props.server?.agents) return []
  return Object.entries(props.server.agents).map(([aid, info]) => ({
    agent_id: aid,
    ...info,
  }))
})

const selectedAgentInfo = computed(() =>
  agents.value.find((a) => a.agent_id === selectedAgent.value),
)

// Terminal proxy functions
function openTerminal(container: HTMLElement, serverId: string, sessionId: string) {
  closeTerminal()

  term = new Terminal({
    fontSize: 12,
    fontFamily: "'JetBrains Mono','Cascadia Code','Fira Code',Menlo,monospace",
    theme: THEME,
    cursorBlink: true,
    scrollback: 3000,
    disableStdin: false,
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.loadAddon(new WebLinksAddon())

  term.open(container)

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const cols = term.cols
  const rows = term.rows
  ws = new WebSocket(
    `${proto}//${location.host}/ws/terminal/${serverId}/${sessionId}?cols=${cols}&rows=${rows}`,
  )
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    terminalActive.value = true
    requestAnimationFrame(() => {
      try {
        fitAddon?.fit()
        ws?.send(JSON.stringify({ type: 'resize', cols: term?.cols, rows: term?.rows }))
      } catch {
        // ignore fit errors
      }
    })
  }

  ws.onmessage = (evt) => {
    if (evt.data instanceof ArrayBuffer) {
      term?.write(new Uint8Array(evt.data))
    } else {
      try {
        const m = JSON.parse(evt.data)
        if (m.type === 'exit') term?.write('\r\n\x1b[90m[exited]\x1b[0m\r\n')
      } catch {
        term?.write(evt.data)
      }
    }
  }

  ws.onclose = () => {
    terminalActive.value = false
    if (term) term.write('\r\n\x1b[90m[disconnected]\x1b[0m\r\n')
  }

  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(data))
  })

  term.onResize(({ cols, rows }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    }
  })
}

function sendTerminalInput(text: string) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(new TextEncoder().encode(text))
  }
}

function closeTerminal() {
  if (ws) { try { ws.close() } catch { /* ignore */ } }
  if (term) { try { term.dispose() } catch { /* ignore */ } }
  ws = null
  term = null
  fitAddon = null
  terminalActive.value = false
}

// When agent selection changes, connect terminal
watch(selectedAgent, async (aid) => {
  closeTerminal()
  if (!aid || !props.server) return
  const info = props.server.agents?.[aid]
  if (!info?.session_id) return
  await nextTick()
  if (termRef.value) {
    openTerminal(termRef.value, props.server.server_id, info.session_id)
  }
})

// Disconnect when server changes
watch(
  () => props.server?.server_id,
  () => {
    closeTerminal()
    selectedAgent.value = ''
  },
)

function sendInject() {
  if (!selectedAgent.value || !injectInput.value) return
  const info = props.server?.agents?.[selectedAgent.value]
  emit('command', {
    action: 'inject',
    agent_id: selectedAgent.value,
    pane_id: info?.pane_id ?? '',
    input: injectInput.value,
  })
  sendTerminalInput(injectInput.value)
  injectInput.value = ''
}

function sendInjectEnter() {
  if (!selectedAgent.value || !injectInput.value) return
  const info = props.server?.agents?.[selectedAgent.value]
  const text = injectInput.value + '\r'
  emit('command', {
    action: 'inject',
    agent_id: selectedAgent.value,
    pane_id: info?.pane_id ?? '',
    input: text,
  })
  sendTerminalInput(text)
  injectInput.value = ''
}

onUnmounted(closeTerminal)
</script>

<template>
  <div class="tab-content">
    <div v-if="!server" class="empty-state">
      <div class="icon">&#9881;</div>
      <div class="text">Select an AgentServer to send commands</div>
    </div>
    <template v-else>
      <!-- Agent Selector -->
      <div class="cmd-header">
        <label class="cmd-label">Target Agent</label>
        <select v-model="selectedAgent" class="agent-select">
          <option value="">-- Select Agent --</option>
          <option v-for="a in agents" :key="a.agent_id" :value="a.agent_id">
            {{ a.agent_id }} ({{ a.role }})
          </option>
        </select>
        <span v-if="selectedAgentInfo" class="agent-meta">
          <span class="status-dot" :class="selectedAgentInfo.status"></span>
          {{ selectedAgentInfo.line_count || 0 }} lines
        </span>
      </div>

      <!-- Terminal Preview -->
      <div class="terminal-area" :class="{ empty: !selectedAgent }">
        <div v-if="!selectedAgent" class="term-placeholder">
          <div class="placeholder-icon">&#9638;</div>
          <div>Select an agent to view its terminal</div>
        </div>
        <div v-else-if="!selectedAgentInfo?.session_id" class="term-placeholder">
          <div class="placeholder-icon">&#9888;</div>
          <div>No terminal session for this agent</div>
        </div>
        <div v-else class="term-container" ref="termRef"></div>
        <div v-if="terminalActive" class="term-status">
          <span class="live-dot"></span> LIVE
        </div>
      </div>

      <!-- Injection Input -->
      <div class="inject-bar" v-if="selectedAgent">
        <input
          v-model="injectInput"
          class="inject-input"
          placeholder="Type command to inject..."
          @keydown.enter.exact="sendInjectEnter"
          @keydown.shift.enter="sendInject"
          :disabled="!selectedAgentInfo?.session_id"
        >
        <button class="btn primary" @click="sendInjectEnter" :disabled="!injectInput">
          Send &#8629;
        </button>
        <button class="btn" @click="sendInject" :disabled="!injectInput" title="Send without Enter">
          Raw
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tab-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

.cmd-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid #21262d;
  background: #161b22; flex-shrink: 0;
}
.cmd-label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }
.agent-select {
  padding: 5px 8px; font-size: 12px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #c9d1d9;
  font-family: 'JetBrains Mono', monospace;
  min-width: 200px;
}
.agent-select:focus { outline: none; border-color: #58a6ff; }
.agent-meta { font-size: 11px; color: #8b949e; margin-left: auto; display: flex; align-items: center; gap: 6px; }
.status-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #484f58;
}
.status-dot.active { background: #3fb950; }

.terminal-area {
  flex: 1; overflow: hidden; position: relative;
  background: #0d1117; min-height: 200px;
}
.terminal-area.empty { display: flex; align-items: center; justify-content: center; }
.term-placeholder {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  color: #484f58; font-size: 13px;
}
.placeholder-icon { font-size: 32px; }
.term-container { width: 100%; height: 100%; padding: 4px; }
.term-container :deep(.xterm) { height: 100%; }
.term-container :deep(.xterm-screen) { height: 100%; }

.term-status {
  position: absolute; top: 8px; right: 12px;
  font-size: 10px; color: #3fb950; display: flex; align-items: center; gap: 4px;
  background: #0d1117cc; padding: 2px 8px; border-radius: 3px;
}
.live-dot {
  width: 6px; height: 6px; border-radius: 50%; background: #3fb950;
  animation: pulse-glow 2s ease-in-out infinite;
}
@keyframes pulse-glow {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; box-shadow: 0 0 6px #3fb950; }
}

.inject-bar {
  display: flex; gap: 6px; padding: 8px 12px;
  border-top: 1px solid #21262d; background: #161b22; flex-shrink: 0;
}
.inject-input {
  flex: 1; padding: 7px 10px; font-size: 13px;
  border: 1px solid #30363d; border-radius: 4px;
  background: #0d1117; color: #c9d1d9;
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
}
.inject-input:focus { outline: none; border-color: #58a6ff; }
.inject-input:disabled { opacity: 0.4; }

.btn {
  padding: 6px 12px; font-size: 11px; border: 1px solid #30363d;
  border-radius: 4px; background: #21262d; color: #c9d1d9;
  cursor: pointer; white-space: nowrap;
}
.btn:hover { border-color: #58a6ff; color: #58a6ff; }
.btn:disabled { opacity: 0.4; cursor: default; }
.btn:disabled:hover { border-color: #30363d; color: #c9d1d9; }
.btn.primary { background: #238636; border-color: #238636; color: #fff; }
.btn.primary:hover { background: #2ea043; }

.empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 8px; color: #484f58;
}
.empty-state .icon { font-size: 32px; }
.empty-state .text { font-size: 13px; }
</style>
