<template>
  <v-dialog v-model="dialog" max-width="500px">
    <template v-slot:activator="{ props }">
      <v-btn
        v-bind="props"
        icon
        size="small"
        :title="isOwner ? 'Manage Permissions' : 'View Permissions'"
      >
        <v-icon>{{ isOwner ? 'mdi-account-key' : 'mdi-account-lock' }}</v-icon>
      </v-btn>
    </template>

    <v-card>
      <v-card-title>
        <span class="text-h5">Terminal Permissions</span>
      </v-card-title>

      <v-card-text>
        <v-container>
          <!-- Owner Information -->
          <v-row>
            <v-col cols="12">
              <v-chip class="mb-4" color="primary">
                <v-icon start>mdi-crown</v-icon>
                Owner: {{ ownerName }}
              </v-chip>
            </v-col>
          </v-row>

          <!-- Generic User Access Control (Only for Owner) -->
          <v-row v-if="isOwner">
            <v-col cols="12">
              <v-switch
                v-model="allowGenericUsers"
                label="Allow all non-owner users to control terminal"
                color="primary"
                @update:model-value="toggleGenericAccess"
              />
              <v-alert
                v-if="allowGenericUsers"
                type="info"
                density="compact"
                class="mt-2"
              >
                All authenticated users (except Viewers) can control this terminal
              </v-alert>
            </v-col>
          </v-row>

          <!-- Current Permission Status (For Non-Owners) -->
          <v-row v-if="!isOwner">
            <v-col cols="12">
              <v-alert
                :type="hasPermission ? 'success' : 'warning'"
                density="compact"
              >
                <v-icon>{{ hasPermission ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
                {{ permissionStatusText }}
              </v-alert>
            </v-col>
          </v-row>

          <!-- Specific User Permissions (Future Enhancement) -->
          <v-row v-if="isOwner && !allowGenericUsers">
            <v-col cols="12">
              <v-alert type="info" density="compact">
                Individual user permissions coming soon...
              </v-alert>
            </v-col>
          </v-row>
        </v-container>
      </v-card-text>

      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" text @click="dialog = false">
          Close
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useTerminalPermissionsStore } from '../../stores/terminalPermissionsStore'

interface Props {
  sessionId: string
}

const props = defineProps<Props>()

const dialog = ref(false)
const permissionsStore = useTerminalPermissionsStore()

// Get permission settings
const permissions = computed(() => permissionsStore.getPermissions(props.sessionId))

// Check if current user is owner
const isOwner = computed(() => permissionsStore.isOwner(props.sessionId))

// Check if current user has permission
const hasPermission = computed(() => permissionsStore.hasControlPermission(props.sessionId))

// Generic users access setting
const allowGenericUsers = ref(permissions.value?.allowGenericUsers || false)

// Owner name (for display)
const ownerName = computed(() => {
  const owner = permissions.value?.ownerId
  if (owner === permissionsStore.currentUser?.sub) {
    return 'You'
  }
  return permissionsStore.currentUser?.username || owner || 'Unknown'
})

// Permission status text for non-owners
const permissionStatusText = computed(() => {
  if (hasPermission.value) {
    if (permissions.value?.allowGenericUsers) {
      return 'You have control access (generic users allowed)'
    }
    return 'You have control access'
  }
  return 'You have read-only access'
})

// Initialize permissions when component mounts
watch(() => props.sessionId, (newSessionId) => {
  if (newSessionId && !permissions.value) {
    permissionsStore.initializePermissions(newSessionId)
  }
}, { immediate: true })

// Toggle generic user access
const toggleGenericAccess = () => {
  permissionsStore.toggleGenericUserAccess(props.sessionId)
}

// Update local state when permissions change
watch(() => permissions.value?.allowGenericUsers, (newValue) => {
  if (newValue !== undefined) {
    allowGenericUsers.value = newValue
  }
})
</script>

<style scoped>
.v-chip {
  font-weight: 500;
}
</style>