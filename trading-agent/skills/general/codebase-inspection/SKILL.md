---
name: codebase-inspection
description: Codebase structure auditing, symbol navigation, and invariant verification.
category: GENERAL
version: 1.0.0
platforms:
  - windows
  - linux
  - macos
---

# Codebase Inspection Skill

Guidelines for auditing large-scale repositories, tracing cross-module dependencies, and verifying architectural invariants.

## Inspection Checklist

1. **Top-Level Entry Points**:
   - Trace startup lifecycle from orchestrator entry point down to background task pools.
   - Inspect configuration loading precedence, environment variable defaults, and validation schemas.

2. **Data & State Flow**:
   - Identify single sources of truth (SSOT) for critical runtime state.
   - Audit database models, session management, and cross-thread concurrency safety.

3. **Tool & Protocol Surfaces**:
   - Verify tool registry completeness, input model type annotations, and safety sandboxing.
   - Check error handling, graceful fallback degradation, and telemetry reporting.
