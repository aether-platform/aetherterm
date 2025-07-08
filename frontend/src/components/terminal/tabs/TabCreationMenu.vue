<template>
  <div class="add-tab-container">
    <button
      ref="buttonRef"
      @click="toggleMenu"
      class="add-tab-btn"
      :class="{ 'menu-open': showMenu }"
      title="Add New Tab"
    >
      +
    </button>

    <!-- Add Tab Menu -->
    <div 
      v-if="showMenu" 
      class="add-tab-menu" 
      @click.stop
      :style="{
        top: menuPosition.top + 'px',
        left: menuPosition.left + 'px'
      }"
    >
      <!-- Terminal (Direct Action) -->
      <button 
        @click="addTab('terminal')"
        class="menu-item terminal-item"
      >
        <span class="menu-icon">💻</span>
        <span class="menu-text">Terminal</span>
      </button>

      <!-- AI Agent (Direct Action) -->
      <button 
        @click="addTab('ai-agent')"
        class="menu-item ai-agent-item"
      >
        <span class="menu-icon">🤖</span>
        <span class="menu-text">AI Agent</span>
      </button>

    </div>

    <!-- Background overlay when menu is open -->
    <div 
      v-if="showMenu" 
      @click="showMenu = false"
      class="menu-overlay"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue';

interface Emits {
  (e: 'add-tab', type: 'terminal' | 'ai-agent'): void
}

const emit = defineEmits<Emits>()

const showMenu = ref(false)
const menuPosition = ref({ top: 0, left: 0 })
const buttonRef = ref<HTMLElement | null>(null)

const toggleMenu = async () => {
  console.log('🔥 Toggle menu clicked, current state:', showMenu.value)
  showMenu.value = !showMenu.value
  console.log('🔥 Menu state after toggle:', showMenu.value)
  
  if (showMenu.value && buttonRef.value) {
    // Calculate position relative to viewport for fixed positioning
    const rect = buttonRef.value.getBoundingClientRect()
    menuPosition.value = {
      top: rect.bottom + 2, // 2px gap
      left: rect.right - 180 // Align to right edge, accounting for menu width
    }
    console.log('🔥 Calculated menu position:', menuPosition.value)
  }
  
  // Debug: Check if menu element exists in DOM
  await nextTick()
  const menuEl = document.querySelector('.add-tab-menu')
  console.log('🔥 Menu element in DOM:', menuEl)
  if (menuEl) {
    const rect = menuEl.getBoundingClientRect()
    console.log('🔥 Menu actual position:', { top: rect.top, left: rect.left, width: rect.width, height: rect.height })
  }
}

const addTab = (type: 'terminal' | 'ai-agent') => {
  console.log('🔥 Add tab clicked, type:', type)
  emit('add-tab', type)
  showMenu.value = false
}

// Close menu when clicking outside
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as Element
  if (!target.closest('.add-tab-container')) {
    showMenu.value = false
  }
}

// Close menu on escape key
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && showMenu.value) {
    showMenu.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeyDown)
})
</script>

<style scoped lang="scss">
@import '../../../assets/styles/base.scss';

.add-tab-container {
  position: relative;
  flex-shrink: 0;
  z-index: 1000; /* Ensure container has higher z-index */
}

.add-tab-btn {
  @include button-reset;
  @include flex-center;
  
  width: $tab-height;
  height: $tab-height;
  background-color: var(--color-bg-secondary);
  border-right: $border-width solid var(--color-border-primary);
  color: var(--color-text-muted);
  font-size: $font-size-lg;
  font-weight: $font-weight-bold;
  transition: $transition-colors;

  &:hover {
    background-color: var(--color-bg-tertiary);
    color: var(--color-primary);
  }

  &.menu-open {
    background-color: var(--color-primary);
    color: var(--color-text-primary);
  }

  @include focus-ring;
}

.add-tab-menu {
  position: fixed !important; // Use fixed positioning to escape overflow containers
  min-width: 180px;
  z-index: 10000; // Very high z-index to ensure visibility
  background-color: #2d2d2d; // Solid background color
  border: 1px solid #444; // Visible border
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5); // Enhanced shadow for better visibility
  padding: 4px 0;
}

.menu-section {
  border-bottom: 1px solid var(--color-border-secondary);

  &:last-child {
    border-bottom: none;
  }
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  width: 100%;
  padding: 8px 16px;
  background: none;
  border: none;
  color: #ffffff;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: #3d3d3d;
  }

  &.terminal-item:hover {
    background-color: #2196f3;
    color: #ffffff;
  }

  &.ai-agent-item:hover {
    background-color: #9c27b0;
    color: #ffffff;
  }
}

.menu-icon {
  font-size: $font-size-md;
  flex-shrink: 0;
}

.menu-text {
  font-weight: $font-weight-medium;
  flex: 1;
}

.menu-overlay {
  @include fixed-full;
  z-index: $z-index-modal-backdrop;
  background: transparent;
}

// Remove animations for now to ensure visibility

// Enhanced hover effects
.menu-item {
  transition: all 0.2s ease;

  &:hover {
    transform: translateX(2px);
    box-shadow: inset 3px 0 0 var(--color-primary);
  }
}

/* Responsive */
@include mobile-only {
  .add-tab-menu {
    right: -10px;
    min-width: 160px;
  }
}

</style>