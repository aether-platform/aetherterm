/**
 * Unified JWT authentication utilities for AetherTerm
 * Combines best features from both auth.ts and jwtUtils.ts
 */

// Storage constants
const JWT_TOKEN_KEY = 'aetherterm_jwt_token'
const JWT_REFRESH_TOKEN_KEY = 'aetherterm_refresh_token'

export interface JWTPayload {
  sub?: string
  email?: string
  username?: string
  preferred_username?: string
  roles?: string[]
  permissions?: string[]
  isSupervisor?: boolean
  exp?: number
  iat?: number
}

export interface UserInfo {
  sub?: string
  username?: string
  email?: string
  roles?: string[]
  permissions?: string[]
  isSupervisor: boolean
  exp?: number
  iat?: number
}

/**
 * Decode JWT token without verification (client-side only)
 */
export function decodeJWT(token: string): JWTPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      return null
    }

    const payload = parts[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded) as JWTPayload
  } catch (error) {
    console.error('Failed to decode JWT:', error)
    return null
  }
}

/**
 * Check if JWT token is expired
 */
export function isTokenExpired(payload: JWTPayload): boolean {
  if (!payload.exp) return true
  return Date.now() >= payload.exp * 1000
}

/**
 * Get JWT token from multiple sources (comprehensive fallback)
 */
export function getJWTToken(): string | null {
  try {
    // Try primary storage location first
    const primary = localStorage.getItem(JWT_TOKEN_KEY)
    if (primary) return primary

    // Try alternative storage keys
    const stored = localStorage.getItem('jwt_token') || localStorage.getItem('auth_token')
    if (stored) return stored

    // Try sessionStorage
    const session = sessionStorage.getItem('jwt_token') || sessionStorage.getItem('auth_token')
    if (session) return session

    // Try URL parameters (for direct links)
    const urlParams = new URLSearchParams(window.location.search)
    const urlToken = urlParams.get('token')
    if (urlToken) return urlToken

    // Try cookies
    const cookies = document.cookie.split(';')
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=')
      if (name === 'jwt_token' || name === 'auth_token') {
        return decodeURIComponent(value)
      }
    }

    return null
  } catch (error) {
    console.error('Failed to get JWT token:', error)
    return null
  }
}

/**
 * Set JWT token in localStorage
 */
export function setJWTToken(token: string): void {
  try {
    localStorage.setItem(JWT_TOKEN_KEY, token)
  } catch (error) {
    console.error('Failed to set JWT token:', error)
  }
}

/**
 * Remove JWT token from localStorage
 */
export function removeJWTToken(): void {
  try {
    localStorage.removeItem(JWT_TOKEN_KEY)
    localStorage.removeItem(JWT_REFRESH_TOKEN_KEY)
    // Also clean up alternative keys
    localStorage.removeItem('jwt_token')
    localStorage.removeItem('auth_token')
  } catch (error) {
    console.error('Failed to remove JWT token:', error)
  }
}

/**
 * Get refresh token from localStorage
 */
export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(JWT_REFRESH_TOKEN_KEY)
  } catch (error) {
    console.error('Failed to get refresh token:', error)
    return null
  }
}

/**
 * Set refresh token in localStorage
 */
export function setRefreshToken(token: string): void {
  try {
    localStorage.setItem(JWT_REFRESH_TOKEN_KEY, token)
  } catch (error) {
    console.error('Failed to set refresh token:', error)
  }
}

/**
 * Check if JWT token exists and is not expired
 */
export function isTokenValid(): boolean {
  const token = getJWTToken()
  if (!token) {
    return false
  }

  try {
    const payload = decodeJWT(token)
    if (!payload) {
      return false
    }

    // Check expiration
    if (isTokenExpired(payload)) {
      console.warn('JWT token has expired')
      removeJWTToken()
      return false
    }

    return true
  } catch (error) {
    console.error('Failed to validate JWT token:', error)
    removeJWTToken()
    return false
  }
}

/**
 * Check if token is close to expiring (within 5 minutes)
 */
export function isTokenNearExpiry(): boolean {
  const token = getJWTToken()
  if (!token) {
    return true
  }

  try {
    const payload = decodeJWT(token)
    if (!payload || !payload.exp) {
      return true
    }

    const now = Math.floor(Date.now() / 1000)
    const expiryTime = payload.exp
    const fiveMinutes = 5 * 60 // 5 minutes in seconds

    return (expiryTime - now) < fiveMinutes
  } catch (error) {
    console.error('Failed to check token expiry:', error)
    return true
  }
}

/**
 * Check if current user has supervisor privileges
 */
export function isSupervisor(): boolean {
  const token = getJWTToken()
  if (!token) return false

  const payload = decodeJWT(token)
  if (!payload || isTokenExpired(payload)) return false

  // Check multiple possible supervisor indicators
  if (payload.isSupervisor === true) return true
  if (payload.roles?.includes('supervisor') || payload.roles?.includes('admin')) return true
  if (
    payload.permissions?.includes('terminal:supervise') ||
    payload.permissions?.includes('admin:all')
  )
    return true

  return false
}

/**
 * Check if user has required role
 */
export function hasRole(requiredRole: string): boolean {
  const user = getCurrentUser()
  if (!user || !user.roles) {
    return false
  }
  
  return user.roles.includes(requiredRole)
}

/**
 * Get comprehensive user information from JWT
 */
export function getCurrentUser(): UserInfo | null {
  const token = getJWTToken()
  if (!token) return null

  const payload = decodeJWT(token)
  if (!payload || isTokenExpired(payload)) return null

  return {
    sub: payload.sub,
    username: payload.username || payload.preferred_username,
    email: payload.email,
    roles: payload.roles || [],
    permissions: payload.permissions || [],
    isSupervisor: isSupervisor(),
    exp: payload.exp,
    iat: payload.iat
  }
}

/**
 * Create Authorization header with Bearer token
 */
export function getAuthHeader(): Record<string, string> {
  const token = getJWTToken()
  if (!token) {
    return {}
  }
  
  return {
    'Authorization': `Bearer ${token}`
  }
}

/**
 * Refresh JWT token using refresh token
 */
export async function refreshJWTToken(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    return false
  }

  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken })
    })

    if (response.ok) {
      const data = await response.json()
      if (data.access_token) {
        setJWTToken(data.access_token)
        if (data.refresh_token) {
          setRefreshToken(data.refresh_token)
        }
        return true
      }
    }
  } catch (error) {
    console.error('Failed to refresh JWT token:', error)
  }

  // If refresh failed, remove tokens
  removeJWTToken()
  return false
}

// Legacy alias for backward compatibility
export const checkJWTToken = isTokenValid
export const getUserFromToken = getCurrentUser
export const decodeJWTToken = decodeJWT
