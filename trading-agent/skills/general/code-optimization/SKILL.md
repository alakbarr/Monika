---
name: code-optimization
description: Enforce minimal, dependency-light, standard-library-first code architectures.
category: engineering
version: 1.0.0
platforms: [windows, linux, macos]
tags: [minimalism, yagni, refactoring, performance, zero-bloat, stdlib]
---

# Minimal Architecture & Code Optimization Playbook

Institutional principles for writing high-performance, maintainable code with minimal external dependency footprints.

## 1. Core Principles
- **YAGNI (You Aren't Gonna Need It)**: Do not create abstractions, generic factories, or speculative wrappers until three concrete distinct call-sites demand them.
- **Standard Library First**:
  - Always prefer Python stdlib (`dataclasses`, `functools`, `typing`, `asyncio`, `sqlite3`, `hashlib`, `hmac`, `decimal`, `json`, `math`) before adding third-party dependencies.
  - Avoid heavy libraries for trivial utility tasks (e.g. use `re` or `urllib` instead of introducing heavy parsing dependencies).

## 2. Refactoring Rules
- **One Line Over Fifty**: If a standard library list comprehension or dictionary lookup solves the problem, eliminate custom iteration classes.
- **Fail-Closed Defensive Design**: Every external boundary (I/O, database, network) must fail closed with clean fallback states.
- **Cyclomatic Complexity**: Functions must not exceed 10 branches of complexity; extract pure helper functions where branching expands.
