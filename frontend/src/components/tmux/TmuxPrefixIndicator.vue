<template>
  <div class="prefix-indicator">
    <span class="prefix-key">^B</span>
    <span class="prefix-text">PREFIX</span>
  </div>
</template>

<style scoped>
  .prefix-indicator {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 100;
    background: rgba(99, 102, 241, 0.9);
    color: white;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    display: flex;
    gap: 6px;
    align-items: center;
    animation: fadeIn 0.1s ease;
  }

  .prefix-key {
    background: rgba(255, 255, 255, 0.2);
    padding: 1px 4px;
    border-radius: 2px;
    font-size: 10px;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>
