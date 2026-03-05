<template>
  <div class="tmux-layout">
    <TmuxContainer class="tmux-layout__main" />
    <Transition name="sidebar-slide" @after-leave="onTransitionEnd" @after-enter="onTransitionEnd">
      <PilotSidebar v-if="uiMode.showSidebar" class="tmux-layout__sidebar" />
    </Transition>
  </div>
</template>

<script setup lang="ts">
  import { useUIModeStore } from '../../stores/uiModeStore'
  import TmuxContainer from './TmuxContainer.vue'
  import PilotSidebar from '../pilot/PilotSidebar.vue'

  const uiMode = useUIModeStore()

  function onTransitionEnd() {
    window.dispatchEvent(new Event('resize'))
  }
</script>

<style scoped>
  .tmux-layout {
    display: flex;
    flex-direction: row;
    height: 100%;
    width: 100%;
  }

  .tmux-layout__main {
    flex: 1;
    min-width: 0;
  }

  .sidebar-slide-enter-active,
  .sidebar-slide-leave-active {
    transition: transform 200ms ease, opacity 200ms ease;
  }

  .sidebar-slide-enter-from,
  .sidebar-slide-leave-to {
    transform: translateX(100%);
    opacity: 0;
  }
</style>
