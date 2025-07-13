/**
 * Terminal Permissions Store
 * 
 * Manages permission controls for terminal access.
 * Allows owners to grant/revoke permissions to other users.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getCurrentUser } from '@/utils/auth'

export interface TerminalPermission {
  sessionId: string
  ownerId: string
  allowedUsers: string[]  // List of user IDs who have been granted access
  allowGenericUsers: boolean  // Whether to allow all non-owner users
  createdAt: Date
  updatedAt: Date
}

export const useTerminalPermissionsStore = defineStore('terminalPermissions', () => {
  // Permissions map: sessionId -> permission settings
  const permissions = ref<Map<string, TerminalPermission>>(new Map())
  
  // Get current user info
  const currentUser = computed(() => getCurrentUser())
  
  // Check if current user is the owner of a session
  const isOwner = (sessionId: string): boolean => {
    const permission = permissions.value.get(sessionId)
    if (!permission) return true // If no permissions set, assume owner
    
    return permission.ownerId === currentUser.value?.sub
  }
  
  // Check if we're in debug mode (URL contains debug or workspace-debug)
  const isDebugMode = (): boolean => {
    const path = window.location.pathname
    return path.includes('/debug') || path.includes('/workspace-debug')
  }
  
  // Check if current user has permission to control the terminal
  const hasControlPermission = (sessionId: string): boolean => {
    const permission = permissions.value.get(sessionId)
    const user = currentUser.value
    
    // In development mode (no auth), always allow
    if (!user || !user.sub) {
      console.log('📋 PERMISSIONS: No user context - allowing in development mode')
      return true
    }
    
    // Anonymous users can only access debug mode
    if (user.roles?.includes('Anonymous') && !isDebugMode()) {
      console.log('📋 PERMISSIONS: Anonymous user outside debug mode - blocking')
      return false
    }
    
    if (!permission) {
      console.log('📋 PERMISSIONS: No permission settings - allowing')
      return true
    }
    
    // Owner always has permission
    if (permission.ownerId === user.sub) {
      console.log('📋 PERMISSIONS: User is owner - allowing')
      return true
    }
    
    // Check role-based permissions
    if (user.roles?.includes('Supervisor')) {
      console.log('📋 PERMISSIONS: User has Supervisor role - allowing')
      return true
    }
    
    if (user.roles?.includes('Owner')) {
      console.log('📋 PERMISSIONS: User has Owner role - allowing')
      return true
    }
    
    if (user.roles?.includes('Viewer')) {
      console.log('📋 PERMISSIONS: User has Viewer role - blocking')
      return false
    }
    
    if (user.roles?.includes('Anonymous')) {
      console.log('📋 PERMISSIONS: User has Anonymous role - blocking')
      return false
    }
    
    // Check if generic users are allowed
    if (permission.allowGenericUsers) {
      console.log('📋 PERMISSIONS: Generic users allowed - allowing')
      return true
    }
    
    // Check if user is in the allowed list
    const allowed = permission.allowedUsers.includes(user.sub)
    console.log(`📋 PERMISSIONS: User in allowed list: ${allowed}`)
    return allowed
  }
  
  // Initialize permissions for a new session
  const initializePermissions = (sessionId: string, ownerId?: string) => {
    const owner = ownerId || currentUser.value?.sub || 'dev-user'
    
    // In development mode (no auth), be permissive
    const isDevelopmentMode = !currentUser.value || !currentUser.value.sub
    
    permissions.value.set(sessionId, {
      sessionId,
      ownerId: owner,
      allowedUsers: [],
      allowGenericUsers: isDevelopmentMode, // Allow in development mode
      createdAt: new Date(),
      updatedAt: new Date()
    })
    
    console.log(`📋 PERMISSIONS: Initialized session ${sessionId}, owner: ${owner}, dev mode: ${isDevelopmentMode}`)
  }
  
  // Toggle generic user access
  const toggleGenericUserAccess = (sessionId: string) => {
    const permission = permissions.value.get(sessionId)
    if (!permission) return
    
    permission.allowGenericUsers = !permission.allowGenericUsers
    permission.updatedAt = new Date()
    
    // Persist to localStorage
    savePermissions()
  }
  
  // Grant access to a specific user
  const grantUserAccess = (sessionId: string, userId: string) => {
    const permission = permissions.value.get(sessionId)
    if (!permission) return
    
    if (!permission.allowedUsers.includes(userId)) {
      permission.allowedUsers.push(userId)
      permission.updatedAt = new Date()
      savePermissions()
    }
  }
  
  // Revoke access from a specific user
  const revokeUserAccess = (sessionId: string, userId: string) => {
    const permission = permissions.value.get(sessionId)
    if (!permission) return
    
    const index = permission.allowedUsers.indexOf(userId)
    if (index > -1) {
      permission.allowedUsers.splice(index, 1)
      permission.updatedAt = new Date()
      savePermissions()
    }
  }
  
  // Get permission settings for a session
  const getPermissions = (sessionId: string): TerminalPermission | undefined => {
    return permissions.value.get(sessionId)
  }
  
  // Save permissions to localStorage
  const savePermissions = () => {
    const permissionsArray = Array.from(permissions.value.entries())
    localStorage.setItem('terminalPermissions', JSON.stringify(permissionsArray))
  }
  
  // Load permissions from localStorage
  const loadPermissions = () => {
    try {
      const stored = localStorage.getItem('terminalPermissions')
      if (stored) {
        const permissionsArray = JSON.parse(stored)
        permissions.value = new Map(permissionsArray.map(([k, v]: [string, any]) => [
          k,
          {
            ...v,
            createdAt: new Date(v.createdAt),
            updatedAt: new Date(v.updatedAt)
          }
        ]))
      }
    } catch (error) {
      console.error('Failed to load terminal permissions:', error)
    }
  }
  
  // Initialize by loading from localStorage
  loadPermissions()
  
  return {
    // State
    permissions,
    currentUser,
    
    // Getters
    isOwner,
    hasControlPermission,
    getPermissions,
    isDebugMode,
    
    // Actions
    initializePermissions,
    toggleGenericUserAccess,
    grantUserAccess,
    revokeUserAccess
  }
})