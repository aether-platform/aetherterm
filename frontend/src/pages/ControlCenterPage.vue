<template>
  <div class="control-center">
    <!-- Hero / Welcome section -->
    <div class="hero-section">
      <div class="hero-content">
        <h1 class="hero-title">AetherTerm</h1>
        <p class="hero-subtitle">AI-Powered Terminal Workspace</p>
      </div>
      <div class="hero-actions">
        <button @click="createNewSession" class="primary-btn">
          <span class="btn-icon">+</span>
          New Session
        </button>
        <button @click="refreshAll" :disabled="isLoading" class="secondary-btn">
          <span class="btn-icon" :class="{ spinning: isLoading }">&#8635;</span>
          {{ isLoading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Connection status -->
    <div v-if="error" class="status-banner error">
      <span class="banner-icon">!</span>
      <span>{{ error }}</span>
      <button @click="error = null" class="banner-dismiss">&times;</button>
    </div>

    <!-- Quick stats -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon pty-icon">&gt;_</div>
        <div class="stat-body">
          <div class="stat-value">{{ ptySessions.length }}</div>
          <div class="stat-label">PTY Sessions</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon tmux-icon">&#9638;</div>
        <div class="stat-body">
          <div class="stat-value">{{ tmuxSessions.length }}</div>
          <div class="stat-label">Tmux Sessions</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon control-icon">&#9881;</div>
        <div class="stat-body">
          <div class="stat-value" :class="controlStatus.connected ? 'text-green' : 'text-muted'">
            {{ controlStatus.connected ? 'Online' : 'Offline' }}
          </div>
          <div class="stat-label">ControlServer</div>
        </div>
      </div>
    </div>

    <!-- Keyboard shortcuts hint -->
    <div class="shortcuts-hint">
      <span class="hint-label">Shortcuts</span>
      <div class="shortcut-chips">
        <span class="chip"><kbd>Ctrl+B</kbd> prefix</span>
        <span class="chip"><kbd>"</kbd> hsplit</span>
        <span class="chip"><kbd>%</kbd> vsplit</span>
        <span class="chip"><kbd>c</kbd> new window</span>
        <span class="chip"><kbd>d</kbd> detach</span>
        <span class="chip"><kbd>z</kbd> zoom</span>
        <span class="chip"><kbd>[</kbd> copy mode</span>
      </div>
    </div>

    <!-- Tmux Sessions -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">Tmux Sessions</h2>
        <span class="section-count">{{ tmuxSessions.length }}</span>
      </div>

      <div v-if="tmuxSessions.length === 0" class="empty-state">
        <div class="empty-icon">&#9638;</div>
        <div class="empty-text">No active tmux sessions</div>
        <button @click="createNewSession" class="empty-action">Create your first session</button>
      </div>

      <div v-else class="session-grid">
        <div
          v-for="sess in tmuxSessions"
          :key="sess.session_id"
          class="session-card"
          @click="connectToTmuxSession(sess.session_id)"
        >
          <div class="card-header">
            <span class="card-name">{{ sess.name }}</span>
            <span class="card-badge active">active</span>
          </div>
          <div class="card-meta">
            <span class="meta-item">
              <span class="meta-icon">&#9632;</span>
              {{ Object.keys(sess.windows || {}).length }} windows
            </span>
            <span class="meta-item">
              <span class="meta-icon">&#9684;</span>
              {{ sess.active_clients }} clients
            </span>
          </div>
          <div class="card-footer">
            <span class="card-id">{{ sess.session_id.slice(0, 8) }}</span>
            <span class="card-time">{{ formatTimestamp(sess.created_at) }}</span>
          </div>
          <div class="card-actions" @click.stop>
            <button
              @click="deleteTmuxSession(sess.session_id)"
              class="card-action-btn danger"
              title="Terminate session"
            >
              &times;
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- PTY Sessions -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">PTY Sessions</h2>
        <span class="section-count">{{ ptySessions.length }}</span>
      </div>

      <div v-if="ptySessions.length === 0" class="empty-state compact">
        <div class="empty-text">No active PTY sessions</div>
      </div>

      <div v-else class="session-list">
        <div
          v-for="session in ptySessions"
          :key="session.id"
          class="session-row"
        >
          <div class="row-info">
            <span class="row-id">{{ session.id }}</span>
            <span class="row-badge" :class="session.status">{{ session.status }}</span>
          </div>
          <div class="row-meta">
            <span>PID: {{ session.pid }}</span>
            <span>{{ formatDate(session.created_at) }}</span>
          </div>
          <div class="row-actions">
            <button @click="connectToSession(session.id)" class="row-btn connect">Connect</button>
            <button @click="deleteSession(session.id)" class="row-btn danger">Kill</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-refresh indicator -->
    <div class="refresh-indicator" v-if="autoRefreshActive">
      <span class="refresh-dot"></span>
      Auto-refreshing every 10s
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onUnmounted, ref } from 'vue'
  import { useRouter } from 'vue-router'

  interface PtySession {
    id: string
    pid: number | null
    status: string
    created_at: string
  }

  interface TmuxSession {
    session_id: string
    name: string
    created_at: number
    windows: Record<string, unknown>
    active_clients: number
  }

  const router = useRouter()
  const ptySessions = ref<PtySession[]>([])
  const tmuxSessions = ref<TmuxSession[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const autoRefreshActive = ref(true)
  const controlStatus = ref({ connected: false, sessions: 0 })
  let refreshTimer: ReturnType<typeof setInterval> | null = null

  const fetchPtySessions = async () => {
    try {
      const response = await fetch('/api/pty')
      if (!response.ok) throw new Error('Failed to fetch PTY sessions')
      ptySessions.value = await response.json()
    } catch (err: any) {
      error.value = err.message
    }
  }

  const fetchTmuxSessions = async () => {
    try {
      const response = await fetch('/api/tmux/sessions')
      if (!response.ok) throw new Error('Failed to fetch tmux sessions')
      tmuxSessions.value = await response.json()
    } catch {
      tmuxSessions.value = []
    }
  }

  const fetchControlStatus = async () => {
    try {
      const response = await fetch('/api/control/status')
      if (response.ok) {
        controlStatus.value = await response.json()
      }
    } catch {
      controlStatus.value = { connected: false, sessions: 0 }
    }
  }

  const refreshAll = async () => {
    isLoading.value = true
    error.value = null
    await Promise.all([fetchPtySessions(), fetchTmuxSessions(), fetchControlStatus()])
    isLoading.value = false
  }

  const deleteSession = async (id: string) => {
    if (!confirm(`Terminate PTY session ${id}?`)) return
    try {
      const response = await fetch(`/api/pty/${id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Failed to delete session')
      await fetchPtySessions()
    } catch (err: any) {
      alert(err.message)
    }
  }

  const deleteTmuxSession = async (id: string) => {
    if (!confirm(`Terminate tmux session?`)) return
    try {
      const response = await fetch(`/api/tmux/sessions/${id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Failed to terminate tmux session')
      await fetchTmuxSessions()
    } catch (err: any) {
      alert(err.message)
    }
  }

  const connectToSession = (id: string) => {
    router.push(`/tmux/${id}`)
  }

  const connectToTmuxSession = (id: string) => {
    router.push(`/tmux/${id}`)
  }

  const createNewSession = () => {
    router.push('/tmux/_new')
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString()
    } catch {
      return dateStr
    }
  }

  const formatTimestamp = (ts: number) => {
    try {
      return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return String(ts)
    }
  }

  onMounted(() => {
    refreshAll()
    refreshTimer = setInterval(refreshAll, 10000)
  })

  onUnmounted(() => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  })
</script>

<style scoped>
  .control-center {
    padding: 32px 40px;
    color: #e0e0e0;
    max-width: 960px;
    margin: 0 auto;
    min-height: 100%;
    overflow-y: auto;
  }

  /* Hero */
  .hero-section {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .hero-title {
    font-size: 28px;
    font-weight: 800;
    margin: 0;
    background: linear-gradient(135deg, #fff 0%, #4caf50 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }

  .hero-subtitle {
    font-size: 13px;
    color: #666;
    margin: 4px 0 0;
  }

  .hero-actions {
    display: flex;
    gap: 8px;
  }

  .primary-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #4caf50;
    color: #fff;
    border: none;
    padding: 8px 18px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
  }

  .primary-btn:hover {
    background: #43a047;
    box-shadow: 0 4px 16px rgba(76, 175, 80, 0.4);
    transform: translateY(-1px);
  }

  .secondary-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.06);
    color: #aaa;
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .secondary-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: #ddd;
  }

  .btn-icon {
    font-size: 16px;
    line-height: 1;
  }

  .spinning {
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Status banner */
  .status-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 8px;
    margin-bottom: 24px;
    font-size: 13px;
  }

  .status-banner.error {
    background: rgba(244, 67, 54, 0.08);
    border: 1px solid rgba(244, 67, 54, 0.3);
    color: #f44336;
  }

  .banner-icon {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(244, 67, 54, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
  }

  .banner-dismiss {
    margin-left: auto;
    background: none;
    border: none;
    color: inherit;
    font-size: 16px;
    cursor: pointer;
    opacity: 0.6;
  }

  /* Stats */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 24px;
  }

  .stat-card {
    display: flex;
    align-items: center;
    gap: 14px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 16px;
    transition: all 0.2s;
  }

  .stat-card:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
  }

  .stat-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }

  .pty-icon {
    background: rgba(99, 102, 241, 0.12);
    color: #818cf8;
    font-family: monospace;
    font-weight: 700;
  }

  .tmux-icon {
    background: rgba(76, 175, 80, 0.12);
    color: #4caf50;
  }

  .control-icon {
    background: rgba(255, 152, 0, 0.12);
    color: #ff9800;
  }

  .stat-value {
    font-size: 20px;
    font-weight: 700;
    color: #fff;
  }

  .stat-label {
    font-size: 11px;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .text-green { color: #4caf50; }
  .text-muted { color: #666; }

  /* Shortcuts hint */
  .shortcuts-hint {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    margin-bottom: 28px;
    overflow-x: auto;
  }

  .hint-label {
    font-size: 10px;
    font-weight: 700;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    flex-shrink: 0;
  }

  .shortcut-chips {
    display: flex;
    gap: 8px;
    flex-wrap: nowrap;
  }

  .chip {
    font-size: 11px;
    color: #888;
    white-space: nowrap;
  }

  kbd {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    padding: 1px 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: #bbb;
  }

  /* Sections */
  .section {
    margin-bottom: 32px;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
  }

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0;
  }

  .section-count {
    font-size: 11px;
    color: #555;
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 10px;
  }

  /* Session grid (tmux) */
  .session-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .session-card {
    position: relative;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .session-card:hover {
    background: rgba(76, 175, 80, 0.05);
    border-color: rgba(76, 175, 80, 0.2);
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }

  .card-name {
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    font-family: 'JetBrains Mono', monospace;
  }

  .card-badge {
    font-size: 9px;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.3px;
  }

  .card-badge.active {
    background: rgba(76, 175, 80, 0.15);
    color: #4caf50;
  }

  .card-meta {
    display: flex;
    gap: 16px;
    margin-bottom: 10px;
  }

  .meta-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #888;
  }

  .meta-icon {
    font-size: 10px;
    opacity: 0.5;
  }

  .card-footer {
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #555;
  }

  .card-id {
    font-family: monospace;
  }

  .card-actions {
    position: absolute;
    top: 8px;
    right: 8px;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .session-card:hover .card-actions {
    opacity: 1;
  }

  .card-action-btn {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .card-action-btn.danger {
    background: rgba(244, 67, 54, 0.1);
    color: #f44336;
  }

  .card-action-btn.danger:hover {
    background: rgba(244, 67, 54, 0.25);
  }

  /* Session list (PTY) */
  .session-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .session-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    padding: 10px 14px;
    transition: all 0.15s;
  }

  .session-row:hover {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.1);
  }

  .row-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .row-id {
    font-family: monospace;
    font-weight: 600;
    font-size: 13px;
    color: #ddd;
  }

  .row-badge {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 8px;
    text-transform: uppercase;
    background: rgba(255, 255, 255, 0.06);
    color: #888;
  }

  .row-badge.running {
    background: rgba(76, 175, 80, 0.15);
    color: #4caf50;
  }

  .row-meta {
    display: flex;
    gap: 16px;
    font-size: 11px;
    color: #666;
  }

  .row-actions {
    display: flex;
    gap: 6px;
  }

  .row-btn {
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.15s;
  }

  .row-btn.connect {
    background: rgba(76, 175, 80, 0.12);
    color: #4caf50;
  }

  .row-btn.connect:hover {
    background: rgba(76, 175, 80, 0.25);
  }

  .row-btn.danger {
    background: rgba(244, 67, 54, 0.08);
    color: #f44336;
  }

  .row-btn.danger:hover {
    background: rgba(244, 67, 54, 0.2);
  }

  /* Empty state */
  .empty-state {
    text-align: center;
    padding: 48px 24px;
    border: 1px dashed rgba(255, 255, 255, 0.08);
    border-radius: 12px;
  }

  .empty-state.compact {
    padding: 24px;
  }

  .empty-icon {
    font-size: 32px;
    opacity: 0.15;
    margin-bottom: 12px;
  }

  .empty-text {
    font-size: 13px;
    color: #555;
    margin-bottom: 16px;
  }

  .empty-action {
    background: rgba(76, 175, 80, 0.12);
    color: #4caf50;
    border: 1px solid rgba(76, 175, 80, 0.2);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }

  .empty-action:hover {
    background: rgba(76, 175, 80, 0.2);
    border-color: rgba(76, 175, 80, 0.4);
  }

  /* Auto-refresh indicator */
  .refresh-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    color: #444;
    justify-content: center;
    padding-top: 16px;
  }

  .refresh-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #4caf50;
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }

  /* Responsive */
  @media (max-width: 640px) {
    .control-center {
      padding: 20px 16px;
    }
    .hero-section {
      flex-direction: column;
      gap: 16px;
      align-items: flex-start;
    }
    .stats-row {
      grid-template-columns: 1fr;
    }
    .session-grid {
      grid-template-columns: 1fr;
    }
    .shortcuts-hint {
      display: none;
    }
  }
</style>
