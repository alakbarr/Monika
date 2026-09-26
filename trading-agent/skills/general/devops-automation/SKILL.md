---
name: devops-automation
description: "Process orchestration, systemd management, and containerized deployment."
version: 1.0.0
category: GENERAL
tags: [devops, systemd, deployment, docker, monitoring, processes]
---

# DevOps Automation & Process Supervision

## Overview
Institutional guidelines for managing server processes, background daemons, systemd service units, and automated deployment pipelines for trading systems.

## Operational Directives
1. **Daemon Supervision**:
   - Always run production trading daemons under systemd or supervisor with automatic restart policies (`Restart=always`, `RestartSec=10`).
   - Monitor heartbeat files written by EA bridges or background scheduled loops.

2. **Zero Downtime Updates**:
   - Use atomic symlinks (`current -> releases/20260927_01`) or container rolling updates.
   - Run pre-flight health checks and database migrations (`alembic upgrade head`) before shifting traffic.

3. **Safe Process Interruption**:
   - Never kill critical trading processes with `SIGKILL` (`kill -9`) without first attempting `SIGTERM` to allow open order states and SQLite WAL locks to flush cleanly.
