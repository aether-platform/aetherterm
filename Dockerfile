# Multi-stage build for optimized image size
# Supports both AMD64 and ARM64 architectures
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY README.md ./

# Copy source code first for dependency resolution
COPY src/ ./src/

# Install Python dependencies
RUN uv pip install --system --no-cache-dir -e .

# Build frontend stage
FROM node:24.4.0-alpine as frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    lsof \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash aetherterm

# Set working directory
WORKDIR /app

# Copy Python installation from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY pyproject.toml ./
COPY README.md ./

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./src/aetherterm/agentserver/static/
COPY --from=frontend-builder /app/frontend/dist/index.html ./src/aetherterm/agentserver/templates/

# Copy default configuration
COPY src/aetherterm/aetherterm.conf.default /etc/aetherterm/aetherterm.conf

# Create necessary directories
RUN mkdir -p /var/log/aetherterm /var/run/aetherterm \
    && chown -R aetherterm:aetherterm /var/log/aetherterm /var/run/aetherterm /app

# Switch to non-root user
USER aetherterm

# Expose ports
EXPOSE 57575 8765

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:57575/health || exit 1

# Default command - run AgentServer
CMD ["aetherterm-agentserver", "--host", "0.0.0.0", "--port", "57575"]

# Labels for metadata
LABEL org.opencontainers.image.title="AetherTerm"
LABEL org.opencontainers.image.description="AI-enhanced terminal emulator with web interface"
LABEL org.opencontainers.image.vendor="Project Aether"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/aether-platform/aetherterm"
