import { defineStore } from 'pinia'

interface BufferLine {
  content: string
  timestamp: number
  type: 'input' | 'output' | 'error'
}

interface ScreenBuffer {
  lines: BufferLine[]
  maxLines: number
  currentLine: number
  savedStates: { [key: string]: BufferLine[] }
}

interface SessionBuffer {
  [sessionId: string]: ScreenBuffer
}

export const useScreenBufferStore = defineStore('screenBuffer', {
  state: (): { buffers: SessionBuffer } => ({
    buffers: {}
  }),

  getters: {
    getBuffer: (state) => (sessionId: string): ScreenBuffer => {
      if (!state.buffers[sessionId]) {
        state.buffers[sessionId] = {
          lines: [],
          maxLines: 5000,
          currentLine: 0,
          savedStates: {}
        }
      }
      return state.buffers[sessionId]
    },

    getBufferLines: (state) => (sessionId: string, startLine?: number, endLine?: number): BufferLine[] => {
      const buffer = state.buffers[sessionId]
      if (!buffer) return []
      
      const start = startLine ?? 0
      const end = endLine ?? buffer.lines.length
      return buffer.lines.slice(start, end)
    },

    getBufferStats: (state) => (sessionId: string) => {
      const buffer = state.buffers[sessionId]
      if (!buffer) return { totalLines: 0, currentLine: 0, maxLines: 0 }
      
      return {
        totalLines: buffer.lines.length,
        currentLine: buffer.currentLine,
        maxLines: buffer.maxLines
      }
    }
  },

  actions: {
    addLine(sessionId: string, content: string, type: 'input' | 'output' | 'error' = 'output') {
      const buffer = this.getBuffer(sessionId)
      
      const newLine: BufferLine = {
        content,
        timestamp: Date.now(),
        type
      }
      
      buffer.lines.push(newLine)
      buffer.currentLine = buffer.lines.length - 1
      
      // Trim buffer if it exceeds max lines
      if (buffer.lines.length > buffer.maxLines) {
        const excess = buffer.lines.length - buffer.maxLines
        buffer.lines.splice(0, excess)
        buffer.currentLine = Math.max(0, buffer.currentLine - excess)
      }
      
      // Note: Persistence is handled by the backend, not localStorage
    },


    clearBuffer(sessionId: string) {
      const buffer = this.getBuffer(sessionId)
      buffer.lines = []
      buffer.currentLine = 0
    },

    saveBufferState(sessionId: string, stateName: string) {
      const buffer = this.getBuffer(sessionId)
      buffer.savedStates[stateName] = JSON.parse(JSON.stringify(buffer.lines))
    },

    restoreBufferState(sessionId: string, stateName: string): boolean {
      const buffer = this.getBuffer(sessionId)
      const savedState = buffer.savedStates[stateName]
      
      if (savedState) {
        buffer.lines = JSON.parse(JSON.stringify(savedState))
        buffer.currentLine = buffer.lines.length - 1
        return true
      }
      return false
    },

    deleteBufferState(sessionId: string, stateName: string) {
      const buffer = this.getBuffer(sessionId)
      delete buffer.savedStates[stateName]
    },

    setMaxBufferLines(sessionId: string, maxLines: number) {
      const buffer = this.getBuffer(sessionId)
      buffer.maxLines = Math.max(100, maxLines)
      
      // Trim if current buffer exceeds new limit
      if (buffer.lines.length > buffer.maxLines) {
        const excess = buffer.lines.length - buffer.maxLines
        buffer.lines.splice(0, excess)
        buffer.currentLine = Math.max(0, buffer.currentLine - excess)
      }
    },

    exportBuffer(sessionId: string, format: 'text' | 'json' = 'text'): string {
      const buffer = this.getBuffer(sessionId)
      
      if (format === 'json') {
        return JSON.stringify({
          sessionId,
          exportTime: new Date().toISOString(),
          lines: buffer.lines
        }, null, 2)
      }
      
      return buffer.lines
        .map(line => `[${new Date(line.timestamp).toISOString()}] ${line.type.toUpperCase()}: ${line.content}`)
        .join('\n')
    },

    importBuffer(sessionId: string, data: string, format: 'text' | 'json' = 'json'): boolean {
      try {
        if (format === 'json') {
          const parsed = JSON.parse(data)
          if (parsed.lines && Array.isArray(parsed.lines)) {
            const buffer = this.getBuffer(sessionId)
            buffer.lines = parsed.lines
            buffer.currentLine = buffer.lines.length - 1
            return true
          }
        }
        return false
      } catch {
        return false
      }
    },

    searchBuffer(sessionId: string, query: string, caseSensitive: boolean = false): Array<{ lineIndex: number, line: BufferLine }> {
      const buffer = this.getBuffer(sessionId)
      const searchQuery = caseSensitive ? query : query.toLowerCase()
      
      return buffer.lines
        .map((line, index) => ({ lineIndex: index, line }))
        .filter(({ line }) => {
          const content = caseSensitive ? line.content : line.content.toLowerCase()
          return content.includes(searchQuery)
        })
    },

    removeSession(sessionId: string) {
      delete this.buffers[sessionId]
    }
  }
})