<template>
  <div class="s3-sidebar">
    <S3Header :loading="loading" @refresh="refreshData" />
    
    <div class="sidebar-content">
      <S3AuthStatus :is-authenticated="isAuthenticated" />
      
      <S3StatusIndicator :s3-status="s3Status" />
      
      <S3BucketList
        :is-authenticated="isAuthenticated"
        :buckets="buckets"
        :selected-bucket="selectedBucket"
        @select-bucket="selectBucket"
      />
      
      <S3FileList
        :selected-bucket="selectedBucket"
        :current-path="currentPath"
        :current-path-display="currentPathDisplay"
        :files="files"
        @upload-files="openUploadModal"
        @create-folder="createFolder"
        @navigate-up="navigateUp"
        @navigate-to-folder="navigateToFolder"
        @download-file="downloadFile"
      />
    </div>

    <div v-if="loading" class="loading-indicator">
      <div class="spinner">⏳</div>
    </div>

    <S3UploadModal
      :visible="showUploadModal"
      :uploads="uploads"
      @close="closeUploadModal"
      @upload-files="handleFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import S3Header from './s3/S3Header.vue'
import S3AuthStatus from './s3/S3AuthStatus.vue'
import S3StatusIndicator from './s3/S3StatusIndicator.vue'
import S3BucketList from './s3/S3BucketList.vue'
import S3FileList from './s3/S3FileList.vue'
import S3UploadModal from './s3/S3UploadModal.vue'

// State
const loading = ref(false)
const buckets = ref<Array<{ name: string; created: string }>>([])
const selectedBucket = ref('')
const currentPath = ref('')
const files = ref<Array<any>>([])
const showUploadModal = ref(false)
const uploads = ref<Array<{ name: string; progress: number }>>([])

interface S3Status {
  status: string
  aws_available: boolean
  message: string
}

const s3Status = ref<S3Status>({
  status: '',
  aws_available: false,
  message: ''
})

// Computed
const isAuthenticated = computed(() => true) // Page is OIDC protected
const currentPathDisplay = computed(() => {
  if (!currentPath.value) return selectedBucket.value
  return `${selectedBucket.value}/${currentPath.value}`
})

// API Functions - No authentication needed as page is OIDC protected
const makeRequest = async (url: string, options: RequestInit = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }

  const response = await fetch(url, { ...options, headers })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(`API Error: ${response.status} - ${error}`)
  }
  return response.json()
}

const checkS3Status = async () => {
  try {
    const response = await fetch('/api/s3/status')
    const status = await response.json()
    s3Status.value = status
  } catch (error) {
    console.error('Failed to check S3 status:', error)
    s3Status.value = {
      status: 'error',
      aws_available: false,
      message: 'Failed to check S3 status'
    }
  }
}

const refreshBuckets = async () => {
  loading.value = true
  try {
    const data = await makeRequest('/api/s3/buckets')
    buckets.value = data.buckets || []
  } catch (error) {
    console.error('Failed to load buckets:', error)
    buckets.value = []
  } finally {
    loading.value = false
  }
}

const selectBucket = async (bucketName: string) => {
  selectedBucket.value = bucketName
  currentPath.value = ''
  await loadFiles()
}

const loadFiles = async () => {
  if (!selectedBucket.value) return

  loading.value = true
  try {
    const prefix = currentPath.value ? `?prefix=${encodeURIComponent(currentPath.value)}` : ''
    const data = await makeRequest(`/api/s3/files/${selectedBucket.value}${prefix}`)
    files.value = data.files || []
  } catch (error) {
    console.error('Failed to load files:', error)
    files.value = []
  } finally {
    loading.value = false
  }
}

const navigateToFolder = (file: any) => {
  if (file.type === 'folder') {
    const folderPath = file.key || file.name
    currentPath.value = currentPath.value ? `${currentPath.value}/${folderPath}` : folderPath
    loadFiles()
  }
}

const navigateUp = () => {
  const pathParts = currentPath.value.split('/')
  pathParts.pop()
  currentPath.value = pathParts.join('/')
  loadFiles()
}

const downloadFile = async (file: any) => {
  try {
    const filePath = file.key || file.name
    const response = await fetch(
      `/api/s3/download/${selectedBucket.value}?key=${encodeURIComponent(filePath)}`
    )

    if (response.ok) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filePath.split('/').pop() || 'download'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    }
  } catch (error) {
    console.error('Download error:', error)
  }
}

const openUploadModal = () => {
  showUploadModal.value = true
}

const closeUploadModal = () => {
  showUploadModal.value = false
  uploads.value = []
}

const handleFileSelect = async (fileList: FileList) => {
  const files = Array.from(fileList)
  
  for (const file of files) {
    const upload = { name: file.name, progress: 0 }
    uploads.value.push(upload)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const filePath = currentPath.value ? `${currentPath.value}/${file.name}` : file.name

      const response = await fetch(
        `/api/s3/upload/${selectedBucket.value}?key=${encodeURIComponent(filePath)}`,
        {
          method: 'POST',
          body: formData
        }
      )

      if (response.ok) {
        upload.progress = 100
        setTimeout(() => loadFiles(), 1000)
      }
    } catch (error) {
      console.error('Upload error:', error)
    }
  }
}

const createFolder = async () => {
  const folderName = prompt('Enter folder name:')
  if (!folderName) return

  try {
    const folderPath = currentPath.value ? `${currentPath.value}/${folderName}/` : `${folderName}/`

    const response = await fetch(
      `/api/s3/create-folder/${selectedBucket.value}?key=${encodeURIComponent(folderPath)}`,
      {
        method: 'POST'
      }
    )

    if (response.ok) {
      await loadFiles()
    }
  } catch (error) {
    console.error('Create folder error:', error)
  }
}

const refreshData = () => {
  checkS3Status()
  if (isAuthenticated.value) {
    refreshBuckets()
    if (selectedBucket.value) {
      loadFiles()
    }
  }
}

onMounted(() => {
  refreshData()
})
</script>

<style scoped>
.s3-sidebar {
  height: 100%;
  width: 100%;
  background: #1e1e1e;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.loading-indicator {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.spinner {
  font-size: 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Scrollbar styling */
.sidebar-content::-webkit-scrollbar {
  width: 4px;
}

.sidebar-content::-webkit-scrollbar-track {
  background: #2a2a2a;
}

.sidebar-content::-webkit-scrollbar-thumb {
  background: #666;
  border-radius: 2px;
}

.sidebar-content::-webkit-scrollbar-thumb:hover {
  background: #888;
}
</style>