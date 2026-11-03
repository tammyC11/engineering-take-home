.PHONY: help doctor setup up down restart observe app test test-api test-app lint format migration logs psql erase reset

COMPOSE := docker compose
# Tool containers run as you, so files they write into the repo stay yours (matters on Linux).
ME := $(shell id -u):$(shell id -g)
API := $(COMPOSE) run --rm --user $(ME)
TEST_DB := -e DATABASE_URL=postgresql+psycopg://diary:diary@db:5432/diary_test
# The Flutter image only runs as root, so its output is handed back to you afterwards.
flutter = $(COMPOSE) run --rm flutter sh -c '$(1); status=$$?; chown -R $(ME) /app; exit $$status'

help: ## Show the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

doctor: ## Check that Docker is installed, running, and the ports are free
	@command -v docker >/dev/null || { echo "Docker is missing: https://docs.docker.com/get-docker/"; exit 1; }
	@docker info >/dev/null 2>&1 || { \
		if docker info 2>&1 | grep -qi "permission denied"; then \
			echo 'Docker refused access. Run: sudo usermod -aG docker $$USER, then log out and in.'; \
		else echo "Docker is installed but not running. Start it and retry."; fi; exit 1; }
	@$(COMPOSE) version >/dev/null 2>&1 || { echo "Docker Compose v2 is missing."; exit 1; }
	@$(COMPOSE) ps --format '{{.Ports}}' | grep -q ':2800[0-3]->' \
		|| docker run --rm -p 28000:1 -p 28001:2 -p 28002:3 -p 28003:4 nginx:1.29-alpine true >/dev/null 2>&1 \
		|| { echo "Can't use ports 28000-28003. Is another program using them?"; exit 1; }
	@echo "All good."

setup: doctor ## Download and build everything once (a few GB; do this before you start the clock)
	$(COMPOSE) --profile tools --profile observe pull db web flutter prometheus grafana
	$(COMPOSE) build
	$(call flutter,flutter pub get)
	$(MAKE) app

up: ## Start the API (localhost:28000/docs) and the app (localhost:28001)
	@test -f app/build/web/index.html || $(MAKE) app
	$(COMPOSE) up -d --wait
	@echo "App: http://localhost:28001   API docs: http://localhost:28000/docs"

down: ## Stop everything
	$(COMPOSE) --profile observe down

restart: ## Restart the API; this also applies new migrations
	$(COMPOSE) restart api

observe: ## Start Prometheus (localhost:28002) and Grafana (localhost:28003)
	$(COMPOSE) --profile observe up -d --wait
	@echo "Grafana: http://localhost:28003   Prometheus: http://localhost:28002"

app: ## Rebuild the Flutter web app (reload the browser afterwards)
	$(call flutter,flutter build web --no-web-resources-cdn)

test: test-api test-app ## Run all tests

test-api: ## Run backend tests (uses a separate test database)
	$(API) $(TEST_DB) api pytest

test-app: ## Run Flutter tests
	$(call flutter,flutter test)

lint: ## Lint backend and app
	$(API) --no-deps api ruff check .
	$(call flutter,flutter analyze)

format: ## Format backend and app code
	$(API) --no-deps api ruff format .
	$(call flutter,dart format lib test)

migration: ## Create a migration: make migration m="add something", then make restart
	$(API) api alembic revision --autogenerate -m "$(m)"

logs: ## Follow the API logs
	$(COMPOSE) logs -f api

psql: ## Open a SQL shell on the database
	$(COMPOSE) exec db psql -U diary diary

erase: ## Erase one patient's data: make erase PATIENT=1 (a dry run), then add CONFIRM=yes
	@test -n "$(PATIENT)" || { echo "Usage: make erase PATIENT=<id> [CONFIRM=yes]"; exit 1; }
	$(API) api python -m app.erase $(PATIENT) $(if $(filter yes,$(CONFIRM)),--confirm)

reset: ## Delete the database and start fresh
	$(COMPOSE) --profile observe down -v
	$(MAKE) up
