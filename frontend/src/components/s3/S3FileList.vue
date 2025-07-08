<template>
  <div v-if="selectedBucket" class="files-section">
    <div class="section-header">
      <h4>Files</h4>
      <span class="file-count">({{ files.length }})</span>
      <div class="file-actions">
        <button @click="emit('uploadFiles')" class="action-btn" title="Upload">
          📤
        </button>
        <button @click="emit('createFolder')" class="action-btn" title="New Folder">
          📁
        </button>
      </div>
    </div>

    <!-- Current Path -->
    <div v-if="currentPath" class="current-path">
      <span class="path-icon">📍</span>
      <span class="path-text">{{ currentPathDisplay }}</span>
      <button @click="emit('navigateUp')" class="path-btn" title="Go Up">
        ⬆️
      </button>
    </div>

    <!-- File List -->
    <div class="file-list">
      <div
        v-for="file in files"
        :key="file.key || file.name"
        class="file-item"
        :class="{ folder: file.type === 'folder' }"
        @click="handleFileClick(file)"
        :title="file.key || file.name"
      >
        <span class="file-icon">
          {{ file.type === 'folder' ? '📁' : getFileIcon(file.name || file.key || '') }}
        </span>
        <div class="file-details">
          <div class="file-name">{{ truncateName(file.name || file.key || '', 25) }}</div>
          <div class="file-meta">
            <span v-if="file.size" class="file-size">{{ formatFileSize(file.size) }}</span>
            <span v-if="file.last_modified" class="file-date">{{ formatDate(file.last_modified) }}</span>
          </div>
        </div>
        <button
          v-if="file.type !== 'folder'"
          @click.stop="emit('downloadFile', file)"
          class="download-btn"
          title="Download"
        >
          ⬇️
        </button>
      </div>

      <div v-if="files.length === 0" class="empty-state">
        <span class="empty-icon">📂</span>
        <span class="empty-text">No files in this location</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface S3File {
  key?: string
  name?: string
  size?: number
  last_modified?: string
  type?: string
}

defineProps<{
  selectedBucket: string
  currentPath: string
  currentPathDisplay: string
  files: S3File[]
}>()

const emit = defineEmits<{
  uploadFiles: []
  createFolder: []
  navigateUp: []
  navigateToFolder: [file: S3File]
  downloadFile: [file: S3File]
}>()

const truncateName = (name: string, maxLength: number) => {
  return name.length > maxLength ? name.substring(0, maxLength) + '...' : name
}

const getFileIcon = (fileName: string) => {
  if (!fileName) return '📄'
  const ext = fileName.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'jpg':
    case 'jpeg':
    case 'png':
    case 'gif':
      return '🖼️'
    case 'pdf':
      return '📕'
    case 'txt':
    case 'md':
      return '📝'
    case 'zip':
    case 'tar':
    case 'gz':
      return '🗜️'
    case 'mp3':
    case 'wav':
      return '🎵'
    case 'mp4':
    case 'avi':
      return '🎬'
    default:
      return '📄'
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return ''
  }
}

const handleFileClick = (file: S3File) => {
  if (file.type === 'folder') {
    emit('navigateToFolder', file)
  }
}
</script>

<style scoped>
.files-section {
  margin: 8px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  border-bottom: 1px solid #333;
  margin-bottom: 8px;
}

.section-header h4 {
  margin: 0;
  font-size: 12px;
  color: #fff;
  font-weight: 500;
  flex: 1;
}

.file-count {
  font-size: 10px;
  color: #aaa;
}

.file-actions {
  display: flex;
  gap: 4px;
}

.action-btn {
  background: none;
  border: none;
  color: #ccc;
  padding: 2px;
  cursor: pointer;
  border-radius: 2px;
  font-size: 10px;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #333;
  color: white;
}

.current-path {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: #2a2a2a;
  border-radius: 3px;
  margin-bottom: 8px;
  font-size: 10px;
}

.path-icon {
  font-size: 10px;
}

.path-text {
  flex: 1;
  color: #4caf50;
  font-weight: 500;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.path-btn {
  background: none;
  border: none;
  color: #ccc;
  cursor: pointer;
  font-size: 10px;
  padding: 2px;
}

.path-btn:hover {
  color: #4caf50;
}

.file-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.2s;
  border-left: 2px solid transparent;
}

.file-item:hover {
  background: #333;
}

.file-item.folder {
  border-left-color: #ff9800;
}

.file-item.folder:hover {
  background: #3d2c00;
}

.file-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.file-details {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 11px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  gap: 8px;
  font-size: 9px;
  color: #aaa;
  margin-top: 2px;
}

.file-size,
.file-date {
  flex-shrink: 0;
}

.download-btn {
  background: none;
  border: none;
  color: #ccc;
  cursor: pointer;
  font-size: 10px;
  padding: 2px;
  border-radius: 2px;
  transition: all 0.2s;
  flex-shrink: 0;
}

.download-btn:hover {
  background: #333;
  color: #4caf50;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: #666;
  text-align: center;
  gap: 8px;
}

.empty-icon {
  font-size: 24px;
}

.empty-text {
  font-size: 11px;
}

/* Scrollbar styling */
.file-list::-webkit-scrollbar {
  width: 4px;
}

.file-list::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.file-list::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.file-list::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>