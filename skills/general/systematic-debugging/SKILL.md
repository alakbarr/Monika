---
name: systematic-debugging
description: "Scientific root-cause analysis, log inspection, and defect remediation for Monika."
category: general
version: 1.1.0
consumers: [chat_agent, human_reference]
platforms: [windows, linux, macos]
tags: [debugging, root_cause, logging, telemetry, errors, failure_patterns]
---

# Monika Systematic Debugging & Diagnostics Playbook

## 1. 4-Step Scientific Debugging Method
1. **Observe & Capture Telemetry**:
   - Collect exact exception traceback, module name, and state snapshot.
   - Inspect application logs in `logs/` or terminal stdout.
2. **Formulate Falsifiable Hypotheses**:
   - Rank potential failure causes based on empirical telemetry rather than assumptions.
   - Test each hypothesis sequentially (e.g. database schema mismatch vs broker IPC disconnection).
3. **Apply Minimal Surgical Patch**:
   - Resolve the root vulnerability at the narrowest responsible module layer.
   - Never suppress errors with blanket `try...except Exception: pass`.
4. **Prove Resolution**:
   - Execute targeted unit test first, followed by `pytest tests/ -x -q` to guarantee zero regression.

## 2. Common Monika Failure Patterns & Diagnostic SOP

| Failure Symptom | Likely Root Cause | Diagnostic & Resolution SOP |
|:---|:---|:---|
| **Stale H4 Indicator Rejection** | MT5 terminal disconnected or historical bar fetch failed | Check `heartbeat.txt` and MT5 terminal IPC connection. Run `python -m cli.main doctor`. |
| **Broker Error 10004 (REQUOTE)** | Market moved beyond price deviation during volatility spike | Apply `mt5_slippage_defense` protocol (`ORDER_FILLING_IOC` with `deviation = 50`). |
| **Priced-In Score $\ge 8$ Hard Block** | Market has fully anticipated scheduled catalyst | Normal system safety behavior. Verify `macro_priced_in_calculator.py` outputs. Do not bypass RiskGate. |
| **Tool JSON Decode Error** | LLM output included conversational markdown wrappers around JSON | Use `extract_and_parse_json()` from `analysis/providers/base_provider.py` which scrubs thinking tags and code fences. |
| **Database Lock / Sync Timeout** | SQLite/PostgreSQL transaction held open across long async call | Ensure all DB calls use `async with session.begin():` and avoid long network I/O inside open transactions. |

## 3. Diagnostic Commands Reference
```bash
# 1. Full system health audit
python -m cli.main doctor

# 2. Re-run failed test in verbose mode
pytest tests/path/to/test_file.py -vv -s

# 3. Check database migration head
alembic current
```
