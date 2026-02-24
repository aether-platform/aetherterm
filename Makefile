include Makefile.config
-include Makefile.custom.config

all: install lint build-frontend run-agentserver

# ============================================================
# Setup
# ============================================================

install:
	uv sync
	cd frontend && $(NPM) install

clean:
	rm -fr $(NODE_MODULES)
	rm -fr $(VENV)
	rm -fr *.egg-info
	find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ============================================================
# Development
# ============================================================

# AgentServer (Web Terminal)
AGENTSERVER_ARGS ?= --host=localhost --port=57575 --unsecure --debug
run-agentserver:
	uv run aetherterm-agentserver $(AGENTSERVER_ARGS)

# AgentShell (AI Terminal Wrapper)
AGENTSHELL_ARGS ?=
run-agentshell:
	uv run aetherterm-agentshell $(AGENTSHELL_ARGS)

# AgentShell ZMQ Observer (connects to running terminal)
AGENTSHELL_ZMQ_ARGS ?= --session default
run-agentshell-zmq:
	uv run aetherterm-agentshell-zmq $(AGENTSHELL_ZMQ_ARGS)

# ControlServer (Central Management)
CONTROLSERVER_ARGS ?= --port=8765
run-controlserver:
	uv run aetherterm-controlserver $(CONTROLSERVER_ARGS)

lint:
	uv run ruff check src/
	uv run ruff format --check src/

fmt:
	uv run ruff check --fix src/
	uv run ruff format src/

test:
	uv run pytest tests/

# ============================================================
# Frontend
# ============================================================

build-frontend:
	cd frontend && $(NPM) install
	cd frontend && $(NPM) run build
	mv frontend/dist/index.html src/aetherterm/agentserver/templates/index.html
	rm -rf src/aetherterm/agentserver/static/*
	cp -r frontend/dist/* src/aetherterm/agentserver/static/

# ============================================================
# Docker
# ============================================================

DOCKER_IMAGE ?= ghcr.io/aether-platform/aetherterm
DOCKER_TAG   ?= latest

# Local build (native arch only)
docker-build:
	docker compose build

# Local run
docker-up:
	docker compose up -d

docker-up-agent:
	docker compose --profile agent up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# Multi-arch build & push (requires: docker buildx create --use)
docker-buildx:
	docker buildx bake --push

docker-buildx-tag:
	TAG=$(DOCKER_TAG) docker buildx bake --push
