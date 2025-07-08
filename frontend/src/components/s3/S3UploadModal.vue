<template>
  <div v-if="visible" class="modal-overlay" @click="emit('close')">
    <div class="upload-modal" @click.stop>
      <div class="modal-header">
        <h3>Upload Files</h3>
        <button @click="emit('close')" class="modal-close">✕</button>
      </div>
      
      <div class="modal-content">
        <div class="upload-area">
          <input
            ref="fileInput"
            type="file"
            multiple
            @change="handleFileSelect"
            class="file-input"
            id="file-upload"
          />
          <label for="file-upload" class="upload-label">
            <div class="upload-icon">📤</div>
            <div class="upload-text">
              <p>Click to select files</p>
              <small>or drag and drop</small>
            </div>
          </label>
        </div>

        <!-- Upload Progress -->
        <div v-if="uploads.length > 0" class="upload-progress">
          <h4>Upload Progress</h4>
          <div
            v-for="upload in uploads"
            :key="upload.name"
            class="upload-item"
          >
            <div class="upload-info">
              <span class="upload-name">{{ upload.name }}</span>
              <span class="upload-percent">{{ upload.progress }}%</span>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: upload.progress + '%' }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Upload {
  name: string
  progress: number
}

defineProps<{
  visible: boolean
  uploads: Upload[]
}>()

const emit = defineEmits<{
  close: []
  uploadFiles: [files: FileList]
}>()

const fileInput = ref<HTMLInputElement>()

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (files) {
    emit('uploadFiles', files)
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.upload-modal {
  background: #1e1e1e;
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  border: 1px solid #333;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #333;
  background: #252525;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  color: #fff;
}

.modal-close {
  background: none;
  border: none;
  color: #ccc;
  font-size: 18px;
  cursor: pointer;
  padding: 4px;
  border-radius: 3px;
}

.modal-close:hover {
  background: #333;
  color: white;
}

.modal-content {
  padding: 16px;
}

.upload-area {
  margin-bottom: 16px;
}

.file-input {
  display: none;
}

.upload-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  border: 2px dashed #666;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background: #2a2a2a;
}

.upload-label:hover {
  border-color: #4caf50;
  background: #2e2e2e;
}

.upload-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.upload-text {
  text-align: center;
}

.upload-text p {
  margin: 0 0 4px 0;
  font-size: 14px;
  color: #fff;
}

.upload-text small {
  color: #aaa;
  font-size: 12px;
}

.upload-progress {
  max-height: 200px;
  overflow-y: auto;
}

.upload-progress h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #fff;
}

.upload-item {
  margin-bottom: 12px;
  padding: 8px;
  background: #2a2a2a;
  border-radius: 4px;
}

.upload-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 12px;
}

.upload-name {
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.upload-percent {
  color: #4caf50;
  font-weight: 500;
}

.progress-bar {
  height: 4px;
  background: #444;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4caf50, #66bb6a);
  transition: width 0.3s ease;
}

/* Scrollbar styling */
.upload-progress::-webkit-scrollbar {
  width: 4px;
}

.upload-progress::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.upload-progress::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}
</style>