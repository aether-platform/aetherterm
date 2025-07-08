# Socket.IO Events Cleanup Plan

## Current Event Structure Analysis

### Terminal Management Events

#### Keep (Core functionality)
- `connect` / `disconnect` - Connection lifecycle
- `create_terminal` - Create new terminal session
- `terminal_input` - Send input to terminal
- `terminal_output` - Receive output from terminal
- `terminal_resize` - Handle terminal resize
- `terminal_error` - Terminal error notifications
- `terminal_ready` - Terminal initialization complete

#### Remove/Refactor
- `shell_output` → Use `terminal_output` instead
- `ctl_output` → Use `terminal_output` with type field
- `resume_terminal` → Use `reconnect_session`
- `terminal_closed` → Use `terminal_error` with closed status

### Workspace Management Events

#### Current Issues
- Frontend uses localStorage as primary storage
- Server sync is treated as optional/secondary
- Multiple similar events for save/load/resume

#### Proposed Server-Only Architecture
```
Client → Server Events:
- `workspace_create` - Create new workspace
- `workspace_get` - Get workspace by ID
- `workspace_list` - List all workspaces
- `workspace_update` - Update workspace (tabs, panes)
- `workspace_delete` - Delete workspace

Server → Client Events:
- `workspace_data` - Workspace data response
- `workspace_list_data` - List of workspaces
- `workspace_error` - Error response
```

### Session Management Events

#### Simplify to:
- `session_create` - Create new session
- `session_reconnect` - Reconnect to existing session
- `session_close` - Close session
- `session_data` - Session data/state

Remove:
- `reconnect_session` → Use `session_reconnect`
- `get_session_info` → Use `session_data`
- `session_not_found` → Use error response

### AI Integration Events

#### Keep as-is (well structured):
- `ai_chat_message` / `ai_chat_chunk` / `ai_chat_complete`
- `ai_get_info` / `ai_info_response`
- `ai_chat_error`

### Log Monitoring Events

#### Keep core events:
- `log_monitor_subscribe` / `log_monitor_unsubscribe`
- `log_monitor_data` (rename from various stat events)
- `log_search` / `log_search_results`

Remove redundant:
- `log_monitor_stats` → Use `log_monitor_data`
- `log_system_stats` → Use `log_monitor_data`
- `log_terminal_stats` → Use `log_monitor_data`

### Agent/Wrapper Events

#### Review necessity:
- Many agent-related events seem unused
- Wrapper session sync may be obsolete

## Implementation Steps

### Phase 1: Remove localStorage dependency
1. Remove `WorkspacePersistenceManager`
2. Remove localStorage reads/writes from `workspaceStore`
3. Make all workspace operations server-side only

### Phase 2: Consolidate terminal events
1. Merge output events into single `terminal_output`
2. Standardize error handling with `terminal_error`
3. Remove duplicate session management events

### Phase 3: Simplify workspace events
1. Implement server-only workspace management
2. Remove background sync logic
3. Clean up cross-tab sync (not needed with server state)

### Phase 4: Clean up unused events
1. Remove agent/wrapper events if unused
2. Consolidate log monitoring events
3. Remove debug/test events

## Benefits

1. **Simpler architecture** - Single source of truth (server)
2. **Fewer events** - Easier to maintain and debug
3. **Better performance** - No localStorage/server sync overhead
4. **Clearer semantics** - Each event has single purpose
5. **Proper session management** - Server maintains all state

## Migration Notes

- Ensure backward compatibility during transition
- Update both frontend and backend simultaneously
- Test thoroughly with multiple tabs/windows
- Document new event structure clearly