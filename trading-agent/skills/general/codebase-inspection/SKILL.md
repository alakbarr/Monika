---
name: codebase-inspection
description: "Monika codebase structure auditing, module navigation, and invariant verification."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [codebase, navigation, architecture, invariants, index, structure]
---

# Monika Codebase Inspection & Navigation Playbook

## 1. Authoritative Repository Orientation
- **Exhaustive Codebase Index**: `D:\Monika\INDEX.md` is the primary single source of truth for all modules, classes, and exported functions. Always inspect `INDEX.md` before making architectural assumptions.
- **Directory Hierarchy**: `D:\Monika\STRUCTURE.md` provides the complete file system tree.

## 2. Core Architectural Subsystems
```text
D:\Monika\trading-agent\
├── agent/                  # Central daemon lifecycle, orchestrator, and loop runners
├── analysis/               # Cognitive Engine: macro stages, debate system, quant calculators, providers
│   ├── calculators/        # Confluence, priced-in, and adaptive risk policies
│   ├── debate/             # Adversarial Bull/Bear analysts & Investment Judge
│   ├── memory/             # Trade reflection, closed-loop skill crystallizer, background review
│   ├── providers/          # Multi-LLM provider abstraction & LLMFactory
│   ├── research/           # Macro research playbook execution engine
│   └── tools/              # Tool registry, definitions, and domain tool handlers
├── config/                 # YAML settings, plugin catalogs, and backups
├── database/               # SQLAlchemy 2.0 async models, engine, and migrations
├── execution/              # MT5 IPC bridge, order execution engine, verification assertions
├── graph/                  # LangGraph state nodes, edges, and workflow orchestration
├── logging_observability/  # Telemetry, reporting (DOCX, PPTX), dashboard APIs
├── risk/                   # 10-layer deterministic RiskGate and capital preservation fortress
└── skills/                 # Declarative operational skills, playbooks, and crystallized rules
```

## 3. Tool & Protocol Inspection SOP
- When inspecting or adding an agent tool:
  1. Check declaration in `analysis/tools/tools_definitions.py` (tool name, parameters, json schema).
  2. Locate business logic handler in `analysis/tools/domain/<category>_handlers.py`.
  3. Verify registration in `analysis/tools/executor.py` or `analysis/tools/tools_registry.py`.

## 4. Invariant Verification & Health Checks
- **Automated Health Check**: Run `python -m cli.main doctor` to verify database connectivity, MT5 IPC status, and configuration validity.
- **Test Suite Verification**: Run `pytest tests/ -x -q` to verify zero regression across all core subsystems.
- **Skill Linting**: Run `python -m trading_agent.skills.trading_skill_linter` or execute skill curator verification before committing modifications to `skills/`.
