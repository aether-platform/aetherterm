<template>
  <div class="agent-task-panel">
    <!-- Header -->
    <div class="task-header">
      <span class="task-title">Agent Tasks</span>
      <span class="task-count">{{ taskStore.taskList.length }}</span>
    </div>

    <!-- Filter tabs -->
    <div class="filter-tabs">
      <button
        v-for="tab in filterTabs"
        :key="tab.key"
        class="filter-tab"
        :class="{ active: activeFilter === tab.key }"
        @click="activeFilter = tab.key"
      >
        {{ tab.label }}
        <span class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <!-- Create task form -->
    <div class="create-task-form">
      <input
        v-model="newSubject"
        class="task-input"
        type="text"
        placeholder="Task subject..."
        @keydown.enter="handleCreate"
      />
      <textarea
        v-model="newDescription"
        class="task-textarea"
        placeholder="Description (optional)..."
        rows="2"
      ></textarea>
      <button class="create-btn" :disabled="!newSubject.trim()" @click="handleCreate">
        Create Task
      </button>
    </div>

    <!-- Task list -->
    <div class="task-list">
      <div
        v-for="task in filteredTasks"
        :key="task.task_id"
        class="task-card"
        :class="`task-${task.status}`"
      >
        <div class="task-card-header">
          <span class="task-subject">{{ task.subject }}</span>
          <span class="task-status-badge" :class="`badge-${task.status}`">
            {{ statusLabel(task.status) }}
          </span>
        </div>

        <div v-if="task.description" class="task-description">
          {{ task.description }}
        </div>

        <div class="task-meta">
          <span v-if="task.owner" class="task-owner">
            Owner: {{ task.owner }}
          </span>
          <span v-if="task.blocked_by && task.blocked_by.length > 0" class="task-blocked">
            Blocked by: {{ task.blocked_by.join(', ') }}
          </span>
        </div>

        <div class="task-actions">
          <button
            v-if="task.status === 'pending'"
            class="action-btn claim-btn"
            @click="handleClaim(task.task_id)"
          >
            Claim
          </button>
          <button
            v-if="task.status === 'in_progress'"
            class="action-btn complete-btn"
            @click="handleComplete(task.task_id)"
          >
            Complete
          </button>
          <button
            class="action-btn delete-btn"
            @click="handleDelete(task.task_id)"
          >
            Delete
          </button>
        </div>
      </div>

      <div v-if="filteredTasks.length === 0" class="tasks-empty">
        No {{ activeFilter === 'all' ? '' : activeFilter.replace('_', ' ') }} tasks.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { useAgentTaskStore } from '../../stores/agentTaskStore'

  const taskStore = useAgentTaskStore()

  const activeFilter = ref<'all' | 'pending' | 'in_progress' | 'completed'>('all')
  const newSubject = ref('')
  const newDescription = ref('')

  const filterTabs = computed(() => [
    { key: 'all' as const, label: 'All', count: taskStore.taskList.length },
    { key: 'pending' as const, label: 'Pending', count: taskStore.pendingTasks.length },
    { key: 'in_progress' as const, label: 'In Progress', count: taskStore.inProgressTasks.length },
    { key: 'completed' as const, label: 'Completed', count: taskStore.completedTasks.length },
  ])

  const filteredTasks = computed(() => {
    switch (activeFilter.value) {
      case 'pending':
        return taskStore.pendingTasks
      case 'in_progress':
        return taskStore.inProgressTasks
      case 'completed':
        return taskStore.completedTasks
      default:
        return taskStore.taskList
    }
  })

  function statusLabel(status: string): string {
    switch (status) {
      case 'pending':
        return 'Pending'
      case 'in_progress':
        return 'In Progress'
      case 'completed':
        return 'Done'
      default:
        return status
    }
  }

  async function handleCreate() {
    if (!newSubject.value.trim()) return
    await taskStore.createTask(newSubject.value.trim(), newDescription.value.trim())
    newSubject.value = ''
    newDescription.value = ''
  }

  async function handleClaim(taskId: string) {
    // Claim with a placeholder agent id; the backend can resolve the actual agent
    await taskStore.claimTask(taskId, 'self')
  }

  async function handleComplete(taskId: string) {
    await taskStore.updateTask(taskId, { status: 'completed' })
  }

  async function handleDelete(taskId: string) {
    await taskStore.deleteTask(taskId)
  }
