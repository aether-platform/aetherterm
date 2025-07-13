/**
 * Configuration constants for AetherTerm
 */

// Server configuration
export const DEFAULT_AGENT_SERVER_HOST = 'localhost'
export const DEFAULT_AGENT_SERVER_PORT = 57575
export const DEFAULT_CONTROL_SERVER_PORT = 8765

// WebSocket configuration
export const SOCKET_RECONNECT_ATTEMPTS = 5
export const SOCKET_RECONNECT_DELAY = 1000
export const SOCKET_TIMEOUT = 10000

// Terminal configuration
export const DEFAULT_TERMINAL_COLS = 80
export const DEFAULT_TERMINAL_ROWS = 24
export const TERMINAL_SCROLLBACK = 2000
export const TERMINAL_FIT_DEBOUNCE_MS = 100
export const TERMINAL_OUTPUT_FLUSH_MS = 8

// Session configuration
export const SESSION_RETRY_DELAY = 1000
export const SESSION_MAX_RETRIES = 10

// Test configuration
export const DEFAULT_TEST_LOG_SIZE = 5000
export const DEFAULT_TEST_LOG_INTERVAL = 1000

// Random ID generation
export const RANDOM_ID_MIN = 50000
export const RANDOM_ID_MAX = 1000000

// Get configuration from environment or use defaults
export const getAgentServerUrl = (): string => {
  const envUrl = import.meta.env.VITE_AGENT_SERVER_URL
  if (envUrl) return envUrl
  
  const host = import.meta.env.VITE_AGENT_SERVER_HOST || DEFAULT_AGENT_SERVER_HOST
  const port = import.meta.env.VITE_AGENT_SERVER_PORT || DEFAULT_AGENT_SERVER_PORT
  return `http://${host}:${port}`
}

export const getControlServerUrl = (): string => {
  const envUrl = import.meta.env.VITE_CONTROL_SERVER_URL
  if (envUrl) return envUrl
  
  const host = import.meta.env.VITE_CONTROL_SERVER_HOST || DEFAULT_AGENT_SERVER_HOST
  const port = import.meta.env.VITE_CONTROL_SERVER_PORT || DEFAULT_CONTROL_SERVER_PORT
  return `http://${host}:${port}`
}