<template>
  <div class="tasks-tab">
    <!-- Quick create -->
    <div class="tasks-tab__create">
      <input
        v-model="newSubject"
        class="tasks-tab__create-input"
        placeholder="New task..."
        @keydown.enter="createTask"
      />
      <button class="tasks-tab__create-btn" @click="createTask" :disabled="!newSubject.trim()">+</button>
    </div>

    <div class="tasks-tab__sections">
      <!-- Pending -->
      <div class="tasks-tab__section">
        <div class="tasks-tab__section-header">
          <span class="tasks-tab__section-dot dot--pending" />
          Pending
          <span class="tasks-tab__count">{{ taskStore.pendingTasks.length }}</span>
        </div>
        <div v-if="taskStore.pendingTasks.length === 0" class="tasks-tab__section-empty">
          No pending tasks
        </div>
        <div v-for="task in taskStore.pendingTasks" :key="task.task_id" class="task-card">
          <div class="task-card__subject">{{ task.subject }}</div>
          <div class="task-card__meta">
            <span class="task-card__badge badge--pending">pending</span>
            <span v-if="task.owner" class="task-card__owner">{{ task.owner }}</span>
          </div>
        </div>
      </div>

      <!-- In Progress -->
      <div class="tasks-tab__section">
        <div class="tasks-tab__section-header">
          <span class="tasks-tab__section-dot dot--in-progress" />
          In Progress
          <span class="tasks-tab__count">{{ taskStore.inProgressTasks.length }}</span>
        </div>
        <div v-if="taskStore.inProgressTasks.length === 0" class="tasks-tab__section-empty">
          No tasks in progress
        </div>
        <div v-for="task in taskStore.inProgressTasks" :key="task.task_id" class="task-card">
          <div class="task-card__subject">{{ task.subject }}</div>
          <div class="task-card__meta">
            <span class="task-card__badge badge--in-progress">in progress</span>
            <span v-if="task.owner" class="task-card__owner">{{ task.owner }}</span>
          </div>
        </div>
      </div>

      <!-- Completed -->
      <div class="tasks-tab__section">
        <div class="tasks-tab__section-header">
          <span class="tasks-tab__section-dot dot--completed" />
          Completed
          <span class="tasks-tab__count">{{ taskStore.completedTasks.length }}</span>
        </div>
        <div v-if="taskStore.completedTasks.length === 0" class="tasks-tab__section-empty">
          No completed tasks
        </div>
        <div v-for="task in taskStore.completedTasks" :key="task.task_id" class="task-card">
          <div class="task-card__subject">{{ task.subject }}</div>
          <div class="task-card__meta">
            <span class="task-card__badge badge--completed">completed</span>
            <span v-if="task.owner" class="task-card__owner">{{ task.owner }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { useAgentTaskStore } from '../../stores/agentTaskStore'

  const taskStore = useAgentTaskStore()
  const newSubject = ref('')

  function createTask() {
    const subject = newSubject.value.trim()
    if (!subject) return
    taskStore.createTask(subject)
    newSubject.value = ''
  }
</script>

<style scoped>
  .tasks-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .tasks-tab__create {
    display: flex;
    gap: 4px;
    padding: 8px 12px;
    border-bottom: 1px solid #2d3139;
    flex-shrink: 0;
  }

  .tasks-tab__create-input {
    flex: 1;
    background: #0d1117;
    border: 1px solid #2d3139;
    border-radius: 4px;
    padding: 4px 8px;
    color: #c9d1d9;
    font-size: 12px;
    outline: none;
  }

  .tasks-tab__create-input:focus {
    border-color: #58a6ff;
  }

  .tasks-tab__create-input::placeholder {
    color: #484f58;
  }

  .tasks-tab__create-btn {
    background: #238636;
    border: none;
    color: #fff;
    width: 28px;
    height: 28px;
    border-radius: 4px;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .tasks-tab__create-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .tasks-tab__sections {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .tasks-tab__section {
    margin-bottom: 8px;
  }

  .tasks-tab__section-header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .tasks-tab__section-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }

  .dot--pending {
    background: #d29922;
  }

  .dot--in-progress {
    background: #58a6ff;
  }

  .dot--completed {
    background: #3fb950;
  }

  .tasks-tab__count {
    color: #484f58;
    font-weight: 400;
  }

  .tasks-tab__section-empty {
    padding: 8px 12px 8px 24px;
    color: #484f58;
    font-size: 12px;
  }

  .task-card {
    padding: 6px 12px 6px 24px;
    cursor: default;
    transition: background 0.15s;
  }

  .task-card:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .task-card__subject {
    font-size: 13px;
    color: #c9d1d9;
    line-height: 1.3;
  }

  .task-card__meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
  }

  .task-card__badge {
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    text-transform: capitalize;
  }

  .badge--pending {
    background: rgba(210, 153, 34, 0.15);
    color: #d29922;
  }

  .badge--in-progress {
    background: rgba(88, 166, 255, 0.15);
    color: #58a6ff;
  }

  .badge--completed {
    background: rgba(63, 185, 80, 0.15);
    color: #3fb950;
  }

  .task-card__owner {
    font-size: 10px;
    color: #484f58;
  }
</style>
