# Terminal Restoration Implementation Plan

## Overview
This document outlines the requirements and implementation plan for three critical terminal features:
1. AI Cost tab functionality restoration
2. Tab restoration and screen buffer recreation
3. AI chat activation

## 1. AI Cost Tab Restoration

### Current Status
- ✅ Frontend component exists: `frontend/src/components/AICostSidebar.vue`
- ✅ API endpoints defined: `/api/ai/costs`, `/api/ai/costs/daily`, `/api/ai/costs/models`
- ✅ Backend handlers implemented in `ai_service.py`
- ❌ Data not displaying correctly in UI

### Root Cause Analysis
The AI Cost tab is making requests to the API endpoints, but the responses may not match the expected format or the AI service might not be properly initialized.

### Implementation Tasks

#### Task 1.1: Verify AI Service Initialization
- **File**: `src/aetherterm/agentserver/infrastructure/config/di_container.py`
- **Action**: Ensure AI service is properly initialized with correct provider settings
- **Priority**: High

#### Task 1.2: Fix Data Format Mismatch
- **Files**: 
  - `src/aetherterm/agentserver/infrastructure/external/ai_service.py`
  - `frontend/src/components/AICostSidebar.vue`
- **Action**: Ensure backend response format matches frontend expectations
- **Expected Format**:
  ```json
  {
    "available": true,
    "total_cost": 0.0,
    "requests": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "average_cost_per_request": 0.0,
    "cost_per_1k_tokens": 0.0
  }
  ```

#### Task 1.3: Add Error Handling
- **File**: `frontend/src/components/AICostSidebar.vue`
- **Action**: Improve error display and retry mechanisms
- **Priority**: Medium

## 2. Tab Restoration & Screen Buffer Recreation

### Current Status
- ❌ Tabs not persisting across page reloads
- ❌ Terminal output lost on refresh
- ❌ No session state persistence

### Requirements
1. Persist active tabs in browser storage
2. Restore terminal sessions on reconnect
3. Maintain screen buffer history

### Implementation Tasks

#### Task 2.1: Implement Tab State Persistence
- **Files**: 
  - `frontend/src/stores/terminalTabStore.ts`
  - `frontend/src/stores/screenBufferStore.ts`
- **Action**: 
  - Save tab state to localStorage on changes
  - Restore tabs on component mount
  - Include tab type, title, and session ID

#### Task 2.2: Server-Side Session Management
- **Files**:
  - `src/aetherterm/agentserver/domain/entities/terminals/asyncio_terminal.py`
  - `src/aetherterm/agentserver/endpoint/handlers/terminal_handlers.py`
- **Action**:
  - Implement session persistence with unique IDs
  - Store terminal output buffer (last N lines)
  - Add session reconnection logic

#### Task 2.3: WebSocket Reconnection Flow
- **File**: `frontend/src/stores/aetherTerminalStore.ts`
- **Action**:
  - Implement reconnection with session restoration
  - Request buffer replay on reconnect
  - Handle graceful degradation

### Data Flow
```
1. User opens terminal → Create session with ID
2. Terminal output → Store in server buffer
3. Page refresh → Restore tabs from localStorage
4. WebSocket reconnect → Request session restoration
5. Server → Send buffered output to client
```

## 3. AI Chat Activation

### Current Status
- ✅ Backend WebSocket handlers exist: `ai_handlers.py`
- ✅ AI service integration available
- ❌ Frontend not properly connected to WebSocket events

### Requirements
1. Enable AI chat tab functionality
2. Implement streaming responses
3. Maintain chat history

### Implementation Tasks

#### Task 3.1: Fix WebSocket Event Registration
- **Files**:
  - `src/aetherterm/agentserver/endpoint/websocket/socket_handlers.py`
  - `frontend/src/components/terminal/AIAgentTab.vue`
- **Action**:
  - Register AI WebSocket handlers: `ai_chat_message`, `ai_get_info`
  - Implement proper event listeners in frontend
  - Handle streaming responses

#### Task 3.2: Implement Chat UI
- **File**: `frontend/src/components/terminal/AIAgentTab.vue`
- **Features**:
  - Message input/output display
  - Streaming response rendering
  - Chat history management
  - Error state handling

#### Task 3.3: Connect to AI Service
- **File**: `src/aetherterm/agentserver/infrastructure/external/ai_service.py`
- **Action**:
  - Verify LMStudio connection
  - Implement proper streaming
  - Add timeout handling

### WebSocket Events
```typescript
// Frontend → Backend
socket.emit('ai_chat_message', {
  message: string,
  session_id: string,
  stream: boolean
})

// Backend → Frontend
socket.on('ai_chat_response', {
  response: string,
  session_id: string,
  timestamp: string
})

socket.on('ai_chat_chunk', {
  chunk: string,
  session_id: string,
  timestamp: string
})
```

## Testing Plan

### AI Cost Tab
1. Start server with AI service enabled
2. Make some AI requests to generate usage data
3. Open AI Cost tab and verify data display
4. Test period selection and refresh

### Tab Restoration
1. Open multiple terminal tabs
2. Execute commands in each
3. Refresh page
4. Verify tabs are restored with correct content

### AI Chat
1. Open AI chat tab
2. Send test message
3. Verify response streaming
4. Test error scenarios

## Priority Order
1. **High**: AI Cost tab data display (Quick win)
2. **High**: Tab state persistence (User experience)
3. **Medium**: Screen buffer restoration (Data integrity)
4. **Medium**: AI chat activation (Feature completion)

## Success Criteria
- [ ] AI Cost tab displays real usage data
- [ ] Tabs persist across page refreshes
- [ ] Terminal output is restored on reconnect
- [ ] AI chat responds to messages with streaming
- [ ] All features handle errors gracefully