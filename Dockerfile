# Backend: FastAPI + uv on Python 3.12
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# uv (Astral's fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.9.10 /uv /usr/local/bin/uv

WORKDIR /app

# OS deps for psycopg/asyncpg, lxml, curl_cffi, healthcheck curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libxml2 \
    libxslt1.1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Sync dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# App source
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY data ./data
COPY alembic.ini ./
COPY tests ./tests

# Final install (project itself)
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Entrypoint runs migrations + idempotent seed, then uvicorn
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh
RUN chmod +x /usr/local/bin/api-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/api-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
