/**
 * Frontend Telemetry Configuration (Disabled)
 * 
 * Placeholder for future telemetry implementation.
 * Currently disabled to avoid OpenTelemetry dependency issues.
 */

// Mock telemetry interface for future implementation
export interface TelemetryConfig {
  serviceName: string
  serviceVersion: string
  environment: string
  otlpEndpoint?: string
  apiKey?: string
  enableConsole?: boolean
  sampleRate?: number
}

// Mock telemetry class - no-op implementation
export class FrontendTelemetry {
  private config: TelemetryConfig
  
  constructor(config: Partial<TelemetryConfig> = {}) {
    this.config = {
      serviceName: 'aetherterm-frontend',
      serviceVersion: '0.0.1',
      environment: 'development',
      enableConsole: import.meta.env.DEV,
      sampleRate: 1.0,
      ...config
    }
  }
  
  initialize(): void {
    // No-op implementation
    if (this.config.enableConsole) {
      console.log('📊 Telemetry (disabled): Frontend telemetry placeholder initialized')
    }
  }
  
  createSpan(name: string, attributes: Record<string, any> = {}) {
    // Return mock span
    return {
      setAttributes: (attrs: Record<string, any>) => {},
      setStatus: (status: any) => {},
      recordException: (error: Error) => {},
      end: () => {}
    }
  }
  
  shutdown(): Promise<void> {
    return Promise.resolve()
  }
}

// Global telemetry instance
let telemetryInstance: FrontendTelemetry | null = null

export function initializeTelemetry(config?: Partial<TelemetryConfig>): FrontendTelemetry {
  if (!telemetryInstance) {
    telemetryInstance = new FrontendTelemetry(config)
    telemetryInstance.initialize()
  }
  return telemetryInstance
}

export function getTelemetry(): FrontendTelemetry | null {
  return telemetryInstance
}

// Helper functions for span creation
export function createSpan(name: string, attributes: Record<string, any> = {}) {
  return telemetryInstance?.createSpan(name, attributes) || {
    setAttributes: () => {},
    setStatus: () => {},
    recordException: () => {},
    end: () => {}
  }
}

export function withSpan<T>(name: string, fn: () => T, attributes: Record<string, any> = {}): T {
  const span = createSpan(name, attributes)
  try {
    const result = fn()
    span.end()
    return result
  } catch (error) {
    span.recordException(error as Error)
    span.end()
    throw error
  }
}