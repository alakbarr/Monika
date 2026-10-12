---
name: devops-automation
description: "Monika daemon supervision, Docker VPS deployment, and graceful process management."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [devops, systemd, deployment, docker, monitoring, processes, vps]
---

# Monika DevOps Automation & Production Supervision

## 1. Startup & Shutdown Orchestration
- **Windows Local / Dev Startup**: Run `start_agent.bat` (initializes virtual environment, checks PostgreSQL DB connectivity, and launches agent loop).
- **Graceful Shutdown**: Run `stop_agent.bat` (dispatches `SIGTERM` to allow active MT5 order tickets, WAL locks, and LangGraph checkpoints to flush cleanly). Never terminate with forced kill (`SIGKILL` / `taskkill /f`) during active trade execution.

## 2. Containerized VPS Deployment
- Production Docker compose configuration is located at `deploy/docker-compose.vps.yml`.
- Standard deployment pipeline:
  ```bash
  # 1. Pull latest verified commits
  git pull origin main

  # 2. Execute database schema migrations
  alembic upgrade head

  # 3. Build and reload container services
  docker compose -f deploy/docker-compose.vps.yml up -d --build
  ```

## 3. Daemon Health & Heartbeat Supervision
- **MT5 IPC Heartbeat**: Monitor `heartbeat.txt` or IPC timestamp. If heartbeat is stale $> 120\text{ seconds}$, MT5 terminal IPC bridge is disconnected $\rightarrow$ Trigger system alarm.
- **Process Supervision**: In Linux environments, supervise via systemd unit (`Restart=always`, `RestartSec=10s`, `LimitNOFILE=65536`).
- **Post-Deploy Sanity Check**:
  ```bash
  python -m cli.main doctor
  ```
