# ⚡ AetherTerm

AI-enhanced terminal platform with real-time WebSocket communication and hierarchical agent system.

## Quick Start

```bash
# Install and run
pip install aetherterm
aetherterm --host=localhost --port=57575

# Development setup
uv sync && make build-frontend
make run  # Starts development server with supervisord
```

## Key Features

### Terminal
- Full xterm compatibility with 16M color support
- Native browser scroll and search
- HTML rendering in terminal
- Multiple session support (screen -x style)
- Desktop notifications

### AI Integration
- Hierarchical agent system with MainAgent orchestration
- LangChain integration for advanced AI capabilities
- Real-time response streaming
- Specification-based task execution

### Security
- X.509 certificate authentication
- PAM integration for system auth
- Role-based access control (RBAC)
- SSL/TLS encryption

## Documentation

- **[Architecture](./ARCHITECTURE.md)** - System design and components
- **[Claude Instructions](./CLAUDE.md)** - AI assistant configuration
- **[UI Design](./DESIGN.md)** - Interface principles and layout

## Recent Updates (2025-07-08)

### Bug Fixes
- Fixed memory leaks in terminal component by properly cleaning up timeouts on unmount
- Fixed race condition in terminal closure scheduling that could cause multiple closure tasks
- Added error handling for all asyncio.create_task calls to prevent unhandled exceptions
- Improved type safety by replacing generic 'any' types with proper TypeScript interfaces
- Added loading states with spinner for better UX during connection attempts

### Code Optimization
- Removed ~3.5MB of unused dependencies from frontend bundle
- Eliminated ~2,000 lines of dead code across the codebase
- Simplified store implementations for better performance
- Optimized terminal output buffering for smoother rendering

### Features Enhanced
- Enhanced terminal search with visual highlighting (Ctrl+Shift+F)
  - Added search bar UI with next/previous navigation
  - Visual highlighting of search matches
  - Keyboard shortcuts for search operations
- Improved error messages for permission-denied scenarios
- Better visual feedback during connection and loading states

## Installation Options

```bash
# Basic installation
pip install aetherterm

# With themes support
pip install aetherterm[themes]

# With systemd integration
pip install aetherterm[systemd]
```

## Server Deployment

### Standard Server
```bash
# Basic server
aetherterm --host=myhost --port=57575

# With login prompt
aetherterm --host=myhost --port=57575 --login

# With PAM authentication (requires root)
sudo aetherterm --host=myhost --port=57575 --login --pam_profile=sshd
```

### Docker
```bash
# With password
docker run --env PASSWORD=password -d aetherterm/aetherterm --login

# Without password
docker run -d -p 57575:57575 aetherterm/aetherterm

# Custom port
docker run -d -p 12345:12345 aetherterm/aetherterm --port=12345
```

### Supervisord (Development)
```bash
make run      # Start development server
make stop     # Stop server
make restart  # Restart server
make status   # Check status
make logs     # View logs
```

## Monitoring

Built-in OpenTelemetry integration with Grafana Cloud APM:

```bash
# Configure environment
cp .env.example .env
# Edit .env with Grafana Cloud credentials

# Required variables
GRAFANA_CLOUD_INSTANCE_ID="your-instance-id"
GRAFANA_CLOUD_API_KEY="your-api-key"
ENVIRONMENT="development"
```

### Available Metrics
- Terminal sessions and WebSocket connections
- AI agent requests and token usage
- System resource utilization
- Error tracking and alerts

## Development

### Frontend Development
```bash
cd frontend
pnpm install
pnpm dev          # Development server
pnpm build        # Production build
pnpm type-check   # TypeScript validation
```

### Backend Development
```bash
uv sync           # Install Python dependencies
pytest            # Run tests
uv add <package>  # Add new dependency
```

### Common Tasks
- **Build frontend**: `make build-frontend`
- **Server management**: `make run | stop | restart | status | logs`
- **Check ports**: `lsof -i :57575`
- **Health check**: `curl http://localhost:57575/health`

## Contributing

Fork the repository and submit pull requests. Check GitHub issues for tasks to work on.

## License

Apache License 2.0 - See LICENSE file for details

---
*Part of the AetherPlatform ecosystem*