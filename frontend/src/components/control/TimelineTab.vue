<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'

interface TimelineEntry {
  ts?: string
  _server_id?: string
  type?: string
  from_agent?: string
  detail?: string
}

const props = defineProps<{
  entries: TimelineEntry[]
}>()

const listRef = ref<HTMLElement | null>(null)

const recent = computed(() => props.entries.slice(-300))

watch(
  () => props.entries.length,
  () => {
    nextTick(() => {
      if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
    })
  },
)
</script>

<template>
  <div class="tab-content">
    <div class="timeline-list" ref="listRef">
      <div v-for="(e, i) in recent" :key="i" class="tl-entry">
        <span class="tl-ts">{{ (e.ts || '').slice(11, 19) }}</span>
        <span class="tl-server">[{{ (e._server_id || '').slice(0, 12) }}]</span>
        <span class="tl-type">{{ e.type || '' }}</span>
        <span class="tl-from">{{ e.from_agent || '' }}</span>
        <span class="tl-detail">{{ e.detail || '' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.timeline-list {
  flex: 1; overflow-y: auto; padding: 8px 12px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
}
.tl-entry { padding: 3px 0; font-size: 11px; line-height: 1.5; border-bottom: 1px solid #21262d08; }
.tl-ts { color: #6e7681; }
.tl-server { color: #d2a8ff; }
.tl-type { color: #79c0ff; }
.tl-from { color: #7ee787; }
.tl-detail { color: #c9d1d9; }
</style>
