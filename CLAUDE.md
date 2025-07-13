# AetherTerm - AI Terminal Platform

**Components**: AgentServer (web terminal + MainAgent control), ControlServer (central mgmt)  
**Tech**: Python FastAPI + SocketIO, Vue 3 + TypeScript frontend, LangChain AI integration  
**Features**: MainAgent-controlled agent startup, hierarchical memory, multi-agent coordination, comprehensive security

## Repository Management

**Multi-Repository Setup**: This project is part of the AetherPlatform workspace managed by [tsrc](https://github.com/tanker-io/tsrc).

### Key tsrc Commands
```bash
# From workspace root - sync all repositories
tsrc sync

# Check status across all repositories  
tsrc status

# Update only this repository
git pull origin main
```

**Location**: `app/terminal/` within the unified AetherPlatform workspace  
**Repository**: Independent Git repository as part of tsrc-managed multi-repo setup

## Platform Integration

### Architecture Assumptions
- **JupyterHub Container**: Runs as a service within JupyterHub user containers
- **Proxy Authentication**: User identity provided via proxy headers from JupyterHub
- **Shared Workspace**: Global collaborative workspace with role-based access control
- **AI Integration**: Native LangChain integration for intelligent terminal assistance
- **Session Persistence**: Persistent sessions across container restarts via external storage

### Service Dependencies
- **Upstream**: JupyterHub proxy for authentication and container lifecycle
- **Database**: PostgreSQL for session metadata, Redis for real-time state
- **External**: AI providers (Anthropic, LMStudio), tenant-specific Qdrant instances
- **Storage**: Persistent volumes for session history and workspace data

### Tenant Vector Database Integration
- **Dynamic Qdrant Connection**: Connects to tenant-specific Qdrant instance based on user context
- **Tenant Context Injection**: Automatically configures MCP server with tenant vector database
- **Vector Search Isolation**: All semantic searches scoped to tenant-specific collections
- **Session-Scoped Configuration**: Vector database context maintained per terminal session

## Vector-Enhanced Development Strategy

**CRITICAL**: Use semantic search FIRST for all conceptual development tasks. Traditional tools are secondary.

### Mandatory Vector-First Workflow
```bash
# For conceptual understanding (PRIMARY)
mcp__code-search__qdrant-find → semantic discovery
↓
Read/Glob/Grep → detailed verification

# For specific known files (SECONDARY)  
Read/Glob/Grep → direct access
```

### **Vector Database Registration Requirements**
**ALL Qdrant uploads for this project MUST use this exact metadata structure**:

```javascript
// ✅ TERMINAL PROJECT - Required Metadata Format
{
  "information": "Human-readable description of the file/content",
  "metadata": {
    "file_path": "/full/path/from/project/root/file.ext",
    "content_type": "typescript|javascript|python|vue|markdown|json|configuration",
    "category": "backend|frontend|config|docs|tests",
    "last_modified": "2025-07-13T10:30:00Z",
    "project_context": "AetherTerm terminal application",
    "code": "actual file content here",
    
    // TERMINAL PROJECT METADATA (REQUIRED)
    "project_name": "terminal",
    "project_type": "coding",
    "repository_path": "app/terminal/",
    "tech_stack": ["python", "fastapi", "socketio", "vue3", "typescript", "langchain"],
    "tenant_scope": "multi-tenant"
  }
}
```

**Terminal-Specific Tech Stack**:
- **Backend**: `["python", "fastapi", "socketio", "uvicorn", "asyncio", "langchain"]`
- **Frontend**: `["vue3", "typescript", "vuetify", "vite", "pinia", "xterm"]`
- **AI**: `["langchain", "anthropic", "qdrant", "mcp"]`
- **Infrastructure**: `["supervisord", "postgresql", "redis"]`

**Content Type Mapping for Terminal**:
- **Python files**: `python` - FastAPI, agents, terminal logic
- **Vue files**: `vue` - Terminal UI components
- **TypeScript**: `typescript` - Frontend logic, stores, composables
- **Configuration**: `configuration` - supervisord.conf, pyproject.toml
- **Documentation**: `markdown` - README, docs, architecture

### Semantic Search Patterns
Before using traditional file tools, query Qdrant for these contexts:

**Architecture & Design**: "system architecture components modules structure dependency injection"
**Database Operations**: "database models entities repositories ORM SQLAlchemy PostgreSQL"
**API Development**: "REST API endpoints routes handlers FastAPI WebSocket real-time"
**Frontend**: "Vue components templates reactive state management Vuetify terminal UI"
**Authentication**: "authentication authorization JWT tokens security RBAC PAM X.509"
**AI Integration**: "AI agents LangChain hierarchical coordination MainAgent SubAgents"
**Testing**: "unit tests integration tests pytest fixtures async testing coverage"
**Configuration**: "configuration settings environment variables supervisord process"
**Error Handling**: "exception handling error processing logging OpenTelemetry monitoring"
**Real-time**: "WebSocket Socket.IO real-time bidirectional terminal communication"

## Quick Start

```bash
# Backend setup
uv sync && make build-frontend
make run  # Starts development server with supervisord

# Frontend development  
cd frontend && pnpm install && pnpm dev
```

## Key Files

**Entry Points**: `src/aetherterm/{agentserver,controlserver}/main.py`  
**Frontend**: `frontend/src/main.ts`, `components/TerminalComponent.vue`  
**Config**: `pyproject.toml`, `frontend/package.json`

## Architecture

**Flow**: ControlServer (8765) ← AgentServer (57575) → MainAgent → SubAgents  
**Features**: MainAgent startup control, specification input, hierarchical memory, ControlServer log summarization

## Context-Aware Development Patterns

### Intelligent Feature Development
```bash
# Example: Adding real-time notifications
1. Query: "real-time notifications WebSocket events user interface terminal"
2. Discover: existing notification patterns, UI components, event handling
3. Query: "Vue component reactive state management terminal feedback"
4. Follow established patterns for consistent implementation
```

### Smart Bug Investigation
```bash
# Example: Connection stability issues
1. Query: "WebSocket connection stability timeout retry logic error handling"
2. Discover: connection management, retry mechanisms, error patterns
3. Query: "terminal session persistence state recovery async"
4. Analyze specific implementations with full context
```

### Architecture-First Approach
```bash
# Before major changes:
1. Query: "system architecture component relationships integration points"
2. Understand impact areas and dependencies
3. Query: "similar implementations patterns conventions"
4. Follow established architectural patterns
```

## Development Notes

**Build Process**: Frontend builds to `dist/` → copied to AgentServer `static/` → served by FastAPI  
**Communication**: WebSocket (Socket.IO) for real-time terminal I/O  
**Security**: SSL/TLS, X.509 certs, PAM integration, RBAC
**Vector Strategy**: Always start with semantic discovery for conceptual understanding

## Common Tasks

**Frontend changes**: Edit `frontend/src/` → `make build-frontend` → test  
**Add dependencies**: Python (`pyproject.toml` + `uv sync`), Node (`package.json` + `pnpm install`)  
**Testing**: `pytest` (Python), `pnpm type-check` (frontend)

## Development Server Commands

```bash
make run      # Start development server with supervisord
make stop     # Stop server
make restart  # Restart server  
make status   # Check server status
make logs     # View server logs
```

## Troubleshooting

**Process monitoring**: `make status` or `ps aux | grep agentserver`  
**Port status**: `ss -tulpn | grep 57575` or `lsof -i :57575`  
**Health check**: `curl http://localhost:57575/health`  
**Dependencies**: Missing modules → `uv add <module>` → `uv sync`

## Supervisord Process Management

**IMPORTANT**: This project EXCLUSIVELY uses supervisord for process management and logging.

**Design Decision**: 
- Supervisord handles all process lifecycle management
- Reduces token usage by eliminating manual process management
- Prevents coding agents from spending time on infrastructure tasks
- Enables focus on actual application development

**Configuration**: `./supervisord.conf` (local file)  
**Logs**: `./run/agentserver.log` (local directory)  
**PID files**: `./run/` (local directory)

**Usage**:
```bash
make run      # Start once - runs continuously
make restart  # Only when needed
make status   # Check process health
make logs     # View aggregated logs
```

**DO NOT**:
- Manually start/stop Python processes
- Use `python -m uvicorn` directly
- Manage process states manually
- Implement custom process management

The `make run` command handles all supervisord startup and management automatically.

## Code Standards & Best Practices

### Terminal Implementation
**PTY Handling**: Terminal functionality is provided by PTY (pseudo-terminal) and the user's shell  
**Feature Boundary**: Don't reimplement shell features (history, tab completion, etc.) - let the shell handle them  
**Input/Output**: Simply pass keystrokes to PTY and display output - avoid complex input processing

### Frontend Development
**Performance**: Remove unused dependencies, use lazy loading for heavy components  
**Type Safety**: No 'any' types - define proper TypeScript interfaces for all data structures  
**State Management**: Use Pinia stores with clear separation of concerns  
**Error UX**: Show loading states and user-friendly error messages

### Backend Development
**Async Safety**: Always handle asyncio.create_task with error callbacks  
**Race Conditions**: Properly cancel existing tasks before creating new ones  
**Memory Management**: Clean up resources (timeouts, event listeners) on component unmount  
**WebSocket**: Use Socket.IO for real-time communication with proper event handling

### Security
**Input Validation**: Validate all user input on both frontend and backend  
**Role Checking**: Enforce RBAC (Viewer vs User roles) consistently  
**Session Management**: Proper session lifecycle with cleanup on disconnect
