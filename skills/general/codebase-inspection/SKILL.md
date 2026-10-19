---
name: codebase-inspection
description: "Monika codebase structure auditing, navigation, and invariant verification."
category: general
version: 1.2.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [codebase, navigation, architecture, invariants, index, structure]
---

# Monika Codebase Inspection & Navigation Playbook

## 1. Authoritative Repository Orientation
- **Exhaustive Codebase Index**: `INDEX.md` is the primary single source of truth for all modules, classes, and exported functions. Always inspect `INDEX.md` before making architectural assumptions.
- **Directory Hierarchy**: `STRUCTURE.md` provides the complete file system tree.

## 2. Core Architectural Subsystems
```text
src/monika/
├── core/                   # Telemetry, config schemas, security redactors, clocks, base paths
├── domain/                 # Pure domain entities, risk gate, indicators, ports & protocols
├── application/            # Orchestrator, cognitive engine, debates, schedulers, skills, plugins
├── infrastructure/         # MT5 broker bridge, SQLAlchemy database, scrapers, event stores
└── interfaces/             # FastAPI dashboard API, Textual TUI, CLI commands, Telegram bot
```

## 3. Tool & Protocol Inspection SOP
- When inspecting or adding an agent tool:
  1. Check declaration in `src/monika/application/analysis/tools/definitions/`.
  2. Locate business logic handler in `src/monika/application/analysis/tools/handlers/`.
  3. Verify registration in tool executor and registry.

## 4. Invariant Verification & Health Checks
- **Automated Health Check**: Run `python -m monika.interfaces.cli.main doctor --offline` to verify database connectivity, IPC status, and configuration validity.
- **Test Suite Verification**: Run `pytest tests/ -q -m "not live and not network"` to verify zero regression across all core subsystems.
- **Skill Linting**: Run `python -m monika.application.skills.trading_skill_linter` before committing modifications to `skills/`.
