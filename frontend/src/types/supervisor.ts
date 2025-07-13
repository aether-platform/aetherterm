/**
 * Supervisor-specific type definitions for AetherTerm
 */

export interface SupervisorCommandResponse {
  success: boolean
  message?: string
  data?: unknown
}

export interface TerminalListResponse {
  terminals: Array<{
    sessionId: string
    userId: string
    isActive: boolean
    createdAt: string
  }>
}

export interface TerminalContentResponse {
  content: string
  sessionId: string
}

export interface ProcessLogResponse {
  logs: string
  processName: string
}

export interface SupervisorProcess {
  name: string
  group: string
  pid: number
  state: string
  statename: string
  start: number
  stop: number
  now: number
  description: string
  spawnerr?: string
  exitstatus?: number
  stdout_logfile?: string
  stderr_logfile?: string
}