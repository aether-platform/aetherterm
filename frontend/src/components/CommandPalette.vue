<template>
  <div v-if="show" class="command-palette-overlay" @click.self="close">
    <div class="command-palette">
      <div class="search-container">
        <span class="search-icon">&#x1F50D;</span>
        <input
          ref="inputRef"
          v-model="query"
          type="text"
          placeholder="Type a command or search panes..."
          @keydown.down.prevent="moveDown"
          @keydown.up.prevent="moveUp"
          @keydown.enter="executeCurrent"
          @keydown.esc="close"
        />
      </div>

      <div class="results-container">
        <div
          v-for="(item, index) in filteredItems"
          :key="item.id"
          class="result-item"
          :class="{ active: index === selectedIndex }"
          @click="execute(item)"
          @mouseenter="selectedIndex = index"
        >
          <span class="item-icon">{{ item.icon }}</span>
          <div class="item-details">
            <div class="item-title">{{ item.title }}</div>
            <div class="item-description">{{ item.description }}</div>
          </div>
          <span v-if="item.shortcut" class="item-shortcut">{{ item.shortcut }}</span>
        </div>
        <div v-if="filteredItems.length === 0" class="no-results">No matching commands found.</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { usePaneStore } from '../stores/paneStore'
  import { useUIModeStore } from '../stores/uiModeStore'

  const props = defineProps<{
    show: boolean
  }>()

  const emit = defineEmits<{
    'update:show': [value: boolean]
  }>()

  const paneStore = usePaneStore()
  const uiModeStore = useUIModeStore()

  const query = ref('')
  const selectedIndex = ref(0)
  const inputRef = ref<HTMLInputElement | null>(null)

  interface CommandItem {
    id: string
    title: string
    description: string
    icon: string
    shortcut?: string
    action: () => void
  }

  const commands = computed<CommandItem[]>(() => [
    {
      id: 'split-v',
      title: 'Split Pane Vertical',
      description: 'Split the current pane vertically',
      icon: '&#x2503;',
      shortcut: 'Ctrl+Shift+|',
      action: () => paneStore.addPane('vertical'),
    },
    {
      id: 'split-h',
      title: 'Split Pane Horizontal',
      description: 'Split the current pane horizontally',
      icon: '&#x2501;',
      shortcut: 'Ctrl+Shift+_',
      action: () => paneStore.addPane('horizontal'),
    },
    {
      id: 'toggle-mode',
      title: 'Toggle UI Mode',
      description: 'Switch between Terminal and Chat focus',
      icon: '&#x21C4;',
      shortcut: 'Ctrl+Shift+M',
      action: () => uiModeStore.toggleMode(),
    },
    {
      id: 'close-pane',
      title: 'Close Current Pane',
      description: 'Remove the focused terminal/pane',
      icon: '&#x2715;',
      shortcut: 'Ctrl+Shift+W',
      action: () => {
        if (paneStore.focusedPaneId) paneStore.removePane(paneStore.focusedPaneId)
      },
    },
    // Add dynamic pane items
    ...Array.from(paneStore.panes.values()).map((pane) => ({
      id: `pane-${pane.id}`,
      title: `Focus: ${pane.title}`,
      description: `Switch to session ${pane.sessionId} (${pane.mode})`,
      icon: '&#x25A3;',
      action: () => paneStore.focusPane(pane.id),
    })),
  ])

  const filteredItems = computed(() => {
    if (!query.value) return commands.value
    const q = query.value.toLowerCase()
    return commands.value.filter(
      (item) => item.title.toLowerCase().includes(q) || item.description.toLowerCase().includes(q)
    )
  })

  watch(
    () => props.show,
    (newVal) => {
      if (newVal) {
        query.value = ''
        selectedIndex.value = 0
        nextTick(() => {
          inputRef.value?.focus()
        })
      }
    }
  )

  const moveDown = () => {
    selectedIndex.value = (selectedIndex.value + 1) % filteredItems.value.length
  }

  const moveUp = () => {
    selectedIndex.value =
      (selectedIndex.value - 1 + filteredItems.value.length) % filteredItems.value.length
  }

  const executeCurrent = () => {
    const item = filteredItems.value[selectedIndex.value]
    if (item) execute(item)
  }

  const execute = (item: CommandItem) => {
    item.action()
    close()
  }

  const close = () => {
    emit('update:show', false)
  }
</script>

<style scoped>
  .command-palette-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(2px);
    display: flex;
    justify-content: center;
    padding-top: 15vh;
    z-index: 2000;
  }

  .command-palette {
    width: 600px;
    max-height: 400px;
    background-color: #1a1d23;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: slide-in 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @keyframes slide-in {
    from {
      transform: translateY(-20px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .search-container {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    background-color: rgba(255, 255, 255, 0.03);
  }

  .search-icon {
    margin-right: 12px;
    color: #8b949e;
    font-size: 16px;
  }

  input {
    flex: 1;
    background: none;
    border: none;
    color: #e1e4e8;
    font-size: 14px;
    outline: none;
  }

  .results-container {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }

  .result-item {
    display: flex;
    align-items: center;
    padding: 8px 16px;
    cursor: pointer;
    transition: background 0.1s;
    gap: 12px;
  }

  .result-item:hover,
  .result-item.active {
    background-color: rgba(76, 175, 80, 0.15);
  }

  .result-item.active {
    border-left: 3px solid #4caf50;
    padding-left: 13px;
  }

  .item-icon {
    width: 20px;
    display: flex;
    justify-content: center;
    color: #8b949e;
    font-size: 16px;
  }

  .active .item-icon {
    color: #4caf50;
  }

  .item-details {
    flex: 1;
  }

  .item-title {
    font-size: 13px;
    font-weight: 500;
  }

  .item-description {
    font-size: 11px;
    color: #8b949e;
  }

  .item-shortcut {
    font-size: 10px;
    background-color: rgba(255, 255, 255, 0.05);
    padding: 2px 6px;
    border-radius: 4px;
    color: #8b949e;
    font-family: monospace;
  }

  .no-results {
    padding: 20px;
    text-align: center;
    color: #8b949e;
    font-size: 13px;
  }
</style>
