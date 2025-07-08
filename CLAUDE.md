# AetherTerm - AI Terminal Platform

**Components**: AgentServer (web terminal + MainAgent control), ControlServer (central mgmt)  
**Tech**: Python FastAPI + SocketIO, Vue 3 + TypeScript frontend, LangChain AI integration  
**Features**: MainAgent-controlled agent startup, hierarchical memory, multi-agent coordination, comprehensive security

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

## Development Notes

**Build Process**: Frontend builds to `dist/` → copied to AgentServer `static/` → served by FastAPI  
**Communication**: WebSocket (Socket.IO) for real-time terminal I/O  
**Security**: SSL/TLS, X.509 certs, PAM integration, RBAC

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
