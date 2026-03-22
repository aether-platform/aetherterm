<script setup lang="ts">
/**
 * HeatmapRail - Vertical activity heatmap rail for pane navigation.
 *
 * Displays compact pane dots in a vertical column with role initial and
 * line count. Used in split-agent layout mode alongside the agents column.
 *
 * Ported from: poc/aetherterm-poc/frontend/src/components/HeatmapRail.vue
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
}>()

const emit = defineEmits<{
  'scroll-to': [paneId: string]
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
  <div class="heatmap-rail">
    <div
      v-for="p in panes"
      :key="p.pane_id"
      class="hm-dot"
      :style="{ background: roleColor(p.title) }"
      :title="`${p.title} (${getLineCount(p.pane_id)} lines)`"
      @click="emit('scroll-to', p.pane_id)"
    >
      <span>{{ roleName(p.title).charAt(0).toUpperCase() }}<br>{{ getLineCount(p.pane_id) }}</span>
    </div>
  </div>
</template>

<style scoped>
.heatmap-rail {
  width: 36px; flex-shrink: 0;
  display: flex; flex-direction: column; align-items: center;
  gap: 4px; padding: 6px 0;
  background: rgba(13, 17, 23, 0.85); backdrop-filter: blur(6px);
  border-left: 1px solid #21262d;
  overflow-y: auto; scrollbar-width: none;
}
.heatmap-rail::-webkit-scrollbar { display: none; }
.hm-dot {
  width: 24px; height: 24px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; cursor: pointer; flex-shrink: 0;
  transition: transform 0.1s, outline 0.15s;
}
.hm-dot span { font-size: 7px; line-height: 1; text-align: center; font-weight: 700; }
.hm-dot:hover { transform: scale(1.15); }
</style>
