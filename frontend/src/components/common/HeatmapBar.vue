<script setup lang="ts">
/**
 * HeatmapBar - Horizontal activity heatmap bar for pane overview.
 *
 * Displays pane role badges with line-count indicators in a horizontal strip.
 * Used in float layout mode to show agent activity at a glance.
 *
 * Ported from: poc/aetherterm-poc/frontend/src/components/HeatmapBar.vue
 */

import { useTmuxStore } from '../../stores/tmuxStore'

const ROLE_COLORS: Record<string, string> = {
  claude: '#238636', codex: '#10a37f', opencode: '#8b5cf6', gemini: '#4285f4',
  coder: '#238636', reviewer: '#1f6feb', tester: '#8957e5',
  shell: '#484f58', parent: '#1f6feb', default: '#6e7681',
}

const ROLE_KEYS = ['coder', 'reviewer', 'tester', 'shell', 'parent', 'claude', 'codex', 'opencode', 'gemini']

function roleColor(title: string): string {
  const t = (title || '').toLowerCase()
  for (const [r, c] of Object.entries(ROLE_COLORS)) {
    if (t.includes(r)) return c
  }
  return ROLE_COLORS.default
}

function roleName(title: string): string {
  const t = (title || '').toLowerCase()
  for (const r of ROLE_KEYS) {
    if (t.includes(r)) return r
  }
  return 'window'
}

export interface HeatmapPane {
  pane_id: string
  title: string
}

const props = defineProps<{
  panes: HeatmapPane[]
  activePaneId: string
}>()

const emit = defineEmits<{
  'select-pane': [paneId: string]
}>()

const tmuxStore = useTmuxStore()

function getLineCount(paneId: string): number {
  const win = tmuxStore.activeWindow
  if (!win) return 0
  const pane = win.panes[paneId]
  return pane?.history_size ?? 0
}
</script>

<template>
  <div class="heatmap-bar visible">
    <span class="hm-label">Activity</span>
    <div
      v-for="p in panes"
      :key="p.pane_id"
      class="heatmap-cell"
      :class="{ active: p.pane_id === activePaneId }"
      :style="{ background: roleColor(p.title) }"
      :title="`${p.title} (${getLineCount(p.pane_id)} lines)`"
      @click="emit('select-pane', p.pane_id)"
    >
      {{ roleName(p.title) }}
      <span class="hm-lines">{{ getLineCount(p.pane_id) }}</span>
    </div>
  </div>
</template>

<style scoped>
.heatmap-bar {
  display: flex; align-items: center;
  height: 26px; padding: 0 10px; gap: 4px;
  background: #0d1117; border-bottom: 1px solid #21262d;
  flex-shrink: 0; overflow-x: auto; scrollbar-width: none;
}
.heatmap-bar::-webkit-scrollbar { display: none; }
.hm-label {
  font-size: 9px; color: #484f58; margin-right: 4px;
  text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600; white-space: nowrap;
}
.heatmap-cell {
  min-width: 32px; height: 18px; border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 600; color: #fff;
  cursor: pointer; transition: outline 0.15s, transform 0.1s;
  white-space: nowrap; padding: 0 6px; gap: 3px;
}
.heatmap-cell:hover { transform: scale(1.08); }
.heatmap-cell.active { outline: 2px solid #f0f6fc; outline-offset: 1px; }
.hm-lines { font-size: 8px; opacity: 0.7; }
</style>