</script>

<style scoped>
  .agent-task-panel {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: #1a1b26;
    color: #c0caf5;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
  }

  .task-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    background: #16161e;
    border-bottom: 1px solid #292e42;
    flex-shrink: 0;
  }

  .task-title {
    font-weight: 700;
    font-size: 13px;
    color: #7aa2f7;
  }

  .task-count {
    background: #292e42;
    color: #565f89;
    padding: 1px 6px;
    border-radius: 8px;
    font-size: 10px;
  }

  .filter-tabs {
    display: flex;
    gap: 2px;
    padding: 6px 10px;
    border-bottom: 1px solid #292e42;
    flex-shrink: 0;
  }

  .filter-tab {
    background: #292e42;
    color: #565f89;
    border: none;
    padding: 3px 10px;
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
    border-radius: 3px;
    transition: background 0.15s, color 0.15s;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .filter-tab.active {
    background: #7aa2f7;
    color: #1a1b26;
  }

  .filter-tab:not(.active):hover {
    background: #3b4261;
    color: #c0caf5;
  }

  .tab-count {
    font-size: 10px;
    opacity: 0.8;
  }

  .create-task-form {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border-bottom: 1px solid #292e42;
    flex-shrink: 0;
  }

  .task-input {
    background: #292e42;
    color: #c0caf5;
    border: 1px solid #3b4261;
    border-radius: 3px;
    padding: 5px 8px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
  }

  .task-input:focus {
    border-color: #7aa2f7;
  }

  .task-input::placeholder {
    color: #565f89;
  }

  .task-textarea {
    background: #292e42;
    color: #c0caf5;
    border: 1px solid #3b4261;
    border-radius: 3px;
    padding: 5px 8px;
    font-size: 11px;
    font-family: inherit;
    outline: none;
    resize: vertical;
    min-height: 32px;
  }

  .task-textarea:focus {
    border-color: #7aa2f7;
  }

  .task-textarea::placeholder {
    color: #565f89;
  }

  .create-btn {
    align-self: flex-end;
    background: #9ece6a;
    color: #1a1b26;
    border: none;
    border-radius: 3px;
    padding: 4px 14px;
    font-size: 11px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }

  .create-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .create-btn:not(:disabled):hover {
    opacity: 0.85;
  }

  .task-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .task-list::-webkit-scrollbar {
    width: 4px;
  }

  .task-list::-webkit-scrollbar-thumb {
    background: #3b4261;
    border-radius: 10px;
  }

  .tasks-empty {
    color: #565f89;
    text-align: center;
    margin-top: 24px;
    font-style: italic;
  }

  .task-card {
    padding: 8px 10px;
    background: #1e2030;
    border-radius: 4px;
    border-left: 2px solid #3b4261;
  }

  .task-card.task-pending {
    border-left-color: #e0af68;
  }

  .task-card.task-in_progress {
    border-left-color: #7aa2f7;
  }

  .task-card.task-completed {
    border-left-color: #9ece6a;
  }

  .task-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }

  .task-subject {
    font-weight: 600;
    color: #c0caf5;
    font-size: 12px;
  }

  .task-status-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .badge-pending {
    background: rgba(224, 175, 104, 0.2);
    color: #e0af68;
  }

  .badge-in_progress {
    background: rgba(122, 162, 247, 0.2);
    color: #7aa2f7;
  }

  .badge-completed {
    background: rgba(158, 206, 106, 0.2);
    color: #9ece6a;
  }

  .task-description {
    color: #a9b1d6;
    font-size: 11px;
    line-height: 1.4;
    margin-bottom: 4px;
    word-break: break-word;
  }

  .task-meta {
    display: flex;
    gap: 10px;
    font-size: 10px;
    color: #565f89;
    margin-bottom: 6px;
  }

  .task-blocked {
    color: #f7768e;
  }

  .task-actions {
    display: flex;
    gap: 4px;
    justify-content: flex-end;
  }

  .action-btn {
    background: #292e42;
    color: #c0caf5;
    border: none;
    border-radius: 3px;
    padding: 3px 10px;
    font-size: 10px;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }

  .claim-btn:hover {
    background: #7aa2f7;
    color: #1a1b26;
  }

  .complete-btn:hover {
    background: #9ece6a;
    color: #1a1b26;
  }

  .delete-btn:hover {
    background: #f7768e;
    color: #1a1b26;
  }
</style>
