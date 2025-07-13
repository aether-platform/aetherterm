/**
 * Common type definitions for AetherTerm
 */

// WebSocket event data types
export interface ChatMessageData {
  id: string
  senderId: string
  content: string
  timestamp: number
  username?: string
  avatar?: string
  type?: 'text' | 'system' | 'command'
  roomId?: string
}

export interface AIChatTypingData {
  isTyping: boolean
  sessionId?: string
}

export interface AIChatChunkData {
  chunk: string
  sessionId?: string
}

export interface AIChatCompleteData {
  message: string
  sessionId?: string
}

export interface AIChatErrorData {
  error: string
  sessionId?: string
}

export interface AIInfoResponseData {
  info: string
  sessionId?: string
}

export interface AIResetRetryResponseData {
  success: boolean
  message?: string
}

export interface TerminalReadyData {
  sessionId: string
  cols?: number
  rows?: number
}

export interface ErrorData {
  error: string
  message?: string
  code?: string
  sessionId?: string
}

export interface TerminalOutputData {
  sessionId: string
  data: string
  timestamp?: number
}

export interface TerminalClosedData {
  session?: string
  reason?: string
}

export interface LogSystemStats {
  cpu: number
  memory: number
  disk: number
  timestamp: number
}

export interface LogTerminalStats {
  terminal_id: string
  stats: {
    lines: number
    bytes: number
    commands: number
  }
}

export interface SearchResult {
  id: string
  line: string
  lineNumber: number
  match: string
}

// Process types
export interface ProcessInfo {
  name: string
  pid: number
  status: 'running' | 'stopped' | 'crashed'
  cpu?: number
  memory?: number
  uptime?: number
}

// Connection types
export interface ConnectionInfo {
  id: string
  name: string
  type: string
  status: 'connected' | 'disconnected' | 'error'
  details?: Record<string, unknown>
}

// File types
export interface S3File {
  key: string
  size: number
  lastModified: Date
  isFolder: boolean
  etag?: string
}

// Date formatting functions
export const formatDate = (date: Date | string | number): string => {
  const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date
  if (isNaN(d.getTime())) return 'Invalid Date'
  
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

export const formatTimestamp = (timestamp: number): string => {
  return formatDate(timestamp)
}

export const formatRelativeTime = (timestamp: number): string => {
  const now = Date.now()
  const diff = now - timestamp
  
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}