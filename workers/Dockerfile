FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by lxml, numpy, torch, PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared package first (changes less often)
COPY packages/shared /tmp/shared
RUN pip install --no-cache-dir /tmp/shared && rm -rf /tmp/shared

# Install worker dependencies
COPY workers/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir .

# Copy worker source
COPY workers/app /app/app

# Default: run Celery worker with beat scheduler embedded
CMD ["celery", "-A", "app.celery_app:celery", "worker", "--beat", "--loglevel=info", "--concurrency=4"]
