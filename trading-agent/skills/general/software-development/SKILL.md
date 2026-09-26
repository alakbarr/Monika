---
name: software-development
description: End-to-end software engineering, architecture, and safe coding standards.
category: GENERAL
version: 1.0.0
platforms:
  - windows
  - linux
  - macos
---

# Software Development Skill

Provides rigorous guidelines for building, refactoring, and maintaining production-grade software systems.

## Core Directives

1. **Understand System Architecture First**:
   - Inspect existing architectural diagrams and index files before introducing structural changes.
   - Respect established design patterns (e.g. dependency injection, decoupled event bus, repository pattern).

2. **Surgical Precision & Minimal Blast Radius**:
   - Limit modifications strictly to files directly relevant to the task.
   - Avoid indiscriminate mass refactors across unrelated modules.
   - Always run in-process syntax checks and automated unit tests after editing.

3. **Stale Overwrite Protection**:
   - Never overwrite a file without inspecting its latest disk state.
   - Use fuzzy patching with multi-stage fallbacks to ensure target context matches reality.

4. **Backward Compatibility & Invariants**:
   - Do not break existing public API contracts, database schemas, or serialized wire formats.
   - Ensure deprecations are handled gracefully with fallbacks.
