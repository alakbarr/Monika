# ==============================================================================
# File: agent/turn_tool_round.py
# ==============================================================================

"""
Turn Tool Round Coordinator & Persist-Before-Execute Invariant.
Institutional-grade engine turn protection architecture.

Invariants:
1. Persist-Before-Execute: The model's assistant turn and tool_calls MUST be
   durably persisted to the database/session store BEFORE any tool executes.
   If persistence fails, the coordinator fails closed (aborts turn) to prevent
   phantom side effects (e.g. broker orders placed without record in DB).
2. Mixed-Batch Partitioning: Valid tool calls in a batch execute normally;
   invalid calls receive synthetic error outputs without aborting the valid calls.
3. ESTOP Check: Evaluates emergency stop sentinel before dispatching side-effecting tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Awaitable

from agent.estop import is_estop_active, get_estop_details

logger = logging.getLogger("TradingAgent.Agent.TurnToolRound")


@dataclass
class ToolCallSpec:
    """Normalized tool call specification."""
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str = ""
    is_valid: bool = True
    error_message: Optional[str] = None


@dataclass
class ToolRoundVerdict:
    """Result of a single tool-calling round."""
    action: str  # "continue" | "break" | "return"
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    persistence_failed: bool = False
    halt_reason: Optional[str] = None
    terminal_response: Optional[str] = None


class TurnToolRoundCoordinator:
    """Coordinates tool execution with strict persistence-before-execution guarantees."""

    def __init__(
        self,
        persist_callback: Optional[Callable[[List[Dict[str, Any]]], Awaitable[bool]]] = None,
        valid_tool_names: Optional[set[str]] = None,
    ):
        self.persist_callback = persist_callback
        self.valid_tool_names = valid_tool_names or set()

    def normalize_tool_calls(
        self,
        raw_tool_calls: List[Any],
    ) -> Tuple[List[ToolCallSpec], List[ToolCallSpec]]:
        """
        Normalizes, parses JSON, and partitions tool calls into (valid_calls, invalid_calls).
        Deduplicates identical calls in the same batch.
        """
        valid: List[ToolCallSpec] = []
        invalid: List[ToolCallSpec] = []
        seen_fingerprints: set[str] = set()

        for idx, tc in enumerate(raw_tool_calls):
            # Extract id, name, args from various format styles (dict or object)
            call_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else f"call_{idx}")
            func = getattr(tc, "function", None) or (tc.get("function") if isinstance(tc, dict) else tc)
            name = getattr(func, "name", None) or (func.get("name") if isinstance(func, dict) else str(tc))
            raw_args = getattr(func, "arguments", "") or (func.get("arguments", "") if isinstance(func, dict) else "")

            # Deduplication fingerprint
            fingerprint = f"{name}:{raw_args}"
            if fingerprint in seen_fingerprints:
                logger.info(f"[TurnToolRound] Deduplicating identical tool call: {name}")
                spec = ToolCallSpec(
                    id=call_id,
                    name=name,
                    arguments={},
                    raw_arguments=str(raw_args),
                    is_valid=False,
                    error_message=f"Duplicate tool call '{name}' in same round; ignored to prevent redundant side effects.",
                )
                invalid.append(spec)
                continue
            seen_fingerprints.add(fingerprint)

            # Validate name if known tools provided
            if self.valid_tool_names and name not in self.valid_tool_names:
                spec = ToolCallSpec(
                    id=call_id,
                    name=name,
                    arguments={},
                    raw_arguments=str(raw_args),
                    is_valid=False,
                    error_message=f"Unknown tool '{name}'. Valid tools: {sorted(list(self.valid_tool_names))[:10]}...",
                )
                invalid.append(spec)
                continue

            # Parse arguments JSON
            parsed_args: Dict[str, Any] = {}
            if isinstance(raw_args, dict):
                parsed_args = raw_args
            elif isinstance(raw_args, str) and raw_args.strip():
                try:
                    parsed_args = json.loads(raw_args)
                except Exception as e:
                    spec = ToolCallSpec(
                        id=call_id,
                        name=name,
                        arguments={},
                        raw_arguments=raw_args,
                        is_valid=False,
                        error_message=f"JSON argument parsing error: {e}",
                    )
                    invalid.append(spec)
                    continue

            valid.append(ToolCallSpec(id=call_id, name=name, arguments=parsed_args, raw_arguments=str(raw_args)))

        return valid, invalid

    async def execute_tool_round(
        self,
        raw_tool_calls: List[Any],
        tool_executor_fn: Callable[[str, Dict[str, Any]], Awaitable[Any]],
        assistant_turn_metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolRoundVerdict:
        """
        Executes one tool-calling round adhering to the Persist-Before-Execute invariant.
        """
        # 0. Check ESTOP
        if is_estop_active():
            estop_details = get_estop_details() or {}
            reason = estop_details.get("reason", "ESTOP active")
            logger.critical(f"[TurnToolRound] Tool execution HALTED: ESTOP is active ({reason}).")
            return ToolRoundVerdict(
                action="break",
                halt_reason=f"Emergency Stop (ESTOP) active: {reason}",
                terminal_response=f"[PERINGATAN] Tool execution halted: Emergency Stop is active ({reason}).",
            )

        # 1. Partition calls
        valid_calls, invalid_calls = self.normalize_tool_calls(raw_tool_calls)
        tool_results: List[Dict[str, Any]] = []

        # Generate synthetic error responses for invalid calls immediately
        for inv in invalid_calls:
            tool_results.append({
                "role": "tool",
                "tool_call_id": inv.id,
                "name": inv.name,
                "content": json.dumps({"error": inv.error_message}),
                "is_error": True,
            })

        if not valid_calls and invalid_calls:
            # Only invalid calls in batch, return them directly to model
            return ToolRoundVerdict(action="continue", tool_results=tool_results)

        # 2. PERSIST-BEFORE-EXECUTE INVARIANT
        # Commit the assistant turn and tool requests before any side effects execute.
        if self.persist_callback is not None:
            try:
                all_calls = valid_calls + invalid_calls
                persist_payload = [{
                    "role": "assistant",
                    "tool_calls": [
                        {"id": v.id, "type": "function", "function": {"name": v.name, "arguments": v.raw_arguments}}
                        for v in all_calls
                    ],
                    "metadata": assistant_turn_metadata or {},
                }]
                persist_success = await self.persist_callback(persist_payload)
                if not persist_success:
                    logger.error("[TurnToolRound] Persist-Before-Execute failed (callback returned False). Failing closed.")
                    return ToolRoundVerdict(
                        action="break",
                        persistence_failed=True,
                        halt_reason="Persist-Before-Execute rejected by durable storage.",
                    )
            except Exception as e:
                logger.error(f"[TurnToolRound] Persist-Before-Execute raised exception: {e}. Failing closed.")
                return ToolRoundVerdict(
                    action="break",
                    persistence_failed=True,
                    halt_reason=f"Persist-Before-Execute exception: {str(e)}",
                )

        # 3. Parallel Read-Tool Batching vs Serial Side-Effect Execution
        # Read-only tools (get_*, fetch_*, calc_*) are safely executed concurrently in parallel via asyncio.gather.
        # Side-effecting tools (order execution, trade proposals, state mutations) remain strictly sequential.
        def _is_mutation_tool(name: str) -> bool:
            lower = name.lower()
            return any(k in lower for k in ("order", "trade", "execute", "cancel", "modify", "close", "kill", "proposal", "set_", "submit"))

        read_calls = [c for c in valid_calls if not _is_mutation_tool(c.name)]
        mutation_calls = [c for c in valid_calls if _is_mutation_tool(c.name)]

        # Execute all read-only tools in parallel
        async def _exec_single(call: ToolCallSpec) -> Dict[str, Any]:
            try:
                logger.info(f"[TurnToolRound] Executing tool: {call.name} (call_id={call.id})")
                res = await tool_executor_fn(call.name, call.arguments)
                content_str = res if isinstance(res, str) else json.dumps(res, default=str)
                return {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": content_str,
                    "is_error": False,
                }
            except Exception as e:
                logger.error(f"[TurnToolRound] Error executing tool {call.name}: {e}", exc_info=True)
                return {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps({"error": f"Tool execution failed: {str(e)}"}),
                    "is_error": True,
                }

        # 3a. Parallel execution for read tools
        if read_calls:
            logger.debug(f"[TurnToolRound] Batching {len(read_calls)} read-only tools in parallel...")
            read_results = await asyncio.gather(*[_exec_single(c) for c in read_calls])
            tool_results.extend(read_results)

        # 3b. Strict serial execution for mutation tools
        for mut_call in mutation_calls:
            mut_result = await _exec_single(mut_call)
            tool_results.append(mut_result)

        return ToolRoundVerdict(action="continue", tool_results=tool_results)
