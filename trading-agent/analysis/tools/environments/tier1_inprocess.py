# ==============================================================================
# File: analysis/tools/environments/tier1_inprocess.py
# ==============================================================================

"""
Tier 1: In-Process High-Throughput Quant Sandbox Environment.
Institutional-grade execution isolation architecture.

Provides sub-millisecond execution for mathematical formulas, quantitative logic,
and indicator calculations with restricted built-in globals.
"""

from __future__ import annotations

import ast
import asyncio
import datetime
import io
import json
import math
import queue
import statistics
import sys
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, Optional

from analysis.tools.environments.base_environment import (
    BaseExecutionEnvironment,
    ExecutionOutcome,
)


class Tier1InProcessEnvironment(BaseExecutionEnvironment):
    """Executes safe Python code blocks in-process with minimal latency."""

    def __init__(self):
        self._safe_globals: Dict[str, Any] = {
            "__builtins__": {
                "abs": abs,
                "all": all,
                "any": any,
                "bin": bin,
                "bool": bool,
                "dict": dict,
                "divmod": divmod,
                "enumerate": enumerate,
                "filter": filter,
                "float": float,
                "format": format,
                "hex": hex,
                "int": int,
                "isinstance": isinstance,
                "issubclass": issubclass,
                "iter": iter,
                "len": len,
                "list": list,
                "map": map,
                "max": max,
                "min": min,
                "next": next,
                "oct": oct,
                "ord": ord,
                "pow": pow,
                "print": print,
                "range": range,
                "reversed": reversed,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
                "zip": zip,
            },
            "math": math,
            "statistics": statistics,
            "json": json,
            "datetime": datetime,
        }

        # Dynamically inject numpy or pandas if available in environment
        try:
            import numpy as np
            self._safe_globals["np"] = np
            self._safe_globals["numpy"] = np
        except ImportError:
            pass

        try:
            import pandas as pd
            self._safe_globals["pd"] = pd
            self._safe_globals["pandas"] = pd
        except ImportError:
            pass

    def is_available(self) -> bool:
        return True

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout_seconds: float = 30.0,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            exit_code=1,
            stdout="",
            stderr="Tier 1 In-Process environment does not support shell command execution. Escalate to Tier 2 Host Kernel.",
            execution_time_ms=0.0,
        )

    async def run_python_code(
        self,
        code: str,
        timeout_seconds: float = 30.0,
    ) -> ExecutionOutcome:
        start_time = time.perf_counter()

        # AST Safety Guard: disallow explicit import statements or dunder access
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    return ExecutionOutcome(
                        exit_code=1,
                        stdout="",
                        stderr="Security Violation: Explicit imports are prohibited in Tier 1. Use Tier 2 Host Kernel for imports.",
                        execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
                    )
                if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                    return ExecutionOutcome(
                        exit_code=1,
                        stdout="",
                        stderr="Security Violation: Dunder attribute access prohibited in Tier 1.",
                        execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
                    )
        except SyntaxError as syn_err:
            return ExecutionOutcome(
                exit_code=1,
                stdout="",
                stderr=f"SyntaxError: {syn_err}",
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        compiled = compile(tree, filename="<tier1_sandbox>", mode="exec")
        local_scope: Dict[str, Any] = {}
        res_queue: queue.Queue = queue.Queue()

        def _execute_worker():
            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(compiled, self._safe_globals, local_scope)
                res_queue.put((0, None))
            except Exception as exc:
                res_queue.put((1, exc))

        t = threading.Thread(target=_execute_worker, daemon=True, name="tier1-sandbox-worker")
        t.start()

        loop = asyncio.get_running_loop()
        def _wait_queue():
            try:
                return res_queue.get(timeout=timeout_seconds)
            except queue.Empty:
                return None

        result = await loop.run_in_executor(None, _wait_queue)
        if result is None:
            exit_code = 1
            stderr_buf.write(f"TimeoutError: Execution exceeded timeout of {timeout_seconds}s\n")
        else:
            code, exc = result
            exit_code = code
            if exc:
                stderr_buf.write(f"{type(exc).__name__}: {str(exc)}\n")

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return ExecutionOutcome(
            exit_code=exit_code,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            execution_time_ms=elapsed_ms,
        )

    def cleanup(self) -> None:
        pass
