# ==============================================================================
# File: analysis/tools/core/dispatcher.py
# ==============================================================================

"""
Asynchronous Tool Dispatcher Engine with Timeout Enforcement and Audit Logging.
Institutional-grade tool orchestration architecture.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from typing import Any, Dict, Optional

from analysis.tools.core.coercion import coerce_arguments
from analysis.tools.core.definition import ToolDefinition
from analysis.tools.core.toolset_registry import ToolsetRegistry, get_toolset_registry
from database.session_db_wal import SessionDbWal

logger = logging.getLogger("TradingAgent.Analysis.Tools.Dispatcher")


class ToolExecutionResult:
    def __init__(
        self,
        tool_name: str,
        output: Any,
        is_error: bool = False,
        has_side_effects: bool = False,
        execution_time_ms: float = 0.0,
    ):
        self.tool_name = tool_name
        self.output = output
        self.is_error = is_error
        self.has_side_effects = has_side_effects
        self.execution_time_ms = execution_time_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "output": self.output,
            "is_error": self.is_error,
            "has_side_effects": self.has_side_effects,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


class ToolDispatcher:
    """Asynchronous execution dispatcher for registered tools."""

    def __init__(
        self,
        registry: Optional[ToolsetRegistry] = None,
        db: Optional[SessionDbWal] = None,
    ):
        self.registry = registry or get_toolset_registry()
        self.db = db

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session_id: Optional[str] = None,
        turn_ordinal: int = 1,
    ) -> ToolExecutionResult:
        """
        Executes a registered tool by name with parameter coercion,
        timeout guards, and optional session WAL persistence.
        """
        start_time = time.perf_counter()
        tool_def = self.registry.get_tool(tool_name)

        if not tool_def:
            msg = f"Tool '{tool_name}' is not registered in ToolsetRegistry."
            logger.error(f"[ToolDispatcher] {msg}")
            return ToolExecutionResult(
                tool_name=tool_name,
                output=msg,
                is_error=True,
                has_side_effects=False,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        if not tool_def.handler:
            msg = f"Tool '{tool_name}' has no executable handler attached."
            return ToolExecutionResult(
                tool_name=tool_name,
                output=msg,
                is_error=True,
                has_side_effects=tool_def.has_side_effects,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # Coerce arguments
        try:
            coerced_args = coerce_arguments(tool_def.parameters, arguments)
        except Exception as e:
            msg = f"Argument coercion failed for tool '{tool_name}': {e}"
            logger.warning(f"[ToolDispatcher] {msg}")
            return ToolExecutionResult(
                tool_name=tool_name,
                output=msg,
                is_error=True,
                has_side_effects=tool_def.has_side_effects,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # Dispatch handler with timeout
        is_error = False
        raw_output: Any = None
        try:
            handler = tool_def.handler
            if inspect.iscoroutinefunction(handler):
                raw_output = await asyncio.wait_for(
                    handler(**coerced_args),
                    timeout=tool_def.timeout_seconds,
                )
            else:
                # Run synchronous handler in default threadpool to prevent event loop starvation
                loop = asyncio.get_running_loop()
                raw_output = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: handler(**coerced_args)),
                    timeout=tool_def.timeout_seconds,
                )
        except asyncio.TimeoutError:
            is_error = True
            raw_output = f"Execution timed out after {tool_def.timeout_seconds} seconds."
            logger.error(f"[ToolDispatcher] Tool '{tool_name}' timed out.")
        except Exception as exc:
            is_error = True
            raw_output = f"Tool execution raised exception: {type(exc).__name__}: {str(exc)}"
            logger.error(f"[ToolDispatcher] Tool '{tool_name}' failed: {exc}", exc_info=True)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Persist to SessionDbWal if session_id is active
        if self.db is not None and session_id is not None:
            try:
                out_str = raw_output if isinstance(raw_output, str) else json.dumps(raw_output)
                self.db.record_tool_execution(
                    session_id=session_id,
                    turn_ordinal=turn_ordinal,
                    tool_name=tool_name,
                    arguments=coerced_args,
                    output=out_str,
                    is_error=is_error,
                    has_side_effects=tool_def.has_side_effects,
                )
            except Exception as pe:
                logger.warning(f"[ToolDispatcher] Failed to record tool execution to DB: {pe}")

        return ToolExecutionResult(
            tool_name=tool_name,
            output=raw_output,
            is_error=is_error,
            has_side_effects=tool_def.has_side_effects,
            execution_time_ms=elapsed_ms,
        )
