/**
 * Logger utility for AetherTerm
 * Provides environment-aware logging with different levels
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4
}

interface LoggerConfig {
  level: LogLevel
  prefix?: string
  enableConsole: boolean
  enableRemote?: boolean
}

class Logger {
  private config: LoggerConfig
  
  constructor(config: Partial<LoggerConfig> = {}) {
    this.config = {
      level: import.meta.env.DEV ? LogLevel.DEBUG : LogLevel.WARN,
      enableConsole: true,
      enableRemote: false,
      ...config
    }
  }
  
  private shouldLog(level: LogLevel): boolean {
    return level >= this.config.level && this.config.enableConsole
  }
  
  private formatMessage(level: string, message: string, ...args: unknown[]): string {
    const timestamp = new Date().toISOString()
    const prefix = this.config.prefix ? `[${this.config.prefix}] ` : ''
    return `${timestamp} [${level}] ${prefix}${message}`
  }
  
  debug(message: string, ...args: unknown[]): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      console.log(this.formatMessage('DEBUG', message), ...args)
    }
  }
  
  info(message: string, ...args: unknown[]): void {
    if (this.shouldLog(LogLevel.INFO)) {
      console.info(this.formatMessage('INFO', message), ...args)
    }
  }
  
  warn(message: string, ...args: unknown[]): void {
    if (this.shouldLog(LogLevel.WARN)) {
      console.warn(this.formatMessage('WARN', message), ...args)
    }
  }
  
  error(message: string, ...args: unknown[]): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      console.error(this.formatMessage('ERROR', message), ...args)
    }
  }
  
  setLevel(level: LogLevel): void {
    this.config.level = level
  }
  
  setPrefix(prefix: string): void {
    this.config.prefix = prefix
  }
}

// Create default logger instance
export const logger = new Logger()

// Create specialized loggers
export const terminalLogger = new Logger({ prefix: 'TERMINAL' })
export const socketLogger = new Logger({ prefix: 'SOCKET' })
export const storeLogger = new Logger({ prefix: 'STORE' })
export const authLogger = new Logger({ prefix: 'AUTH' })

// Export factory function for custom loggers
export const createLogger = (config?: Partial<LoggerConfig>): Logger => {
  return new Logger(config)
}