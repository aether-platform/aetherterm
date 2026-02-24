# ============================================================
# Stage 1: Runtime Base (Mise & Dependencies)
# ============================================================
FROM ubuntu:22.04 AS base

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    MISE_DATA_DIR=/opt/mise \
    MISE_CONFIG_DIR=/opt/mise \
    MISE_CACHE_DIR=/tmp/mise-cache \
    MISE_TRUSTED_CONFIG_PATHS=/app/mise.toml \
    MISE_YES=1 \
    MISE_TRUST=1 \
    PATH="/opt/mise/shims:/opt/mise/bin:${PATH}"

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    ca-certificates curl git build-essential libssl-dev libffi-dev unzip binutils \
    tini openssh-client lsof procps dnsutils iputils-ping iproute2 hping3 \
    locales vim less htop tree rsync traceroute nmap net-tools strace xz-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl https://mise.jdx.dev/install.sh | MISE_INSTALL_PATH=/usr/local/bin/mise sh

COPY mise.toml ./
RUN --mount=type=cache,target=/tmp/mise-cache \
    mise trust && mise install && mise reshim

# Install Python build tools
RUN --mount=type=cache,target=/root/.cache/uv \
    mise exec python@3.12 -- pip install --no-cache-dir uv

# ============================================================
# Stage 2: App Builder
# ============================================================
FROM base AS builder

WORKDIR /app
COPY . .

# Install app with jupyter support
ENV UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache-dir ".[jupyter]"

# Build Frontend
WORKDIR /app/frontend
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile && pnpm run build

# ============================================================
# Stage 3: Final Release
# ============================================================
FROM base AS release

ENV NB_USER=aetherterm \
    NB_UID=1000 \
    NB_GID=100 \
    HOME=/home/aetherterm \
    AETHERTERM_PORT=57575

STOPSIGNAL SIGTERM

# Healthcheck for AetherTerm/Jupyter
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8888/healthz || curl -f http://localhost:${AETHERTERM_PORT}/ || exit 1

RUN useradd -m -u $NB_UID -s /bin/bash aetherterm

WORKDIR /app

# Copy application from builder
# Mise stores python at /opt/mise/installs/python/3.12
COPY --from=builder /opt/mise/installs/python/3.12/lib/python3.12/site-packages /opt/mise/installs/python/3.12/lib/python3.12/site-packages
COPY --from=builder /opt/mise/installs/python/3.12/bin/aetherterm* /usr/local/bin/
COPY --from=builder /app/frontend/dist /opt/mise/installs/python/3.12/lib/python3.12/site-packages/aetherterm/agentserver/static/

# Config & Entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    mkdir -p /var/log/aetherterm /var/run/aetherterm && \
    chown -R aetherterm:aetherterm /var/log/aetherterm /var/run/aetherterm /app $HOME

# code-server Installation
RUN curl -fsSL https://code-server.dev/install.sh | sh -s -- --method standalone --prefix /usr/local && \
    CODE_DIR=$(ls -d /usr/local/lib/code-server-*) && \
    rm -f "$CODE_DIR/lib/node" && \
    ln -s "/opt/mise/shims/node" "$CODE_DIR/lib/node"

USER aetherterm
EXPOSE 57575 8888 8080

ENTRYPOINT ["tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["aetherterm-agentserver", "--host=0.0.0.0", "--port=57575", "--unsecure"]
