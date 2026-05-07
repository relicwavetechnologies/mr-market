.PHONY: up down logs ps restart rebuild clean status web-only api-only

# Bring the whole stack up in the foreground with colored, prefixed logs.
# Ctrl+C stops cleanly. First run will build images (~2 min).
up:
	docker compose up

# Detached mode
up-d:
	docker compose up -d

# Stop and remove containers; named volumes (DB + Redis data) persist.
down:
	docker compose down

# Wipe everything including DB data and node_modules cache.
clean:
	docker compose down -v --remove-orphans

# Tail logs (all services). Add SERVICE=api to follow one.
logs:
	docker compose logs -f $(SERVICE)

# Show status
ps:
	docker compose ps

status:
	@docker compose ps
	@echo
	@curl -s -o /dev/null -w "  api  http://localhost:8000/healthz  HTTP %{http_code}\n" http://localhost:8000/healthz || true
	@curl -s -o /dev/null -w "  web  http://localhost:5173/         HTTP %{http_code}\n" http://localhost:5173/        || true

# Restart just one service (no rebuild). Usage: make restart SERVICE=api
restart:
	docker compose restart $(SERVICE)

# Rebuild images after Dockerfile / dependency changes.
rebuild:
	docker compose build --no-cache
	docker compose up
