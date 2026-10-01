---
name: code-optimization
description: "Minimal, dependency-light, async-first software architecture and code optimization."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [minimalism, yagni, refactoring, performance, async, sqlalchemy, zero_bloat]
---

# Monika Architecture & Code Optimization Playbook

## 1. Async-First I/O Invariants
- **Non-Blocking Execution**: All database queries, MT5 IPC bridge calls, network scrapers, and external HTTP requests MUST use `async/await`.
- **Prohibited**: Never invoke synchronous `time.sleep()`, synchronous `requests.get()`, or blocking DB calls inside async loops. Use `asyncio.sleep()` or `httpx.AsyncClient`.

## 2. SQLAlchemy 2.0 Modern Standards
- **Use Modern 2.0 Syntax**: Strictly utilize `select(Model).where(...)` syntax. Legacy 1.x `session.query(Model)` is deprecated and prohibited.
- **Transaction Context Managers**: Always encapsulate database mutations within safe transactional boundaries:
  ```python
  from database.safe_ops import safe_commit
  # Preferred pattern
  async with session.begin():
      stmt = select(SystemConfig).where(SystemConfig.key == "example_key")
      result = (await session.execute(stmt)).scalar_one_or_none()
  ```

## 3. EventBus Decoupling Pattern
- Use `EventBus.emit(event_type, payload)` for cross-subsystem communication (e.g. notifying risk guards, updating position trackers) rather than importing concrete stage modules directly.
- Keeps cognitive layers (`analysis/`), fortress layers (`risk/`), and execution layers (`execution/`) cleanly isolated.

## 4. Error Boundary & Tool Handlers Pattern
- All domain tool handlers MUST catch internal exceptions and return structured dictionary responses (`{"error": "...", "status": "failed"}`) rather than raising unhandled exceptions into the LangGraph loop.
- Never catch raw `Exception` silently with `pass`. Log every unexpected error with appropriate context:
  ```python
  try:
      ...
  except Exception as e:
      logger.warning(f"[{module_name}] Operation failed non-fatally: {e}")
      return {"error": str(e), "status": "failed"}
  ```

## 5. Clean Imports & Anti-Bloat
- Avoid circular imports by importing type annotations under `if TYPE_CHECKING:` guards or importing domain handlers lazily inside tool execution methods.
- Standard Library First: Prefer `dataclasses`, `functools`, `typing`, `asyncio`, `re`, `json`, `datetime` over heavy third-party utility packages.
