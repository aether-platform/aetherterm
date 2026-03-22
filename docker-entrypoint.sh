#!/usr/bin/env bash
set -e

# ============================================================
# AetherTerm Docker Entrypoint
# ============================================================

# Validate required port is not already in use
AETHERTERM_PORT="${AETHERTERM_PORT:-57575}"

# Log startup configuration
echo "🚀 AetherTerm Starting..."
echo "----------------------------------------"
echo "  🌐 Port:  ${AETHERTERM_PORT}"
echo "  🤖 NATS:  ${NATS_URL:-nats://localhost:4222}"
echo "  🐛 Debug: ${AETHERTERM_DEBUG:-false}"
echo "  👤 User:  $(whoami) (UID: $(id -u))"
echo "----------------------------------------"

# Default to jupyter-server if no command provided
if [ $# -eq 0 ]; then
    echo "📓 Starting Jupyter Server (Proxying AetherTerm)..."
    exec jupyter-server --ip=0.0.0.0 --port=8888 --no-browser --allow-root --ServerApp.token='' --ServerApp.password=''
fi

# Check if the first argument is an option (e.g., -f or --host)
if [ "${1#-}" != "$1" ]; then
    set -- aetherterm-agentserver "$@"
fi

# Execute the command
exec "$@"
