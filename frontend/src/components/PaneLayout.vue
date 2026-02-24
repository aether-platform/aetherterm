<template>
  <div class="pane-layout" :class="layoutClass" :style="layoutStyle">
    <!-- Leaf node: render a terminal or code-server -->
    <template v-if="node.type === 'leaf' && node.paneId">
      <CodeServerComponent
        v-if="getPaneMode(node.paneId) === 'code-server'"
        :pane-id="node.paneId"
        :session-id="getSessionId(node.paneId)"
      />
      <TerminalComponent
        v-else
        :pane-id="node.paneId"
        :session-id="getSessionId(node.paneId)"
        :is-focused="isFocused(node.paneId)"
        :mode="getPaneMode(node.paneId)"
        @focus="onPaneFocus(node.paneId)"
      />
    </template>

    <!-- Split node: render children with divider -->
    <template v-else-if="node.children && node.children.length > 0">
      <template v-for="(child, index) in node.children" :key="index">
        <div class="pane-child" :style="childStyle(child, index)">
          <PaneLayout :node="child" :path="[...path, index]" />
        </div>
        <!-- Divider between children -->
        <div
          v-if="index < node.children.length - 1"
          class="pane-divider"
          :class="dividerClass"
          @mousedown.prevent="startDividerDrag($event, index)"
        >
          <div class="divider-handle"></div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { usePaneStore, type PaneLayout as PaneLayoutType } from '../stores/paneStore'
  import CodeServerComponent from './CodeServerComponent.vue'
  import TerminalComponent from './TerminalComponent.vue'

  const props = withDefaults(
    defineProps<{
      node: PaneLayoutType
      path?: number[]
    }>(),
    {
      path: () => [],
    }
  )

  const paneStore = usePaneStore()

  const layoutClass = computed(() => ({
    'layout-hsplit': props.node.type === 'hsplit',
    'layout-vsplit': props.node.type === 'vsplit',
    'layout-leaf': props.node.type === 'leaf',
  }))

  const layoutStyle = computed(() => {
    if (props.node.type === 'leaf') {
      return { flex: props.node.ratio }
    }
    return { flex: props.node.ratio }
  })

  const dividerClass = computed(() => ({
    'divider-horizontal': props.node.type === 'hsplit',
    'divider-vertical': props.node.type === 'vsplit',
  }))

  function childStyle(child: PaneLayoutType, _index: number) {
    return {
      flex: child.ratio,
      minWidth: props.node.type === 'vsplit' ? '100px' : undefined,
      minHeight: props.node.type === 'hsplit' ? '80px' : undefined,
    }
  }

  function getSessionId(paneId: string): string {
    const pane = paneStore.panes.get(paneId)
    return pane?.sessionId || ''
  }

  function isFocused(paneId: string): boolean {
    return paneStore.focusedPaneId === paneId
  }

  function getPaneMode(paneId: string): string {
    const pane = paneStore.panes.get(paneId)
    return pane?.mode || 'terminal'
  }

  function onPaneFocus(paneId: string) {
    paneStore.focusPane(paneId)
  }

  // Divider drag logic
  const isDragging = ref(false)

  function startDividerDrag(event: MouseEvent, childIndex: number) {
    isDragging.value = true
    const startPos = props.node.type === 'vsplit' ? event.clientX : event.clientY
    const container = (event.target as HTMLElement).parentElement
    if (!container) return

    const containerRect = container.getBoundingClientRect()
    const totalSize = props.node.type === 'vsplit' ? containerRect.width : containerRect.height

    const children = props.node.children
    if (!children) return

    const startRatio = children[childIndex].ratio

    const onMove = (e: MouseEvent) => {
      const currentPos = props.node.type === 'vsplit' ? e.clientX : e.clientY
      const delta = (currentPos - startPos) / totalSize
      const newRatio = Math.max(0.1, Math.min(0.9, startRatio + delta))

      paneStore.updateLayoutRatio([...props.path, childIndex], newRatio)
    }

    const onUp = () => {
      isDragging.value = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    document.body.style.cursor = props.node.type === 'vsplit' ? 'col-resize' : 'row-resize'
    document.body.style.userSelect = 'none'
  }
</script>

<style scoped>
  .pane-layout {
    display: flex;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: var(--bg-primary);
  }

  .layout-vsplit {
    flex-direction: row;
  }

  .layout-hsplit {
    flex-direction: column;
  }

  .layout-leaf {
    flex-direction: column;
  }

  .pane-child {
    overflow: hidden;
    display: flex;
    background-color: var(--bg-secondary);
  }

  .pane-divider {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 5;
    background-color: var(--border-color);
    transition: all 0.2s;
  }

  .pane-divider:hover {
    background-color: var(--accent-color);
    box-shadow: 0 0 10px var(--accent-glow);
  }

  .divider-vertical {
    width: 2px;
    cursor: col-resize;
    margin: 0 -1px; /* Overlap to prevent gaps */
  }

  .divider-horizontal {
    height: 2px;
    cursor: row-resize;
    margin: -1px 0;
  }

  .divider-handle {
    width: 1px;
    height: 40px;
    background-color: var(--border-color);
    opacity: 0;
    transition: opacity 0.2s;
  }

  .divider-horizontal .divider-handle {
    width: 40px;
    height: 1px;
  }

  .pane-divider:hover .divider-handle {
    opacity: 1;
    background-color: #fff;
  }
</style>
