# AetherTerm Architecture Documentation

## Overview

AetherTerm is an AI-enhanced terminal platform built with Clean Architecture principles, featuring real-time WebSocket communication, hierarchical AI agents, and comprehensive security.

## Architecture Layers

```
interfaces/        # Presentation Layer - HTTP/WebSocket handlers
application/       # Business Logic - Services and use cases  
domain/           # Core Entities - Terminal business logic
infrastructure/   # External Dependencies - AI, Security, Storage
```

## Technology Stack

### Backend
- **Framework**: Python FastAPI + Socket.IO
- **AI Integration**: LangChain with hierarchical agent system
- **Architecture**: Clean Architecture with DI (91% complete)
- **Security**: SSL/TLS, X.509 certs, PAM integration, RBAC

### Frontend
- **Framework**: Vue 3 + TypeScript + Vuetify
- **State Management**: Pinia stores
- **Communication**: Socket.IO client for real-time updates
- **Build Tool**: Vite with pnpm

## Core Components

### 1. AgentServer (Port 57575)
- Web terminal interface
- MainAgent control system
- Real-time WebSocket communication
- Static file serving for frontend

### 2. ControlServer (Port 8765)
- Central management hub
- Log summarization
- Multi-agent coordination
- System monitoring

### 3. Agent Hierarchy
```
MainAgent (Orchestrator)
├── SubAgents (Task-specific)
├── Memory System (Hierarchical)
└── Tool Integration (LangChain)
```

## UI Architecture

### Layout Structure
- **Tab Bar**: Terminal-focused functionality only
  - Terminal tabs (dynamic)
  - AI Agent tabs (dynamic)
  - Tab Creation Menu
  - Log Monitor (fixed)

- **Side Panel**: All non-terminal application features
  - Assistant (AI chat)
  - Inventory (server management)
  - Admin (system administration)
  - Theme (appearance settings)
  - S3 Browser (file management)
  - AI Costs (cost monitoring)

- **Sidebar**: Quick access shortcuts when Side Panel is collapsed

### Design Principles
1. **No Function Duplication**: Each feature has exactly ONE primary access point
2. **Clear Separation**: Terminal functions in Tab Bar, application features in Side Panel
3. **Consistent Access**: Predictable navigation patterns

## Key Features

### Terminal Capabilities
- xterm compatibility
- 16,777,216 color support
- Native browser scroll and search
- HTML rendering support
- Multiple session support (screen -x style)
- Keyboard text selection
- Desktop notifications

### AI Integration
- MainAgent-controlled agent startup
- Hierarchical memory system
- Multi-agent coordination
- Specification-based task execution
- Real-time AI response streaming

### Security
- X.509 certificate authentication
- PAM integration for system auth
- Role-based access control (RBAC)
- SSL/TLS encryption
- Secure WebSocket connections

## Development Workflow

### Quick Start
```bash
# Backend setup
uv sync && make build-frontend
make run-agentserver ARGS="--host=localhost --port=57575 --unsecure --debug"

# Frontend development  
cd frontend && pnpm install && pnpm dev
```

### Build Process
1. Frontend builds to `dist/` directory
2. Build artifacts copied to AgentServer `static/`
3. FastAPI serves static files and API endpoints

### Common Commands
- **Run tests**: `pytest` (Python), `pnpm type-check` (frontend)
- **Add Python deps**: `uv add <package>` then `uv sync`
- **Add Node deps**: `pnpm add <package>`
- **Build frontend**: `make build-frontend`

## Monitoring & Observability

### OpenTelemetry Integration
- Distributed tracing across all components
- Custom metrics for terminal sessions and AI usage
- Structured logging with trace correlation
- Grafana Cloud APM support

### Key Metrics
- `aetherterm.terminal.sessions.active`
- `aetherterm.websocket.connections.active`
- `aetherterm.ai.requests.total`
- `aetherterm.ai.tokens.usage.total`

## Process Management

### Supervisord Configuration
```ini
[program:agentserver]
command=uv run aetherterm-agentserver --host=localhost --port=57575
directory=/mnt/c/workspace/vibecoding-platform/app/terminal
autostart=true
autorestart=true
```

### Management Commands
- Start: `supervisorctl start agentserver`
- Status: `supervisorctl status`
- Logs: `tail -f /var/log/supervisor/agentserver.log`

## Migration Status

**Clean Architecture**: 91% complete (51 files migrated, 5 legacy remaining)

### Benefits Achieved
- ✅ **Testability**: Each layer independently testable
- ✅ **Maintainability**: Clear code organization
- ✅ **Extensibility**: Easy feature additions
- ✅ **Flexibility**: DI with fallback compatibility

### Remaining Work
1. Complete DI integration in server.py
2. Integration testing for full architecture
3. Consolidate remaining legacy files

---
*Last updated: Clean Architecture migration 91% complete*