/**
 * JWT Token utility functions for authentication
 */

const JWT_TOKEN_KEY = 'aetherterm_jwt_token'
const JWT_REFRESH_TOKEN_KEY = 'aetherterm_refresh_token'

/**
 * Get JWT token from localStorage
 */
export function getJWTToken(): string | null {
  try {
    return localStorage.getItem(JWT_TOKEN_KEY)
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
 * Decode JWT token (without verification)
 */
export function decodeJWTToken(token: string): any {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      throw new Error('Invalid JWT token format')
    }
    
    const payload = parts[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(decoded)
  } catch (error) {
    console.error('Failed to decode JWT token:', error)
    return null
  }
}

/**
 * Check if JWT token exists and is not expired
 */
export function checkJWTToken(): boolean {
  const token = getJWTToken()
  if (!token) {
    return false
  }

  try {
    const payload = decodeJWTToken(token)
    if (!payload) {
      return false
    }

    // Check expiration (exp is in seconds, Date.now() is in milliseconds)
    const now = Math.floor(Date.now() / 1000)
    if (payload.exp && payload.exp < now) {
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
    const payload = decodeJWTToken(token)
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
 * Get user info from JWT token
 */
export function getUserFromToken(): any {
  const token = getJWTToken()
  if (!token) {
    return null
  }

  try {
    const payload = decodeJWTToken(token)
    return payload ? {
      sub: payload.sub,
      username: payload.username || payload.preferred_username,
      email: payload.email,
      roles: payload.roles || [],
      exp: payload.exp,
      iat: payload.iat
    } : null
  } catch (error) {
    console.error('Failed to get user from token:', error)
    return null
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
 * Check if user has required role
 */
export function hasRole(requiredRole: string): boolean {
  const user = getUserFromToken()
  if (!user || !user.roles) {
    return false
  }
  
  return user.roles.includes(requiredRole)
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