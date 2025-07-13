# 🏗️ AetherTerm Component Architecture

## Overview

This document provides detailed architecture documentation for AetherTerm's modular component system, focusing on the interaction patterns, data flow, and integration points between components.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Frontend Component Architecture](#frontend-component-architecture)
3. [Backend Component Architecture](#backend-component-architecture)
4. [Communication Patterns](#communication-patterns)
5. [State Management](#state-management)
6. [Integration Points](#integration-points)

---

## System Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    AetherTerm System                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │   Frontend      │────▶│   AgentServer   │               │
│  │   (Vue.js)      │     │   (FastAPI)     │               │
│  │                 │◀────│                 │               │
│  └─────────────────┘     └─────────────────┘               │
│           │                        │                       │
│           │                        │                       │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │  State Stores   │     │   AgentShell    │               │
│  │   (Pinia)       │     │   (AI Monitor)  │               │
│  └─────────────────┘     └─────────────────┘               │
│           │                        │                       │
│           │                        │                       │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │    Services     │     │  ControlServer  │               │
│  │  (Socket.IO)    │     │   (Central)     │               │
│  └─────────────────┘     └─────────────────┘               │
│                                    │                       │
│                           ┌─────────────────┐               │
│                           │   LangChain     │               │
│                           │   (AI Memory)   │               │
│                           └─────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Primary Responsibility | Key Functions |
|-----------|------------------------|---------------|
| **Frontend** | User interface and interaction | Terminal display, tab management, inventory search |
| **AgentServer** | Terminal server and API | PTY management, WebSocket handling, static serving |
| **AgentShell** | AI-enhanced terminal wrapper | Command monitoring, threat detection, AI analysis |
| **ControlServer** | Central coordination | Multi-instance management, system monitoring |
| **LangChain** | AI memory and retrieval | Conversation tracking, log analysis, knowledge base |

---

## Frontend Component Architecture

### Component Hierarchy

```
App.vue
├── TerminalTabBar.vue
│   ├── AddTabMenu.vue
│   └── TabContent.vue
├── TerminalComponent.vue
│   ├── TerminalContainer.vue
│   ├── TerminalView.vue
│   └── TerminalStatus.vue
├── InventorySearchPanel.vue
│   ├── SearchInput.vue
│   ├── SearchResults.vue
│   └── ServerInventoryContainer.vue
├── TerminalLogMonitorPanel.vue
├── ChatComponent.vue
├── SimpleChatComponent.vue
└── SupervisorControlPanel.vue
```

### Key Frontend Components

#### 1. App.vue
**Purpose**: Root application component
**Responsibilities**:
- Route management
- Global state initialization
- Layout structure
- Theme management

```vue
<template>
  <div id="app" :class="themeClass">
    <router-view />
  </div>
</template>
```

#### 2. TerminalTabBar.vue
**Purpose**: Tab management interface
**Responsibilities**:
- Tab creation, deletion, switching
- Tab status indication
- Context menu handling
- Responsive tab layout

**Key Features**:
- Multiple tab types (terminal, AI chat, log monitor)
- Tab subtypes (pure terminal, inventory terminal)
- Status indicators (active, connecting, error)
- Close button with confirmation

#### 3. TerminalView.vue
**Purpose**: Core terminal interface
**Responsibilities**:
- xterm.js integration
- Terminal I/O handling
- Screen buffer management
- Keyboard shortcut handling

**Recent Enhancements**:
- Enhanced xterm.js configuration (scrollback: 10000)
- New addons: Search, Clipboard, Serialize
- Improved font stack and rendering
- Better alternate screen buffer support

```typescript
// Enhanced terminal configuration
terminal.value = new Terminal({
  scrollback: 10000,
  fontFamily: 'Monaco, Menlo, "SF Mono", "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace',
  fontSize: 14,
  cursorStyle: 'block',
  // ... enhanced options
})
```

#### 4. InventorySearchPanel.vue
**Purpose**: Resource discovery and management
**Responsibilities**:
- Multi-type inventory search
- Filter management
- Context actions
- Integration with terminal tabs

**Search Categories**:
- Services (nginx, postgres, docker)
- Files (configs, logs, scripts)
- Commands (system utilities)
- Servers (SSH targets)
- Containers (Docker/Podman)
- Databases (connection strings)

#### 5. TerminalLogMonitorPanel.vue
**Purpose**: Log monitoring and analysis
**Responsibilities**:
- Real-time log streaming
- Log filtering and search
- Pattern recognition
- Integration with AI analysis

### Component Communication Patterns

#### 1. Props and Events (Parent-Child)
```typescript
// Parent to Child: Props
<TerminalView 
  :sessionId="activeTab.sessionId"
  :status="activeTab.status"
  @terminal-ready="onTerminalReady"
/>

// Child to Parent: Events
this.$emit('terminal-ready', { sessionId, terminal })
```

#### 2. Store-Based Communication (Global State)
```typescript
// Component uses store
const tabStore = useTerminalTabStore()
const terminalStore = useAetherTerminalStore()

// Reactive updates
watch(() => tabStore.activeTabId, (newTabId) => {
  // React to tab changes
})
```

#### 3. Event Bus (Service Layer)
```typescript
// Service-based communication
const aetherService = new AetherTermService()
aetherService.on('terminal_output', handleTerminalOutput)
aetherService.emit('terminal_input', { data, sessionId })
```

---

## Backend Component Architecture

### AgentServer Architecture

#### Core Structure
```
src/aetherterm/agentserver/
├── main.py                  # CLI entry point
├── server.py               # ASGI application factory
├── routes.py               # HTTP endpoints
├── socket_handlers.py      # WebSocket events
├── terminals/              # Terminal management
│   ├── asyncio_terminal.py # Async PTY handling
│   ├── base_terminal.py    # Terminal interface
│   └── default_terminal.py # Default implementation
├── containers.py           # Dependency injection
├── utils/                  # Utility functions
└── static/                 # Frontend build output
```

#### Key Components

##### 1. ASGI Server (server.py)
**Purpose**: FastAPI + Socket.IO integration
**Responsibilities**:
- HTTP route handling
- WebSocket connection management
- Static file serving
- CORS and security headers

```python
def create_asgi_app() -> FastAPI:
    app = FastAPI(title="AetherTerm AgentServer")
    
    # Socket.IO integration
    socket_app = socketio.ASGIApp(sio, app)
    
    # Include routes
    app.include_router(api_router, prefix="/api")
    
    return socket_app
```

##### 2. Terminal Management (asyncio_terminal.py)
**Purpose**: PTY lifecycle management
**Responsibilities**:
- Process spawning and monitoring
- I/O stream handling
- Signal management
- Resource cleanup

```python
class AsyncioTerminal:
    async def create_terminal(self, cols: int, rows: int) -> dict:
        # Spawn PTY process
        # Set up async I/O handling
        # Return session info
        
    async def handle_input(self, data: str):
        # Process user input
        # Send to PTY
        
    async def handle_output(self):
        # Read PTY output
        # Emit to connected clients
```

##### 3. Socket Handlers (socket_handlers.py)
**Purpose**: Real-time communication
**Responsibilities**:
- Client connection management
- Event routing and processing
- Session state management
- Error handling

```python
@sio.event
async def connect(sid, environ, auth):
    # Handle client connection
    # Initialize session
    
@sio.event  
async def terminal_input(sid, data):
    # Route input to appropriate terminal
    # Handle command processing
    
@sio.event
async def create_terminal(sid, data):
    # Create new terminal session
    # Notify clients of new session
```

### AgentShell Architecture

#### Core Structure
```
src/aetherterm/agentshell/
├── main.py                     # Entry point
├── controller/
│   └── terminal_controller.py  # Main control logic
├── pty_monitor/               # Real-time monitoring
│   ├── ai_analyzer.py         # AI threat detection
│   ├── input_blocker.py       # Command blocking
│   └── pty_controller.py      # PTY integration
├── service/                   # Service layer
│   ├── ai_service.py          # AI integration
│   ├── shell_agent.py         # Shell automation
│   └── server_connector.py    # AgentServer communication
└── agents/                    # AI agent implementations
    ├── command_analyzer.py    # Command analysis
    ├── langchain_agent.py     # LangChain integration
    └── manager.py             # Agent coordination
```

#### Key Components

##### 1. Terminal Controller (terminal_controller.py)
**Purpose**: Central coordination of terminal operations
**Responsibilities**:
- PTY lifecycle management
- AI agent coordination
- Command interception and analysis
- Integration with AgentServer

##### 2. AI Analyzer (ai_analyzer.py)
**Purpose**: Real-time command analysis
**Responsibilities**:
- Command threat assessment
- Pattern recognition
- Risk scoring
- Action recommendations

```python
class AIAnalyzer:
    async def analyze_command(self, command: str) -> AnalysisResult:
        # Analyze command for threats
        # Compute risk score
        # Return recommendations
        
    async def should_block_command(self, command: str) -> bool:
        # Determine if command should be blocked
        # Based on risk assessment
```

##### 3. Input Blocker (input_blocker.py)
**Purpose**: Command execution control
**Responsibilities**:
- Command filtering
- User confirmation prompts
- Execution prevention
- Audit logging

### LangChain Integration Architecture

#### Memory System Structure
```
src/aetherterm/langchain/
├── memory/
│   ├── conversation_memory.py  # Chat history
│   ├── session_memory.py      # Session persistence
│   └── hierarchical_memory.py # Multi-level memory
├── storage/
│   ├── redis_adapter.py       # Redis backend
│   ├── sql_adapter.py         # SQL backend
│   └── vector_adapter.py      # Vector database
└── config/
    ├── memory_config.py       # Memory settings
    └── storage_config.py      # Storage configuration
```

#### Key Components

##### 1. Hierarchical Memory (hierarchical_memory.py)
**Purpose**: Multi-level memory management
**Responsibilities**:
- Short-term: Recent commands and outputs
- Medium-term: Session summaries and patterns
- Long-term: User preferences and system knowledge

##### 2. Vector Adapter (vector_adapter.py)
**Purpose**: Semantic search and retrieval
**Responsibilities**:
- Embedding generation
- Similarity search
- Knowledge retrieval
- Context augmentation

---

## Communication Patterns

### 1. WebSocket Communication Flow

```
Client (Browser) ←→ AgentServer ←→ AgentShell ←→ Shell/PTY
        │                │              │
        │                │              └─ AI Analysis
        │                │
        │                └─ Log Processing ←→ LangChain
        │
        └─ UI Updates (Vue Components)
```

#### Event Flow Examples

1. **Terminal Input**:
   ```
   User Types → Frontend → WebSocket → AgentServer → AgentShell → PTY
   ```

2. **AI Analysis**:
   ```
   Command → AgentShell → AI Analyzer → Risk Assessment → Block/Allow
   ```

3. **Output Display**:
   ```
   PTY Output → AgentShell → AgentServer → WebSocket → Frontend → Terminal
   ```

### 2. State Synchronization

#### Store Updates Flow
```typescript
// Action triggers store update
tabStore.createTab('terminal')

// Store notifies components via reactivity
watch(() => tabStore.activeTabs, (newTabs) => {
  // Component reacts to change
})

// Service layer syncs with backend
aetherService.createTerminal(tabId)
```

#### Backend State Management
```python
# Session state in AgentServer
class SessionManager:
    async def create_session(self) -> Session:
        # Create session
        # Store in registry
        # Notify clients
        
    async def update_session_status(self, session_id: str, status: str):
        # Update internal state
        # Broadcast to clients
```

---

## State Management

### Frontend State Architecture

#### Store Responsibilities

1. **terminalTabStore.ts**:
   - Tab lifecycle (create, close, switch)
   - Tab metadata (title, status, type)
   - Server context management
   - Pre-execution commands

2. **aetherTerminalStore.ts** (unified store):
   - Connection status
   - Session management  
   - WebSocket state
   - Service configuration
   - Terminal I/O handling
   - AI events processing

3. **chatStore.ts**:
   - AI conversation history
   - Chat session management
   - Context tracking

4. **terminalBlockStore.ts**:
   - Command blocking state
   - Block notifications
   - User confirmations

#### State Flow Patterns

```typescript
// Action → Mutation → State → Computed → Component
tabStore.createTab() → tabs.push() → activeTabs → Component Update
```

### Backend State Management

#### Session State
- **In-Memory**: Active sessions, connection status
- **Persistent**: User preferences, session history
- **Distributed**: Multi-instance coordination (via ControlServer)

#### Configuration State
- **Static**: Configuration files, environment variables
- **Dynamic**: Runtime settings, feature flags
- **User-Specific**: Personal preferences, customizations

---

## Integration Points

### 1. Frontend ↔ Backend Integration

#### WebSocket Integration
```typescript
// Frontend service
class AetherTermService {
  private socket: Socket
  
  constructor() {
    this.socket = io('/terminal')
    this.setupEventHandlers()
  }
  
  createTerminal(cols: number, rows: number) {
    return this.socket.emit('create_terminal', { cols, rows })
  }
}
```

```python
# Backend handler
@sio.event
async def create_terminal(sid, data):
    terminal = await terminal_manager.create_terminal(
        cols=data['cols'], 
        rows=data['rows']
    )
    await sio.emit('terminal_created', terminal.to_dict(), room=sid)
```

#### REST API Integration
```typescript
// Frontend API calls
const response = await fetch('/api/terminals', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ cols: 80, rows: 24 })
})
```

### 2. AgentServer ↔ AgentShell Integration

#### Command Flow
```python
# AgentServer forwards command to AgentShell
async def handle_terminal_input(sid, data):
    if agent_shell_connected:
        result = await agent_shell.analyze_command(data['command'])
        if result.should_block:
            await sio.emit('command_blocked', result.to_dict(), room=sid)
            return
    
    # Proceed with normal command execution
    await terminal.send_input(data['command'])
```

### 3. Component ↔ Store Integration

#### Reactive Patterns
```typescript
// Component reactively updates based on store changes
const { activeTab, activeTabs } = storeToRefs(tabStore)

// Watch for specific changes
watch(activeTab, (newTab) => {
  if (newTab?.type === 'terminal') {
    // Initialize terminal
  }
})
```

### 4. AI System Integration

#### LangChain Memory Integration
```python
# AgentShell integrates with LangChain memory
class ShellAgent:
    def __init__(self, memory_system: HierarchicalMemory):
        self.memory = memory_system
        
    async def analyze_command(self, command: str):
        # Retrieve relevant context from memory
        context = await self.memory.retrieve_context(command)
        
        # Analyze with context
        analysis = await self.ai_analyzer.analyze(command, context)
        
        # Store result in memory
        await self.memory.store_analysis(command, analysis)
        
        return analysis
```

---

## Component Lifecycle

### Frontend Component Lifecycle

```typescript
// Component lifecycle in TerminalView.vue
export default defineComponent({
  setup() {
    onMounted(() => {
      // Initialize terminal
      // Connect to service
      // Setup event listeners
    })
    
    onBeforeUnmount(() => {
      // Cleanup terminal
      // Disconnect service
      // Remove listeners
    })
    
    return {
      // Reactive properties
      // Methods
    }
  }
})
```

### Backend Component Lifecycle

```python
# AgentServer lifecycle
class AgentServer:
    async def startup(self):
        # Initialize services
        # Setup routes
        # Start terminal manager
        
    async def shutdown(self):
        # Cleanup terminals
        # Close connections
        # Save state
```

### Session Lifecycle

1. **Creation**: User requests new terminal/session
2. **Initialization**: Backend creates PTY, frontend creates tab
3. **Active**: User interaction, command execution, AI monitoring
4. **Cleanup**: Session close, resource cleanup, state persistence

---

## Performance Considerations

### Frontend Performance
- **Virtual Scrolling**: For large terminal outputs
- **Debounced Search**: For inventory search
- **Lazy Loading**: For tab content
- **Memory Management**: Proper cleanup of terminals and listeners

### Backend Performance
- **Async Operations**: Non-blocking I/O throughout
- **Connection Pooling**: Efficient resource utilization
- **Caching**: Session state, AI analysis results
- **Resource Limits**: PTY limits, memory constraints

### Communication Efficiency
- **Event Batching**: Reduce WebSocket overhead
- **Delta Updates**: Send only changes
- **Compression**: For large outputs
- **Connection Management**: Proper cleanup and reconnection

---

## Security Architecture

### Component Security Responsibilities

1. **Frontend**: Input validation, XSS prevention, secure storage
2. **AgentServer**: Authentication, authorization, session security
3. **AgentShell**: Command validation, threat detection, audit logging
4. **ControlServer**: System security, compliance monitoring

### Security Integration Points
- **Authentication Flow**: Frontend → AgentServer → IdP
- **Command Validation**: AgentShell → AI Analysis → Block/Allow
- **Audit Trail**: All components → Central logging
- **Session Security**: Encrypted communication, session isolation

---

## Conclusion

The AetherTerm component architecture provides a robust, scalable foundation for AI-enhanced terminal operations. The modular design enables independent development and deployment while maintaining strong integration points for seamless user experience.

Key architectural strengths:
- **Separation of Concerns**: Clear component responsibilities
- **Reactive Architecture**: Real-time updates throughout system
- **Security by Design**: Multiple layers of protection
- **Extensible**: Plugin architecture for new features
- **Scalable**: Distributed architecture ready for enterprise deployment