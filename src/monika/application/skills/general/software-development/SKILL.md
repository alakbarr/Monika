---
name: software-development
description: "Surgical software engineering, safe refactoring, and quality invariants for Monika."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [software_engineering, architecture, testing, refactoring, invariants]
---

# Software Development Skill & Engineering Standards

## 1. Pre-Edit Mandatory Checklist
Before making any file modifications:
1. **Read-Before-Write**: Always read the target file completely using `view_file` or `read_file` to understand surrounding context and existing imports.
2. **Identify Callers**: Search for all call-sites across the codebase to ensure interface changes do not break downstream consumers.
3. **Locate Test Fixtures**: Find corresponding test files in `tests/` to prepare validation assertions.
4. **Stale Overwrite Protection**: Never overwrite a file without inspecting its latest disk state.

## 2. Surgical Precision & Minimal Blast Radius
- **Surgical Edits**: Restrict changes strictly to the narrowest responsible layer. Never perform indiscriminate multi-file refactors when a localized patch solves the issue.
- **Backward Compatibility**: Preserve existing function signatures and dataclass/Pydantic schemas where external modules depend on them.
- **Type Annotations**: All new functions and methods MUST include complete Python 3.10+ type hints (`typing.Optional`, `typing.Union`, `list[str]`, `dict[str, Any]`).

## 3. Post-Edit Mandatory Verification Checklist
After modifying any Python source file:
- [ ] Run targeted unit test:
  ```bash
  pytest tests/path/to/test_modified_module.py -v
  ```
- [ ] Run full test suite regression check:
  ```bash
  pytest tests/ -x -q
  ```
- [ ] Ensure zero new lint or import syntax warnings.

## 4. Prohibited Anti-Patterns
- ❌ Blind file overwriting without reading existing content.
- ❌ Modifying database schemas without an accompanying Alembic migration script.
- ❌ Introducing new third-party dependencies without verifying Python standard library alternatives.
- ❌ Leaving empty exception handlers (`except Exception: pass`) without logging.
