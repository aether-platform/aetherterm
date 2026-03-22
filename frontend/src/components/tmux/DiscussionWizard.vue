<template>
  <Teleport to="body">
    <div class="wizard-overlay" @click.self="store.closeWizard()">
      <div class="wizard-dialog">
        <div class="wizard-header">
          <h3>Discussion w/ Agents</h3>
          <button class="wizard-close" @click="store.closeWizard()">&times;</button>
        </div>

        <div class="wizard-body">
          <!-- Topic -->
          <div class="wizard-field">
            <label class="wizard-label">Topic</label>
            <textarea
              v-model="store.topic"
              class="wizard-textarea"
              placeholder="What would you like to discuss?"
              rows="3"
              :disabled="store.isSubmitting"
              @keydown.ctrl.enter="submit"
              @keydown.meta.enter="submit"
            />
          </div>

          <!-- Scale -->
          <div class="wizard-field">
            <label class="wizard-label">Scale</label>
            <div class="wizard-options wizard-options--vertical">
              <button
                class="wizard-option"
                :class="{ active: store.scale === 'sme' }"
                :disabled="store.isSubmitting"
                @click="store.scale = 'sme'"
              >
                <span class="option-title">SME</span>
                <span class="option-desc">Small / Lean (2-3 agents)</span>
              </button>
              <button
                class="wizard-option"
                :class="{ active: store.scale === 'le' }"
                :disabled="store.isSubmitting"
                @click="store.scale = 'le'"
              >
                <span class="option-title">LE</span>
                <span class="option-desc">Enterprise (4+ agents)</span>
              </button>
            </div>
          </div>

          <!-- Role -->
          <div class="wizard-field">
            <label class="wizard-label">Role</label>
            <div class="wizard-options wizard-options--vertical">
              <button
                class="wizard-option"
                :class="{ active: store.role === 'both' }"
                :disabled="store.isSubmitting"
                @click="store.role = 'both'"
              >
                <span class="option-title">Both</span>
                <span class="option-desc">Cross-functional (Biz + Dev)</span>
              </button>
              <button
                class="wizard-option"
                :class="{ active: store.role === 'biz' }"
                :disabled="store.isSubmitting"
                @click="store.role = 'biz'"
              >
                <span class="option-title">Biz</span>
                <span class="option-desc">Strategy / PMO / BA</span>
              </button>
              <button
                class="wizard-option"
                :class="{ active: store.role === 'dev' }"
                :disabled="store.isSubmitting"
                @click="store.role = 'dev'"
              >
                <span class="option-title">Dev</span>
                <span class="option-desc">Architect / SRE / Infra</span>
              </button>
            </div>
          </div>

          <!-- Error -->
          <div v-if="store.lastError" class="wizard-error">
            {{ store.lastError }}
          </div>
        </div>

        <div class="wizard-footer">
          <button
            class="wizard-btn wizard-btn--cancel"
            :disabled="store.isSubmitting"
            @click="store.closeWizard()"
          >
            Cancel
          </button>
          <button
            class="wizard-btn wizard-btn--start"
            :disabled="store.isSubmitting || !store.topic.trim()"
            @click="submit"
          >
            {{ store.isSubmitting ? 'Starting...' : 'Start Discussion' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
  import { useDiscussionStore } from '../../stores/discussionStore'
  import { useTmuxStore } from '../../stores/tmuxStore'

  const store = useDiscussionStore()
  const tmuxStore = useTmuxStore()

  async function submit() {
    if (!tmuxStore.sessionId) {
      store.lastError = 'No session connected. Please wait for connection.'
      return
    }
    await store.startDiscussion(tmuxStore.sessionId)
  }
</script>

<style scoped>
  .wizard-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .wizard-dialog {
    background: #1a1d23;
    border: 1px solid #30363d;
    border-radius: 12px;
    width: 440px;
    max-width: 90vw;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }

  .wizard-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid #30363d;
  }

  .wizard-header h3 {
    font-size: 15px;
    font-weight: 600;
    color: #f0f6fc;
    margin: 0;
  }

  .wizard-close {
    background: none;
    border: none;
    color: #8b949e;
    font-size: 20px;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
  }

  .wizard-close:hover {
    color: #f0f6fc;
  }

  .wizard-body {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow-y: auto;
  }

  .wizard-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .wizard-label {
    font-size: 12px;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .wizard-textarea {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #c9d1d9;
    font-size: 14px;
    padding: 10px 12px;
    resize: vertical;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s;
  }

  .wizard-textarea:focus {
    border-color: #58a6ff;
  }

  .wizard-textarea::placeholder {
    color: #484f58;
  }

  .wizard-options {
    display: flex;
    gap: 6px;
  }

  .wizard-options--vertical {
    flex-direction: column;
  }

  .wizard-option {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px 14px;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
  }

  .wizard-option:hover {
    border-color: #484f58;
    background: #161b22;
  }

  .wizard-option.active {
    border-color: #58a6ff;
    background: rgba(88, 166, 255, 0.08);
  }

  .wizard-option:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .option-title {
    font-size: 14px;
    font-weight: 600;
    color: #f0f6fc;
    min-width: 40px;
  }

  .option-desc {
    font-size: 12px;
    color: #8b949e;
  }

  .wizard-error {
    font-size: 13px;
    color: #f85149;
    background: rgba(248, 81, 73, 0.1);
    border: 1px solid rgba(248, 81, 73, 0.3);
    border-radius: 6px;
    padding: 8px 12px;
  }

  .wizard-footer {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 16px 20px;
    border-top: 1px solid #30363d;
  }

  .wizard-btn {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
  }

  .wizard-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .wizard-btn--cancel {
    background: #21262d;
    border-color: #30363d;
    color: #c9d1d9;
  }

  .wizard-btn--cancel:hover:not(:disabled) {
    border-color: #8b949e;
  }

  .wizard-btn--start {
    background: #238636;
    color: #fff;
  }

  .wizard-btn--start:hover:not(:disabled) {
    background: #2ea043;
  }
</style>
