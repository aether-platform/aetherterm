<template>
  <div class="timeline-tab">
    <div v-if="timeline.length === 0" class="timeline-tab__empty">
      <span>No activity yet</span>
    </div>

    <div v-else ref="scrollEl" class="timeline-tab__list">
      <div
        v-for="entry in timeline"
        :key="entry.id"
        class="timeline-tab__entry"
        :class="'timeline-tab__entry--' + entry.type"
      >
        <div class="timeline-tab__time">{{ formatTime(entry.ts) }}</div>
        <div class="timeline-tab__badge" :class="badgeClass(entry.type)">
          {{ shortType(entry.type) }}
        </div>
        <div class="timeline-tab__detail">
          <span v-if="entry.source" class="timeline-tab__source">{{ entry.source }}</span>
          <span v-if="entry.target" class="timeline-tab__arrow"> -&gt; {{ entry.target }}</span>
          <span class="timeline-tab__text">{{ entry.detail }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useDiscussionStore } from '../../stores/discussionStore'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const discussionStore = useDiscussionStore()
  const tmuxStore = useTmuxStore()
  const scrollEl = ref<HTMLElement | null>(null)

  const timeline = computed(() => discussionStore.timeline)

  function formatTime(ts: string): string {
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return ts.slice(11, 19)
    }
  }

  function shortType(type: string): string {
    const map: Record<string, string> = {
      discussion_start: 'DISC',
      agent_dm: 'DM',
      agent_broadcast: 'BC',
      task_create: 'TASK',
      task_complete: 'DONE',
      create: 'NEW',
      split: 'SPLIT',
      send_keys: 'KEY',
      spawn: 'SPAWN',
      close: 'CLOSE',
      summary: 'SUM',
      note: 'NOTE',
    }
    return map[type] || type.slice(0, 4).toUpperCase()
  }

  function badgeClass(type: string): string {
    if (type.includes('discussion')) return 'badge--purple'
    if (type.includes('task')) return 'badge--yellow'
    if (type.includes('agent')) return 'badge--blue'
    if (type === 'create' || type === 'spawn') return 'badge--green'
    if (type === 'close') return 'badge--red'
    return 'badge--gray'
  }

  // Auto-scroll on new entries
  watch(
    () => timeline.value.length,
    () => {
      nextTick(() => {
        if (scrollEl.value) {
          scrollEl.value.scrollTop = scrollEl.value.scrollHeight
        }
      })
    }
  )

  onMounted(() => {
    if (tmuxStore.sessionId) {
      discussionStore.startTimelinePolling(tmuxStore.sessionId)
    }
  })

  onUnmounted(() => {
    discussionStore.stopTimelinePolling()
  })

  // Restart polling if session changes
  watch(
    () => tmuxStore.sessionId,
    (id) => {
      discussionStore.clearTimeline()
      if (id) {
        discussionStore.startTimelinePolling(id)
      } else {
        discussionStore.stopTimelinePolling()
      }
    }
  )
</script>

<style scoped>
  .timeline-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .timeline-tab__empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #484f58;
    font-size: 13px;
  }

  .timeline-tab__list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .timeline-tab__entry {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    padding: 4px 12px;
    font-size: 12px;
    line-height: 1.4;
    transition: background 0.1s;
  }

  .timeline-tab__entry:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .timeline-tab__time {
    color: #484f58;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    flex-shrink: 0;
    min-width: 60px;
    padding-top: 2px;
  }

  .timeline-tab__badge {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    min-width: 36px;
    text-align: center;
  }

  .badge--purple {
    background: rgba(168, 85, 247, 0.15);
    color: #a855f7;
  }
  .badge--blue {
    background: rgba(88, 166, 255, 0.15);
    color: #58a6ff;
  }
  .badge--green {
    background: rgba(63, 185, 80, 0.15);
    color: #3fb950;
  }
  .badge--yellow {
    background: rgba(210, 153, 34, 0.15);
    color: #d29922;
  }
  .badge--red {
    background: rgba(248, 81, 73, 0.15);
    color: #f85149;
  }
  .badge--gray {
    background: rgba(139, 148, 158, 0.15);
    color: #8b949e;
  }

  .timeline-tab__detail {
    flex: 1;
    min-width: 0;
    color: #c9d1d9;
  }

  .timeline-tab__source {
    color: #58a6ff;
    font-weight: 500;
  }

  .timeline-tab__arrow {
    color: #484f58;
  }

  .timeline-tab__text {
    color: #8b949e;
    margin-left: 4px;
  }
</style>
