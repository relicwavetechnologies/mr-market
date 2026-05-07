#!/usr/bin/env bash
# Backend container entrypoint: wait for Postgres, run migrations + seed, then exec the CMD.
set -euo pipefail

echo "[api] waiting for postgres at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python - <<'PY'
import os, socket, time, sys
host = os.getenv("POSTGRES_HOST", "db")
port = int(os.getenv("POSTGRES_PORT", "5432"))
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[api] postgres reachable at {host}:{port}", flush=True)
            sys.exit(0)
    except OSError:
        time.sleep(1)
print("[api] postgres did not become reachable in 60s", flush=True)
sys.exit(1)
PY

echo "[api] running alembic migrations..."
alembic upgrade head

echo "[api] seeding NIFTY-50 universe (idempotent)..."
python -m scripts.seed_universe || echo "[api] seed step exited non-zero (continuing)"

echo "[api] starting: $*"
exec "$@"
