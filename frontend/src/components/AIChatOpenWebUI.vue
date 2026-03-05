<script setup lang="ts">
  import { ref } from 'vue'

  // Deep Chat handle
  const deepChatRef = ref<any>(null)

  const requestConfig = {
    url: '/api/chat-ui/chat/completions',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }

  // Map OpenWeb UI response back to Deep Chat format
  const responseInterceptor = (response: any) => {
    if (response.choices && response.choices[0] && response.choices[0].message) {
      return { text: response.choices[0].message.content }
    }
    return response
  }
</script>

<template>
  <div class="chat-wrapper">
    <deep-chat
      ref="deepChatRef"
      class="deep-chat-container"
      :request="requestConfig"
      :responseInterceptor="responseInterceptor"
      :messageStyles="{
        default: {
          ai: {
            bubble: {
              backgroundColor: 'var(--vscode-sideBar-background)',
              color: 'var(--vscode-foreground)',
            },
          },
          user: { bubble: { backgroundColor: '#007acc', color: 'white' } },
        },
      }"
      :textInput="{
        placeholder: { text: 'Ask OpenWeb UI...' },
        styles: {
          container: {
            backgroundColor: 'var(--vscode-input-background)',
            border: '1px solid var(--vscode-input-border)',
            color: 'var(--vscode-input-foreground)',
          },
        },
      }"
    />
  </div>
</template>

<style scoped>
  .chat-wrapper {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .deep-chat-container {
    width: 100%;
    height: 100%;
    border: none;
    background-color: transparent;
  }
</style>
