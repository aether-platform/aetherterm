# Session Sharing Analysis - AetherTerm Platform

## Summary of Findings

After analyzing the codebase, I've identified the key reasons why sessions are not properly shared across different browser windows:

## 1. Session ID Generation Issues

### Problem: Time-based Workspace IDs
- **Location**: `/frontend/src/stores/workspaceStore.ts` (line 223)
- **Issue**: Workspace IDs are generated using `workspace_${Date.now()}`
- **Impact**: Each window might create its own workspace if timing is off

```typescript
const workspaceId = `workspace_${Date.now()}`
```

### Problem: No Client ID Persistence
- **Location**: Backend session management doesn't persist client IDs across windows
- **Issue**: Each browser window gets a new Socket.IO connection with a unique `sid`
- **Impact**: Backend treats each window as a separate client

## 2. Session Storage Architecture

### Working Correctly:
- ✅ Workspace data is stored in `localStorage` (persistent across windows)
- ✅ Cross-tab synchronization via `BroadcastChannel` API is implemented
- ✅ Session IDs are stored with workspace data

### Not Working:
- ❌ Socket.IO connections are per-window (not shared)
- ❌ Backend doesn't have a mechanism to associate multiple socket connections with the same user/workspace
- ❌ No client identifier that persists across windows

## 3. Key Components Analysis

### Frontend Storage (`/frontend/src/stores/workspace/persistenceManager.ts`)
- Uses `localStorage` for persistence (correct for cross-window sharing)
- Stores workspace data with session IDs
- Keys used:
  - `aetherterm_workspaces` - List of workspace IDs
  - `aetherterm_current_workspace` - Current workspace ID
  - `aetherterm_workspaces_${id}` - Individual workspace data

### Backend Session Management (`/src/aetherterm/agentserver/domain/services/workspace/session_manager.py`)
- Sessions are tied to `client_id` (which is the Socket.IO `sid`)
- No mechanism to transfer or share sessions between different socket connections
- Each window connection gets its own `client_id`

## 4. How to Verify the Issue

### Method 1: Use the Debug Page
1. Navigate to `http://localhost:57575/debug/workspace` in two different browser windows
2. Check the following:
   - **Window ID**: Should be different (expected)
   - **Socket ID**: Will be different (this is the issue)
   - **Workspace ID**: Should be the same if sharing works
   - **LocalStorage Data**: Should show the same workspace data

### Method 2: Manual Testing
1. Open the terminal in Window A
2. Create a new tab/terminal
3. Note the session ID in the console logs
4. Open Window B
5. Check if the same session appears

### Method 3: Check Browser Developer Tools
1. Open DevTools in both windows
2. Go to Application → Local Storage
3. Check if `aetherterm_workspaces` contains the same data
4. Go to Network → WS tab
5. Note that Socket.IO connections have different `sid` values

## 5. Root Cause

The fundamental issue is that the backend uses Socket.IO's connection ID (`sid`) as the client identifier. Since each browser window creates a new WebSocket connection, they get different `sid` values and are treated as separate clients by the backend.

## 6. Solution Approaches

### Option 1: Implement User-Based Sessions
- Add user authentication (JWT tokens)
- Associate sessions with user IDs instead of socket IDs
- Allow multiple socket connections per user

### Option 2: Implement Workspace Tokens
- Generate a unique workspace token when creating a workspace
- Store this token in localStorage
- Use it to authenticate workspace access across windows

### Option 3: Session Transfer Mechanism
- Implement a session transfer API
- When a new window connects, check localStorage for existing sessions
- Request session transfer from the backend

## 7. Current Workarounds

While sessions aren't truly shared, the following works:
1. Workspace structure is preserved (tabs, panes)
2. Session IDs are stored and attempted to reconnect
3. Screen buffer content is saved in localStorage

However, the backend terminal processes are not shared because each window is treated as a separate client.

## 8. Testing Commands

```bash
# Check if multiple connections exist for the same session
curl http://localhost:57575/api/sessions

# Monitor WebSocket connections
ss -tulpn | grep 57575

# Check backend logs for client connections
tail -f /var/log/supervisor/agentserver.log | grep "Client connected"
```

## Conclusion

Sessions are not shared across browser windows because:
1. Each window gets a unique Socket.IO connection ID (`sid`)
2. Backend uses `sid` as the client identifier
3. No mechanism exists to associate multiple `sid`s with the same workspace/user

The frontend correctly shares workspace data via localStorage, but the backend treats each window as a separate client, preventing true session sharing.