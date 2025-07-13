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
  
  // Check if current user has permission to control the terminal
  const hasControlPermission = (sessionId: string): boolean => {
    const permission = permissions.value.get(sessionId)
    const user = currentUser.value
    
    if (!permission || !user) return true // Default to allow if no permissions set
    
    // Owner always has permission
    if (permission.ownerId === user.sub) return true
    
    // Check if user has Viewer role (read-only)
    if (user.roles?.includes('Viewer')) return false
    
    // Check if generic users are allowed
    if (permission.allowGenericUsers) return true
    
    // Check if user is in the allowed list
    return permission.allowedUsers.includes(user.sub)
  }
  
  // Initialize permissions for a new session
  const initializePermissions = (sessionId: string, ownerId?: string) => {
    const owner = ownerId || currentUser.value?.sub || 'unknown'
    
    permissions.value.set(sessionId, {
      sessionId,
      ownerId: owner,
      allowedUsers: [],
      allowGenericUsers: false, // Default to restrictive
      createdAt: new Date(),
      updatedAt: new Date()
    })
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
    
    // Actions
    initializePermissions,
    toggleGenericUserAccess,
    grantUserAccess,
    revokeUserAccess
  }
})