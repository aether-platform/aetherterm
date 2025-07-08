/**
 * Workspace Token Manager
 * 
 * Generates and manages workspace tokens for cross-window session sharing
 */

export class WorkspaceTokenManager {
  private static readonly TOKEN_KEY = 'aetherterm_workspace_token'
  private static readonly TOKEN_LENGTH = 32
  
  /**
   * Generate a new workspace token
   */
  static generateToken(): string {
    const array = new Uint8Array(this.TOKEN_LENGTH)
    crypto.getRandomValues(array)
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('')
  }
  
  /**
   * Get or create workspace token
   */
  static getOrCreateToken(): string {
    let token = localStorage.getItem(this.TOKEN_KEY)
    
    if (!token) {
      token = this.generateToken()
      localStorage.setItem(this.TOKEN_KEY, token)
      console.log('📋 WORKSPACE: Generated new workspace token:', token)
    } else {
      console.log('📋 WORKSPACE: Using existing workspace token:', token)
    }
    
    return token
  }
  
  /**
   * Get current workspace token
   */
  static getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY)
  }
  
  /**
   * Clear workspace token (for logout/reset)
   */
  static clearToken(): void {
    localStorage.removeItem(this.TOKEN_KEY)
    console.log('📋 WORKSPACE: Cleared workspace token')
  }
  
  /**
   * Validate token format
   */
  static isValidToken(token: string): boolean {
    return /^[0-9a-f]{64}$/.test(token)
  }
}