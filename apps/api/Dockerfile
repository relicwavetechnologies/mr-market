FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared package first (for layer caching)
COPY packages/shared /packages/shared
RUN pip install --no-cache-dir /packages/shared

# Install API dependencies
COPY apps/api/pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY apps/api/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
