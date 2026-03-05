<template>
  <div class="rename-overlay" @click.self="$emit('close')">
    <div class="rename-dialog">
      <label class="rename-label">
        Rename {{ target.type }}:
      </label>
      <input
        ref="inputEl"
        v-model="newName"
        class="rename-input"
        @keydown.enter="submit"
        @keydown.escape="$emit('close')"
      />
      <div class="rename-actions">
        <button class="btn" @click="$emit('close')">Cancel</button>
        <button class="btn btn-primary" @click="submit">Rename</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, ref } from 'vue'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const props = defineProps<{
    target: { type: 'session' | 'window'; id: string; name: string }
  }>()

  const emit = defineEmits<{
    close: []
  }>()

  const tmuxStore = useTmuxStore()
  const newName = ref(props.target.name)
  const inputEl = ref<HTMLInputElement | null>(null)

  function submit() {
    const name = newName.value.trim()
    if (!name) return

    if (props.target.type === 'window') {
      tmuxStore.renameWindow(props.target.id, name)
    } else {
      tmuxStore.renameSession(name)
    }
    emit('close')
  }

  onMounted(() => {
    inputEl.value?.focus()
    inputEl.value?.select()
  })
</script>

<style scoped>
  .rename-overlay {
    position: absolute;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .rename-dialog {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 16px 24px;
    min-width: 300px;
  }

  .rename-label {
    display: block;
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 8px;
  }

  .rename-input {
    width: 100%;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 8px 10px;
    color: #f1f5f9;
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
    outline: none;
    box-sizing: border-box;
  }

  .rename-input:focus {
    border-color: #6366f1;
  }

  .rename-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
  }

  .btn {
    padding: 6px 16px;
    border: 1px solid #334155;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    background: transparent;
    color: #94a3b8;
  }

  .btn-primary {
    background: #6366f1;
    color: white;
    border-color: #6366f1;
  }
</style>
