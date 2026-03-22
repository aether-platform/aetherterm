#!/usr/bin/env bash
set -e

echo "--- AetherTerm Dev Server ---"
echo "  User: $(whoami) (UID: $(id -u))"

# Use a container-local venv to avoid permission issues with host .venv
export UV_PROJECT_ENVIRONMENT="/home/aetherterm/.venv"

# Install dependencies on first run (or when pyproject.toml changes)
STAMP="/tmp/.aetherterm-deps-installed"
PYPROJECT_HASH=$(md5sum /app/pyproject.toml 2>/dev/null | cut -d' ' -f1)
PREV_HASH=$(cat "$STAMP" 2>/dev/null || echo "")

if [ "$PYPROJECT_HASH" != "$PREV_HASH" ]; then
    echo "  Installing dependencies..."
    cd /app && uv sync --quiet
    echo "$PYPROJECT_HASH" > "$STAMP"
    echo "  Dependencies installed."
else
    echo "  Dependencies up to date."
fi

# Use frontend/dist directly if available, otherwise fall back to web/static
if [ -d /app/frontend/dist ]; then
    export AETHERTERM_STATIC_DIR="/app/frontend/dist"
    echo "  Static: /app/frontend/dist (host-built)"
else
    echo "  Static: web/static (pre-deployed)"
fi

echo "  Starting: $*"
echo "---"

exec uv run "$@"
