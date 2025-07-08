include Makefile.config
-include Makefile.custom.config

all: install lint check-outdated build-frontend run

.PHONY: help
help:
	@echo "Development: make run | make stop | make restart | make status | make logs | make pids"
	@echo "Build: make install | make build-frontend | make clean | make clean-run"
	@echo "Quality: make lint | make check-outdated"
	@echo ""
	@echo "Logs and PIDs are stored in: $(PWD)/run/"

install:
	uv sync
	$(PIP) install --upgrade --no-cache pip setuptools -e .[lint,themes] devcore
	cd frontend && $(NPM) install

clean:
	rm -fr $(NODE_MODULES)
	rm -fr $(VENV)
	rm -fr *.egg-info
	@$(MAKE) clean-run

lint:
	$(PYTEST) --flake8 -m flake8 $(PROJECT_NAME)
	$(PYTEST) --isort -m isort $(PROJECT_NAME)

check-outdated:
	$(PIP) list --outdated --format=columns

# Development server commands (supervisord)
run:
	@mkdir -p $(PWD)/run
	@if ! pgrep -f "supervisord.*$(PWD)/supervisord.conf" > /dev/null; then \
		supervisord -c $(PWD)/supervisord.conf; \
		sleep 2; \
	fi
	@supervisorctl -c $(PWD)/supervisord.conf restart agentserver
	@supervisorctl -c $(PWD)/supervisord.conf tail -f agentserver

stop:
	@supervisorctl -c $(PWD)/supervisord.conf stop agentserver

restart:
	@supervisorctl -c $(PWD)/supervisord.conf restart agentserver

status:
	@supervisorctl -c $(PWD)/supervisord.conf status

logs:
	@tail -f $(PWD)/run/agentserver.log

pids:
	@echo "=== Process Status ==="
	@supervisorctl -c $(PWD)/supervisord.conf status
	@echo ""
	@echo "=== PID Files ==="
	@echo "supervisord PID: $$(cat $(PWD)/run/supervisord.pid 2>/dev/null || echo 'not found')"
	@echo "agentserver PID: $$(supervisorctl -c $(PWD)/supervisord.conf status agentserver | awk '{print $$4}' | tr -d ',')"
	@echo "frontend-dev PID: $$(supervisorctl -c $(PWD)/supervisord.conf status frontend-dev | awk '{print $$4}' | tr -d ',')"
	@echo ""
	@echo "=== Files in run/ ==="
	@ls -la $(PWD)/run/ 2>/dev/null || echo "run/ directory not found"

clean-run:
	@supervisorctl -c $(PWD)/supervisord.conf shutdown 2>/dev/null || true
	@rm -rf $(PWD)/run

# Legacy aliases
run-agentserver: run
run-debug: run

build-frontend:
	cd frontend && $(NPM) install
	cd frontend && $(NPM) run build
	mv frontend/dist/index.html src/aetherterm/agentserver/templates/index.html
	rm -rf src/aetherterm/agentserver/static/*
	cp -r frontend/dist/* src/aetherterm/agentserver/static/

release: build-frontend
	git pull
	$(eval VERSION := $(shell PROJECT_NAME=$(PROJECT_NAME) $(VENV)/bin/devcore bump $(LEVEL)))
	git commit -am "Bump $(VERSION)"
	git tag $(VERSION)
	$(PYTHON) setup.py sdist bdist_wheel upload
	git push
	git push --tags
