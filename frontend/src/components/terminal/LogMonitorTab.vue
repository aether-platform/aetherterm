<template>
  <div class="log-monitor-tab-container">
    <TerminalLogMonitorPanel />
  </div>
</template>

<script setup lang="ts">
import TerminalLogMonitorPanel from '../TerminalLogMonitorPanel.vue';
</script>

<style scoped lang="scss">
@import '../../assets/styles/base.scss';

.log-monitor-tab-container {
  @include flex-column;
  flex: 1;
  overflow: hidden;
}
</style>