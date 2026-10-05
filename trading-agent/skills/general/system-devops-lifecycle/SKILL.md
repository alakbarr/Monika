---
name: system-devops-lifecycle
description: "DevOps lifecycle management: health diagnostics, backups, service management."
category: GENERAL
version: 1.0.0
platforms: [windows, linux, macos]
tags: [devops, restart, backup, vacuum, maintenance, service, systemctl, doctor, log, hot_reload, diagnostik]
---

# System DevOps Lifecycle & Operational Reliability

## 1. Scope & Invariants
Monika operates as a 24/7 mission-critical trading harness. Maintaining infrastructure health, low latency, database integrity, and operational state is vital.

## 2. Standard Diagnostics & Health Monitoring

### Routine Health Check
- Query `get_system_health()` to inspect:
  - Database connection status and pending migrations.
  - MT5 terminal connectivity and ping latency.
  - LLM provider status and token budget utilization.
  - Active background scheduler tasks and cron jobs.

### Latency Inspection
- Query `get_latency_breakdown()` to verify:
  - MT5 order execution round-trip latency (target < 50ms).
  - Database query execution time.
  - LLM inference latency across providers.

## 3. Database Maintenance & Backup
- **Automated Backup**: Trigger database backup routines before major schema migrations or parameter adjustments.
- **WAL & Vacuuming**: For SQLite databases, monitor file size and invoke VACUUM optimization when necessary to prevent fragmentation.
- **Table Retention**: Prune expired tick buffers and historical logs past configured retention limits (default: 30 days for tick logs, 90 days for chronicle entries).

## 4. Configuration Updates & Hot-Reloading
- Use `update_config_parameter(key, value)` with strict parameter validation:
  - Risk parameters must never exceed hard limits (risk per trade <= 3%, max daily drawdown <= 10%).
  - Non-critical parameters reload instantly via `config/hot_reload.py` without requiring terminal restart.
  - If a service restart is strictly necessary, ensure pending orders and open position stops are registered in MT5 server-side before terminating processes.
