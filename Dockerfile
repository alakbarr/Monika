# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY trading-agent/logging_observability/dashboard/frontend/package*.json ./
RUN npm ci
COPY trading-agent/logging_observability/dashboard/frontend/ ./
RUN npm run build

# Stage 2: Core Trading Agent
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client curl && rm -rf /var/lib/apt/lists/*

COPY trading-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY trading-agent/ ./trading-agent/
COPY --from=frontend-builder /app/frontend/dist /app/trading-agent/logging_observability/dashboard/frontend/dist
ENV PYTHONPATH=/app/trading-agent

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

USER appuser
CMD ["python", "trading-agent/main.py"]
