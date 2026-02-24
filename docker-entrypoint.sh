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
echo "  🤖 ZMQ:   ${AETHERTERM_ZMQ_ENABLED:-false}"
echo "  🐛 Debug: ${AETHERTERM_DEBUG:-false}"
echo "  👤 User:  $(whoami) (UID: $(id -u))"
echo "----------------------------------------"

# Check if the first argument is an option (e.g., -f or --host)
if [ "${1#-}" != "$1" ]; then
    set -- aetherterm-agentserver "$@"
fi

# Execute the command
exec "$@"
