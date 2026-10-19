# Stage 1: Build React 19 Frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Core Trading Agent (Clean Architecture)
FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml alembic.ini ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps -e .

COPY src/ ./src/
COPY config/ ./config/
COPY skills/ ./skills/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/logs /app/data && \
    chown -R appuser:appuser /app

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

USER appuser
CMD ["python", "-m", "monika.interfaces.cli.main", "run"]
