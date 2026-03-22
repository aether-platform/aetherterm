/**
 * Pinia store for multi-agent discussion management.
 *
 * Handles discussion wizard state and API calls to start discussions.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiBaseUrl } from '../config/environment'

export type DiscussionScale = 'sme' | 'le'
export type DiscussionRole = 'both' | 'biz' | 'dev'

export interface TimelineEntry {
  id: number
  ts: string
  type: string
  source: string
  target: string
  detail: string
  meta?: Record<string, unknown>
}

export const useDiscussionStore = defineStore('discussion', () => {
  // Wizard state
  const isWizardOpen = ref(false)
  const topic = ref('')
  const scale = ref<DiscussionScale>('le')
  const role = ref<DiscussionRole>('both')
  const isSubmitting = ref(false)
  const lastError = ref('')

  // Timeline state
  const timeline = ref<TimelineEntry[]>([])
  const timelineLastId = ref(0)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // Wizard actions
  function openWizard() {
    isWizardOpen.value = true
    topic.value = ''
    scale.value = 'le'
    role.value = 'both'
    lastError.value = ''
  }

  function closeWizard() {
    isWizardOpen.value = false
    isSubmitting.value = false
  }

  async function startDiscussion(sessionId: string) {
    if (!topic.value.trim()) {
      lastError.value = 'Topic is required'
      return false
    }

    isSubmitting.value = true
    lastError.value = ''

    try {
      const res = await fetch(`${apiBaseUrl}/api/tmux/sessions/${sessionId}/discussion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic.value.trim(),
          scale: scale.value,
          role: role.value,
        }),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }))
        lastError.value = data.detail || data.error || 'Failed to start discussion'
        return false
      }

      closeWizard()
      return true
    } catch (e) {
      lastError.value = `Network error: ${e}`
      return false
    } finally {
      isSubmitting.value = false
    }
  }

  // Timeline actions
  async function fetchTimeline(sessionId: string) {
    try {
      const url = `${apiBaseUrl}/api/tmux/sessions/${sessionId}/timeline?since_id=${timelineLastId.value}&limit=200`
      const res = await fetch(url)
      if (!res.ok) return
      const entries: TimelineEntry[] = await res.json()
      if (entries.length > 0) {
        timeline.value.push(...entries)
        timelineLastId.value = entries[entries.length - 1].id
        // Keep last 500
        if (timeline.value.length > 500) {
          timeline.value = timeline.value.slice(-500)
        }
      }
    } catch {
      // Silently ignore poll errors
    }
  }

  function startTimelinePolling(sessionId: string) {
    stopTimelinePolling()
    // Initial fetch
    fetchTimeline(sessionId)
    pollTimer = setInterval(() => fetchTimeline(sessionId), 3000)
  }

  function stopTimelinePolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function clearTimeline() {
    timeline.value = []
    timelineLastId.value = 0
  }

  async function postToTimeline(sessionId: string, detail: string, type: string = 'note') {
    try {
      await fetch(`${apiBaseUrl}/api/tmux/sessions/${sessionId}/timeline/post`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, source: 'ui', detail }),
      })
      await fetchTimeline(sessionId)
    } catch {
      // ignore
    }
  }

  return {
    // Wizard
    isWizardOpen,
    topic,
    scale,
    role,
    isSubmitting,
    lastError,
    openWizard,
    closeWizard,
    startDiscussion,

    // Timeline
    timeline,
    fetchTimeline,
    startTimelinePolling,
    stopTimelinePolling,
    clearTimeline,
    postToTimeline,
  }
})
