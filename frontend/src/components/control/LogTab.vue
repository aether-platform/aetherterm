<script setup lang="ts">
import { ref, watch } from 'vue'

defineProps<{
  servers?: Record<string, unknown>
  timeline?: Array<Record<string, unknown>>
}>()

// Breadcrumb path segments
const path = ref<string[]>([])
const items = ref<Array<{ key: string }>>([])
const logLines = ref<string[]>([])
const loading = ref(false)

const levelLabels = ['Dates', 'Users', 'Sessions', 'Windows', 'Panes', 'Log']
const levelIcons = ['&#128197;', '&#9786;', '&#9635;', '&#9638;', '&#9654;', '&#9776;']

function enc(s: string): string {
  return encodeURIComponent(s)
}

// Fetch directory listing at current path
async function fetchItems() {
  loading.value = true
  logLines.value = []
  try {
    const p = path.value
    let url = ''
    if (p.length === 0) url = '/api/logs/dates'
    else if (p.length === 1) url = `/api/logs/${enc(p[0])}/users`
    else if (p.length === 2) url = `/api/logs/${enc(p[0])}/${enc(p[1])}/sessions`
    else if (p.length === 3) url = `/api/logs/${enc(p[0])}/${enc(p[1])}/${enc(p[2])}/windows`
    else if (p.length === 4) url = `/api/logs/${enc(p[0])}/${enc(p[1])}/${enc(p[2])}/${enc(p[3])}/panes`
    else if (p.length === 5) {
      // Fetch log content
      const resp = await fetch(
        `/api/logs/${enc(p[0])}/${enc(p[1])}/${enc(p[2])}/${enc(p[3])}/${enc(p[4])}?tail=500`,
      )
      const data = await resp.json()
      logLines.value = data.lines || []
      items.value = []
      loading.value = false
      return
    }

    if (url) {
      const resp = await fetch(url)
      const data = await resp.json()
      items.value = Array.isArray(data) ? data.map((d: string) => ({ key: d })) : []
    }
  } catch (e) {
    console.error('Log fetch error:', e)
    items.value = []
  }
  loading.value = false
}

function navigate(key: string) {
  path.value = [...path.value, key]
}

function goTo(index: number) {
  path.value = path.value.slice(0, index)
}

// Auto-fetch on path change
watch(path, fetchItems, { immediate: true, deep: true })

// Auto-refresh log content every 5s when viewing a pane
let refreshTimer: ReturnType<typeof setInterval> | null = null
watch(
  path,
  (p) => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
    if (p.length === 5) {
      refreshTimer = setInterval(fetchItems, 5000)
    }
  },
  { deep: true },
)
</script>

<template>
  <div class="log-tab">
    <!-- Breadcrumb -->
    <div class="breadcrumb">
      <span class="bc-item" @click="goTo(0)">
        <span class="bc-icon" v-html="levelIcons[0]"></span>
        Log
      </span>
      <template v-for="(seg, i) in path" :key="i">
        <span class="bc-sep">/</span>
        <span class="bc-item" @click="goTo(i + 1)">
          <span class="bc-icon" v-html="levelIcons[i + 1]"></span>
          {{ seg }}
        </span>
      </template>
      <span class="bc-level">{{ levelLabels[path.length] }}</span>
      <span v-if="loading" class="bc-loading">loading...</span>
    </div>

    <!-- Directory listing (depth 0-4) -->
    <div v-if="path.length < 5" class="dir-list">
      <div v-if="!items.length && !loading" class="empty-state">
        <div class="icon">&#128194;</div>
        <div class="text">No data at this level</div>
      </div>
      <div
        v-for="item in items"
        :key="item.key"
        class="dir-item"
        @click="navigate(item.key)"
      >
        <span class="dir-icon">&#128193;</span>
        <span class="dir-name">{{ item.key }}</span>
      </div>
    </div>

    <!-- Log content (depth 5) -->
    <div v-else class="log-view">
      <div class="log-header">
        <span class="log-path">{{ path.join('/') }}.log</span>
        <span class="log-count">{{ logLines.length }} lines</span>
      </div>
      <div class="log-entries">
        <div v-if="!logLines.length && !loading" class="empty-state">
          <div class="icon">&#9776;</div>
          <div class="text">No log entries</div>
        </div>
        <div v-for="(line, i) in logLines" :key="i" class="log-line">
          <span class="line-num">{{ i + 1 }}</span>
          <span class="line-text">{{ line }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-tab { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.breadcrumb {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 12px; background: #161b22;
  border-bottom: 1px solid #21262d; flex-shrink: 0;
  font-size: 12px; flex-wrap: wrap;
}
.bc-item {
  color: #58a6ff; cursor: pointer; display: flex; align-items: center; gap: 3px;
  padding: 2px 4px; border-radius: 3px;
}
.bc-item:hover { background: #21262d; }
.bc-icon { font-size: 12px; }
.bc-sep { color: #484f58; }
.bc-level {
  margin-left: auto; font-size: 10px; color: #6e7681;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.bc-loading { font-size: 10px; color: #d29922; margin-left: 8px; }

.dir-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.dir-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; cursor: pointer;
  border-bottom: 1px solid #21262d08;
  transition: background 0.1s;
}
.dir-item:hover { background: #161b22; }
.dir-icon { font-size: 16px; width: 20px; text-align: center; }
.dir-name {
  font-size: 13px; font-weight: 500; color: #f0f6fc;
  font-family: 'JetBrains Mono', monospace;
}

.log-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.log-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px; background: #161b22;
  border-bottom: 1px solid #21262d; flex-shrink: 0;
  font-size: 11px;
}
.log-path { color: #8b949e; font-family: 'JetBrains Mono', monospace; }
.log-count { color: #6e7681; }

.log-entries {
  flex: 1; overflow-y: auto; padding: 0;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace;
  font-size: 11px; line-height: 1.6;
}
.log-line {
  display: flex; padding: 0 8px;
  border-bottom: 1px solid #21262d08;
}
.log-line:hover { background: #161b2288; }
.line-num {
  width: 40px; text-align: right; padding-right: 8px;
  color: #484f58; flex-shrink: 0;
  user-select: none; border-right: 1px solid #21262d;
  margin-right: 8px;
}
.line-text { color: #c9d1d9; white-space: pre-wrap; word-break: break-all; }

.empty-state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 8px; color: #484f58; padding: 40px;
}
.empty-state .icon { font-size: 32px; }
.empty-state .text { font-size: 13px; }
</style>
