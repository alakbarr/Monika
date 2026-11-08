"""
File: src/monika/application/agent/harness/turn_tool_pipeline.py

Coordinates segmented tool batch execution, safety checks, guardrails, and post-tool processing in AgentHarness.
Handles:
1. Tool argument normalization, repair, and deep schema healing.
2. Pruning superseded duplicate submission calls.
3. Final-turn read tool lockdown (forcing terminal submission).
4. Unified guardrail validation (monotonic risk, read-before-act, turn caps).
5. Progressive anti-oscillation tracking (signature hashes & sliding window).
6. Tool family quota enforcement.
7. Anti-laziness inspection check on Turn 1.
8. Trade proposal verification and verified position sizing auto-recalculation.
9. ESTOP safety abort.
10. Read-only replay caching (excluding real-time financial market quotes/positions).
11. Dynamic execution via ToolExecutor with OpenTelemetry tool_span and plugin hooks.
12. Disk spillover offloading (>16KB) and lossy/lossless micro-pruning.
13. Generation-tracked data fetch deduplication and prompt injection isolation.
14. Parallel-safe vs sequential barrier segment execution via ToolBatchPlanner.
"""

from __future__ import annotations

import asyncio
import collections
import inspect
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from monika.application.agent.estop import is_estop_active
from monika.application.agent.harness.tool_batch_planner import ToolBatchPlanner
from monika.application.agent.harness.tool_repair import (
    coerce_tool_arguments,
    deep_repair_tool_arguments,
    repair_tool_arguments,
    repair_tool_name,
)
from monika.application.agent.harness.turn_failure_diagnostics import TurnFailureDiagnosticBuilder
from monika.application.agent.turn_phase_machine import TurnState
from monika.application.plugins.manager.manager import PluginHook, get_plugin_manager
from monika.core.security.prompt_injection_scanner import PromptInjectionScanner
from monika.core.telemetry.tracing.spans import tool_span
from monika.core.validation.tool_response_validator import ToolResponseValidator

logger = logging.getLogger("TradingAgent.AgentHarness.TurnToolPipeline")

REALTIME_FINANCIAL_TOOLS = frozenset(
    {
        "get_market_quote",
        "get_open_positions",
        "get_account_info",
        "get_ticks",
        "get_rate",
        "get_tick",
    }
)

GENERAL_PRUNE_TOOLS = frozenset(
    {
        "run_command",
        "run_terminal_command",
        "execute_code",
        "bash",
        "terminal",
        "read_file",
        "search_files",
        "grep",
        "git_status",
        "git_diff",
        "git_log",
        "web_search",
        "scrape_url",
        "read_url",
    }
)

UNTRUSTED_EXTERNAL_TOOLS = frozenset(
    {
        "get_news_items",
        "get_news_digest",
        "get_retail_sentiment",
        "get_social_sentiment",
        "web_search",
        "get_cot_report",
        "scrape_url",
        "get_forex_sentiment",
        "get_fxssi_sentiment",
        "get_structured_sentiment",
    }
)


@dataclass
class ToolExecutionTracking:
    """Mutable tracking state for tool executions across turn iterations."""

    tool_calls_made: int
    consecutive_tool_sig: Optional[str]
    repeated_tool_count: int
    total_sig_counts: Dict[str, int]
    sliding_window_sigs: collections.deque[str]
    called_tools: Set[str]
    persisted_mandatory_tools: Set[str]
    unpersisted_validation_failures: Set[str]


@dataclass
class ToolPipelineResult:
    """Outcome of executing a batch of tool use blocks."""

    tool_results: List[dict]
    tool_calls_made: int
    consecutive_tool_sig: Optional[str]
    repeated_tool_count: int


class TurnToolPipeline:
    """Executes tool calls while strictly adhering to safety invariants and guardrails."""

    @staticmethod
    async def execute_tools(
        harness: Any,
        session: Any,
        executor: Any,
        tool_use_blocks: List[dict],
        final_text: str,
        stage_name: str,
        stage_symbol: Optional[str],
        turns: int,
        effective_max_turns: int,
        tracking: ToolExecutionTracking,
        turn_state: TurnState,
        active_tools: List[dict],
        prefetch_satisfied_tools: Optional[Set[str]],
        kwargs: Dict[str, Any],
    ) -> ToolPipelineResult:
        planner = ToolBatchPlanner(registry=getattr(executor, "registry", None))

        # 1. Prepare and heal tool calls
        prepared_calls: List[dict] = []
        for block in tool_use_blocks:
            raw_name = (
                str(block.get("name") or "") if isinstance(block, dict) else str(getattr(block, "name", "") or "")
            )
            raw_input = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
            t_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", "")

            t_name = repair_tool_name(raw_name)
            t_input = repair_tool_arguments(raw_input)
            call_item: Dict[str, Any] = {
                "id": t_id,
                "name": t_name,
                "raw_name": raw_name,
                "input": t_input,
            }

            # ── M5: Tool Schema Validation ──
            tool_schema_fn = getattr(executor, "get_tool_schema", None)
            tool_schema = None
            if callable(tool_schema_fn) and not inspect.iscoroutinefunction(tool_schema_fn):
                res = tool_schema_fn(t_name)
                if isinstance(res, dict):
                    tool_schema = res
            if tool_schema and isinstance(tool_schema, dict) and tool_schema.get("input_schema"):
                input_schema = tool_schema["input_schema"]
                raw_sym = stage_symbol or getattr(executor, "symbol", None)
                target_symbol_ctx = (
                    raw_sym if isinstance(raw_sym, str) and raw_sym and not raw_sym.startswith("<") else None
                )
                coerce_tool_arguments(t_input, input_schema, default_symbol=target_symbol_ctx)
                schema_err = None

                try:
                    import jsonschema

                    jsonschema.validate(instance=t_input, schema=input_schema)
                except ImportError:
                    req = input_schema.get("required", [])
                    missing = [r for r in req if r not in t_input]
                    if missing:
                        schema_err = f"missing required fields {missing}"
                except Exception as ve:
                    schema_err = getattr(ve, "message", str(ve))

                if schema_err:
                    healed = deep_repair_tool_arguments(
                        t_name,
                        t_input,
                        input_schema,
                        schema_err,
                        assistant_text=final_text or "",
                        default_symbol=target_symbol_ctx,
                    )
                    if healed:
                        logger.info(
                            f"[{stage_name}][AgentHarness] Auto-healed schema validation error for {t_name} "
                            f"(previously: {schema_err})"
                        )
                        schema_err = None
                    else:
                        diag = TurnFailureDiagnosticBuilder.from_schema_validation_error(
                            turn_number=turns,
                            tool_name=t_name,
                            tool_input=t_input if isinstance(t_input, dict) else {},
                            error_msg=str(schema_err),
                            schema=input_schema,
                        )
                        logger.warning(f"[{stage_name}] Schema validation failed for {t_name}: {schema_err}")
                        if t_name in ("submit_asset_analysis", "submit_fundamental_brief"):
                            tracking.unpersisted_validation_failures.add(t_name)
                            tracking.persisted_mandatory_tools.discard(t_name)
                        call_item["_schema_error"] = {
                            "type": "tool_result",
                            "tool_use_id": t_id,
                            "name": t_name,
                            "content": json.dumps(
                                {
                                    "status": "schema_validation_error",
                                    "error": f"Invalid arguments for {t_name}: {schema_err}. Fix and re-call.",
                                    "expected_schema": diag.expected_schema_summary,
                                    "diagnostic_directive": diag.format_directive(),
                                    "_turn_failure_diagnostic": diag.to_dict(),
                                }
                            ),
                            "is_error": True,
                        }
            prepared_calls.append(call_item)

        # Prune empty duplicate submission calls if substantive submission exists
        submission_tools = {"submit_fundamental_brief", "submit_asset_analysis"}
        for sub_tool in submission_tools:
            sub_calls = [c for c in prepared_calls if c["name"] == sub_tool]
            if len(sub_calls) > 1:
                has_substantive = any(len(c.get("input", {})) > 1 for c in sub_calls)
                if has_substantive:
                    for c in sub_calls:
                        if len(c.get("input", {})) <= 1:
                            c["_superseded"] = True

        # Helper for single tool execution
        async def _execute_single_prepared_tool(call_item: dict) -> dict:
            c_name = call_item["name"]
            c_input = call_item["input"]
            c_id = call_item["id"]

            if hasattr(harness, "repeat_tool_guard") and harness.repeat_tool_guard:
                harness.repeat_tool_guard.observe(c_name, c_input)

            if call_item.get("_superseded"):
                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": json.dumps(
                        {
                            "status": "superseded",
                            "notice": "Duplicate/empty submission call superseded by substantive parallel submission in the same turn.",
                        }
                    ),
                    "is_error": False,
                }

            # Final Turn Read Tools Lockdown
            terminal_tool = (
                "submit_fundamental_brief"
                if ("fundamental" in stage_name.lower() or "stage1" in stage_name.lower())
                else (
                    "submit_asset_analysis"
                    if ("asset" in stage_name.lower() or "stage2" in stage_name.lower())
                    else None
                )
            )
            if turns >= effective_max_turns and terminal_tool and c_name != terminal_tool:
                if c_name.startswith(("get_", "read_", "search_", "inspect_", "diff_")):
                    tracking.tool_calls_made += 1
                    logger.warning(
                        f"[{stage_name}][AgentHarness] Final turn read tool lockdown: blocked '{c_name}'. Forcing '{terminal_tool}'."
                    )
                    return {
                        "type": "tool_result",
                        "tool_use_id": c_id,
                        "name": c_name,
                        "content": json.dumps(
                            {
                                "status": "read_tools_disabled",
                                "error": f"Read tools are strictly disabled on final turn {turns}/{effective_max_turns}. You MUST call '{terminal_tool}' immediately with your synthesized analysis.",
                            }
                        ),
                        "is_error": True,
                    }

            if call_item.get("_schema_error"):
                tracking.tool_calls_made += 1
                if c_name not in ("submit_fundamental_brief", "submit_asset_analysis"):
                    harness.guardrail_controller.record_denial()
                else:
                    tracking.unpersisted_validation_failures.add(c_name)
                    tracking.persisted_mandatory_tools.discard(c_name)
                return call_item["_schema_error"]

            # Guardrail Controller validation
            guard_ctx = dict(kwargs)
            if prefetch_satisfied_tools:
                guard_ctx["prefetch_satisfied_tools"] = prefetch_satisfied_tools
            guard_verdict = harness.guardrail_controller.validate_tool_call(c_name, c_input, context=guard_ctx)
            if not guard_verdict.allowed:
                logger.warning(
                    f"[{stage_name}][AgentHarness] Guardrail blocked '{c_name}' ({guard_verdict.guard_name}): {guard_verdict.reason}"
                )
                tracking.tool_calls_made += 1
                tracking.called_tools.add(c_name)
                if guard_verdict.action in ("reject", "nudge"):
                    if c_name not in ("submit_fundamental_brief", "submit_asset_analysis"):
                        harness.guardrail_controller.record_denial()
                status_val = (
                    "already_executed"
                    if guard_verdict.guard_name == "AntiOscillationGuard"
                    else f"guardrail_{guard_verdict.action}"
                )
                guard_payload: Dict[str, Any] = {
                    "status": status_val,
                    "guard": guard_verdict.guard_name,
                    "notice" if guard_verdict.action == "suppress" else "error": guard_verdict.reason,
                    "suggested_fix": guard_verdict.suggested_fix,
                }
                if guard_verdict.action in ("reject", "nudge"):
                    guard_diag = TurnFailureDiagnosticBuilder.from_guardrail_verdict(
                        turn_number=turns,
                        tool_name=c_name,
                        guard_name=guard_verdict.guard_name,
                        reason=guard_verdict.reason,
                        suggested_fix=guard_verdict.suggested_fix,
                    )
                    guard_payload["diagnostic_directive"] = guard_diag.format_directive()
                    guard_payload["_turn_failure_diagnostic"] = guard_diag.to_dict()
                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": json.dumps(guard_payload),
                    "is_error": guard_verdict.action in ("reject", "nudge"),
                }

            # Progressive Anti-Oscillation Loop Guard
            suppress_threshold = int(harness.settings.get("repeat_tool_suppress_threshold", 2))
            if c_name in ("calculate_position_size", "calculate_size", "get_optimal_intraday_levels"):
                suppress_threshold = max(suppress_threshold, 4)
            call_sig = harness.compute_tool_signature(c_name, c_input)
            tracking.total_sig_counts[call_sig] = tracking.total_sig_counts.get(call_sig, 0) + 1

            if call_sig == tracking.consecutive_tool_sig:
                tracking.repeated_tool_count += 1
            else:
                tracking.consecutive_tool_sig = call_sig
                tracking.repeated_tool_count = 1

            recent_repeats = tracking.sliding_window_sigs.count(call_sig)

            try:
                canonical_args = json.dumps(c_input, sort_keys=True)
            except Exception:
                canonical_args = str(c_input)

            is_hard_suppressed = (
                tracking.repeated_tool_count >= suppress_threshold
                or recent_repeats >= suppress_threshold
                or tracking.total_sig_counts[call_sig] >= (suppress_threshold + 1)
            )

            if is_hard_suppressed:
                logger.warning(
                    f"[{stage_name}][AgentHarness] Anti-Oscillation: Suppressing repeated call for '{c_name}' "
                    f"(consecutive={tracking.repeated_tool_count}, recent={recent_repeats}, total={tracking.total_sig_counts[call_sig]})"
                )
                suppressed_result = {
                    "status": "already_executed",
                    "notice": (
                        f"Tool '{c_name}' with identical parameters was already executed {tracking.repeated_tool_count} time(s). "
                        f"Arguments: {canonical_args}. "
                        f"Do not repeat identical calls. Synthesize data already collected and conclude analysis."
                    ),
                }
                tracking.tool_calls_made += 1
                tracking.called_tools.add(c_name)
                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": json.dumps(suppressed_result),
                }

            needs_repeat_advisory = (
                tracking.repeated_tool_count >= 2 or recent_repeats >= 1 or tracking.total_sig_counts[call_sig] >= 2
            )
            tracking.sliding_window_sigs.append(call_sig)

            # Tool Family Quota Enforcement
            allowed, quota_warn = harness.compactor.check_tool_family_quota(c_name, list(tracking.called_tools))
            if not allowed:
                logger.warning(f"[{stage_name}][AgentHarness] Tool Family Quota Exceeded for '{c_name}': {quota_warn}")
                suppressed_result = {"status": "quota_exceeded", "notice": quota_warn}
                tracking.tool_calls_made += 1
                tracking.called_tools.add(c_name)
                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": json.dumps(suppressed_result),
                }

            # submit_asset_analysis Anti-Laziness & Risk Verification Checks
            if c_name == "submit_asset_analysis":
                target_sym = c_input.get("symbol") or stage_symbol
                decision = str(c_input.get("decision") or "").upper()

                # Anti-laziness on Turn 1
                if turns == 1 and decision in ("WAIT", "HOLD", "NEUTRAL", "PASS", "NO_TRADE"):
                    inspection_tools = {
                        "get_smc_zones",
                        "get_structure_breaks",
                        "get_price_history",
                        "get_indicator_snapshot",
                        "get_mt5_bars",
                        "get_atr",
                        "get_swing_points",
                    }

                    def _normalize_inspection_name(t_name: str) -> str:
                        name = re.sub(r"_(?:M15|M30|H1|H4|D1|W1|MN|recent)$", "", str(t_name))
                        if name.startswith("price_history"):
                            return "get_price_history"
                        if name.startswith("smc_zones"):
                            return "get_smc_zones"
                        if name.startswith("structure_breaks"):
                            return "get_structure_breaks"
                        if name.startswith("indicator_snapshot") or name.startswith("technical_indicators"):
                            return "get_indicator_snapshot"
                        if name.startswith("swing_points"):
                            return "get_swing_points"
                        if name.startswith("atr"):
                            return "get_atr"
                        if name.startswith("mt5_bars") or name.startswith("multi_timeframe_candles"):
                            return "get_mt5_bars"
                        if not name.startswith("get_") and f"get_{name}" in inspection_tools:
                            return f"get_{name}"
                        return name

                    raw_inspected = set(tracking.called_tools) | set(prefetch_satisfied_tools or [])
                    all_inspected_tools = {_normalize_inspection_name(t) for t in raw_inspected} | raw_inspected
                    if not any(t in all_inspected_tools for t in inspection_tools):
                        logger.warning(
                            f"[{stage_name}][AgentHarness] Anti-laziness: blocked premature WAIT on turn 1 without technical inspection."
                        )
                        tracking.tool_calls_made += 1
                        return {
                            "type": "tool_result",
                            "tool_use_id": c_id,
                            "content": json.dumps(
                                {
                                    "status": "anti_laziness_nudge",
                                    "error": (
                                        "Cannot conclude WAIT on turn 1 without inspecting technical structure or price action. "
                                        "You must call get_smc_zones, get_structure_breaks, or get_price_history first."
                                    ),
                                }
                            ),
                            "is_error": True,
                        }

                # Risk Verification Evidence Check for BUY/SELL
                if decision in ("BUY", "SELL", "LONG", "SHORT"):
                    has_evidence = harness.verification_ledger.has_passed_evidence(target_sym)
                    has_inline_sl = c_input.get("stop_loss") is not None or bool(c_input.get("adopted_bracket"))
                    if not has_evidence and not has_inline_sl:
                        logger.warning(
                            f"[{stage_name}][AgentHarness] submit_asset_analysis ({decision} {target_sym}) "
                            f"BLOCKED: No passing verification evidence in ledger and no stop_loss provided."
                        )
                        tracking.unpersisted_validation_failures.add(c_name)
                        tracking.persisted_mandatory_tools.discard(c_name)
                        tracking.tool_calls_made += 1
                        return {
                            "type": "tool_result",
                            "tool_use_id": c_id,
                            "content": json.dumps(
                                {
                                    "status": "blocked_by_stop_gate",
                                    "error": (
                                        f"Trade proposal ({decision} {target_sym}) blocked by TradeStopGate: "
                                        f"No passing calculate_position_size or validate_risk_limits evidence recorded in ledger. "
                                        f"You MUST call calculate_position_size with exact stop_loss and take_profit parameters first."
                                    ),
                                }
                            ),
                            "is_error": True,
                        }

                    if has_evidence:
                        prop_sl = None
                        prop_entry = None
                        prop_tp = None
                        prop_lot = None
                        try:
                            if "stop_loss" in c_input:
                                prop_sl = float(c_input["stop_loss"])
                            if "take_profit" in c_input:
                                prop_tp = float(c_input["take_profit"])
                            if "entry" in c_input or "entry_price" in c_input:
                                prop_entry = float(c_input.get("entry") or c_input.get("entry_price"))
                            entry_cond = c_input.get("entry_condition")
                            if (
                                prop_entry is None
                                and isinstance(entry_cond, dict)
                                and entry_cond.get("price") is not None
                            ):
                                prop_entry = float(entry_cond["price"])
                            raw_lot = c_input.get("lot_size") or c_input.get("lots") or c_input.get("volume")
                            if raw_lot is not None:
                                prop_lot = float(raw_lot)
                        except ValueError, TypeError:
                            pass

                        is_intact, integrity_err = harness.verification_ledger.verify_proposal_integrity(
                            target_sym,
                            entry_price=prop_entry,
                            stop_loss=prop_sl,
                            take_profit=prop_tp,
                            lot_size=prop_lot,
                        )
                        if not is_intact and prop_sl is not None:
                            try:
                                from monika.domain.risk.position_sizing import calculate_lot_size

                                recalc_session = session or getattr(executor, "session", None)
                                recalc_entry = prop_entry
                                if recalc_entry is None and recalc_session is not None:
                                    from sqlalchemy import select
                                    from monika.core.primitives.clock import now as get_clock_now
                                    from monika.infrastructure.database.models import PriceOHLCV

                                    last_bar = (
                                        await recalc_session.execute(
                                            select(PriceOHLCV)
                                            .where(PriceOHLCV.symbol == target_sym)
                                            .where(PriceOHLCV.timestamp <= get_clock_now())
                                            .order_by(PriceOHLCV.timestamp.desc())
                                            .limit(1)
                                        )
                                    ).scalar_one_or_none()
                                    if last_bar:
                                        recalc_entry = float(last_bar.close)

                                if target_sym and recalc_entry is not None:
                                    sizing_res = await calculate_lot_size(
                                        symbol=target_sym,
                                        entry_price=recalc_entry,
                                        stop_loss=float(prop_sl),
                                        take_profit=float(prop_tp) if prop_tp is not None else None,
                                        direction=decision,
                                        session=recalc_session,
                                        settings=harness.settings,
                                    )
                                    if sizing_res and sizing_res.get("is_valid", True):
                                        rec_lots = sizing_res.get("recommended_lots")
                                        harness.verification_ledger.record_tool_execution(
                                            "calculate_position_size",
                                            {
                                                "symbol": target_sym,
                                                "entry_price": recalc_entry,
                                                "stop_loss": float(prop_sl),
                                                "take_profit": float(prop_tp) if prop_tp is not None else None,
                                                "lot_size": rec_lots,
                                            },
                                            sizing_res,
                                        )
                                        is_intact, integrity_err = (
                                            harness.verification_ledger.verify_proposal_integrity(
                                                target_sym,
                                                entry_price=recalc_entry,
                                                stop_loss=prop_sl,
                                                take_profit=prop_tp,
                                                lot_size=rec_lots,
                                            )
                                        )
                                        if is_intact:
                                            c_input["lot_size"] = rec_lots
                                            logger.info(
                                                f"[{stage_name}][AgentHarness] Auto-recalculated verified position sizing on-the-fly for {decision} {target_sym}: "
                                                f"SL={prop_sl}, Lots={rec_lots}, Risk=${sizing_res.get('risk_amount_usd')}"
                                            )
                            except Exception as recalc_err:
                                logger.warning(
                                    f"[{stage_name}][AgentHarness] Auto-recalculating sizing on parameter deviation failed: {recalc_err}"
                                )

                        if not is_intact:
                            logger.warning(
                                f"[{stage_name}][AgentHarness] submit_asset_analysis ({decision} {target_sym}) "
                                f"BLOCKED: Parameter integrity check failed: {integrity_err}"
                            )
                            tracking.unpersisted_validation_failures.add(c_name)
                            tracking.persisted_mandatory_tools.discard(c_name)
                            tracking.tool_calls_made += 1
                            return {
                                "type": "tool_result",
                                "tool_use_id": c_id,
                                "name": c_name,
                                "content": json.dumps(
                                    {
                                        "status": "blocked_by_parameter_integrity",
                                        "error": f"Trade proposal blocked: {integrity_err}",
                                    }
                                ),
                                "is_error": True,
                            }

            if is_estop_active():
                logger.critical(
                    f"[{stage_name}][AgentHarness] ESTOP detected before executing tool '{c_name}'. Aborting tool execution."
                )
                return {
                    "type": "tool_result",
                    "tool_use_id": c_id,
                    "name": c_name,
                    "content": json.dumps({"error": "ESTOP is active. All tool executions are halted."}),
                    "is_error": True,
                }

            await harness._log_tool_call(session, stage_name, c_name, c_input, {"status": "PENDING_EXECUTION"})
            tracking.tool_calls_made += 1
            tracking.called_tools.add(c_name)

            is_read_tool = (
                c_name.startswith(("get_", "fetch_", "calc_", "calculate_")) and c_name not in REALTIME_FINANCIAL_TOOLS
            )
            res_obj = None
            if is_read_tool:
                cached_val = harness.replay_cache.get(c_name, c_input)
                if cached_val is not None:
                    logger.info(f"[{stage_name}][AgentHarness] ReadOnlyReplayCache HIT for '{c_name}'")
                    res_obj = cached_val

            if res_obj is None:
                try:
                    plugin_mgr = get_plugin_manager()
                    await plugin_mgr.emit(
                        PluginHook.PRE_TOOL_CALL, tool_name=c_name, args=c_input, stage_name=stage_name
                    )

                    with tool_span(c_name, symbol=stage_symbol):
                        res_obj = await executor.execute(c_name, c_input)

                    await plugin_mgr.emit(
                        PluginHook.POST_TOOL_CALL,
                        tool_name=c_name,
                        args=c_input,
                        result=res_obj,
                        stage_name=stage_name,
                    )
                    if is_read_tool and isinstance(res_obj, dict) and "error" not in res_obj:
                        harness.replay_cache.put(c_name, c_input, res_obj)
                except Exception as ex:
                    logger.error(f"[{stage_name}][AgentHarness] Tool execution exception in '{c_name}': {ex}")
                    res_obj = {"error": f"Tool execution failed: {str(ex)}", "tool": c_name}

            await harness._log_tool_call(session, stage_name, c_name, c_input, res_obj)
            harness.guardrail_controller.record_tool_call(c_name, c_input, res_obj)
            is_tool_err = bool(
                isinstance(res_obj, dict)
                and (
                    bool(res_obj.get("error"))
                    or res_obj.get("status") in ("error", "failed", "rejected", "blocked", "validation_error")
                    or res_obj.get("valid") is False
                )
            )
            if not is_tool_err:
                harness.guardrail_controller.record_success()
            harness.stall_guard.record_call(c_name, res_obj, turn_idx=turns, tool_args=c_input)
            harness.verification_ledger.record_tool_execution(c_name, c_input, res_obj)

            if is_tool_err and isinstance(res_obj, dict) and "_turn_failure_diagnostic" not in res_obj:
                err_msg_val = str(
                    res_obj.get("error")
                    or res_obj.get("errors")
                    or res_obj.get("message")
                    or res_obj.get("reason")
                    or res_obj.get("status")
                    or "Tool execution failed"
                )
                err_diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
                    turn_number=turns,
                    tool_name=c_name,
                    tool_input=c_input if isinstance(c_input, dict) else {},
                    error_msg=err_msg_val,
                )
                res_obj = dict(res_obj)
                res_obj["_turn_failure_diagnostic"] = err_diag.to_dict()
                res_obj.setdefault("diagnostic_directive", err_diag.format_directive())

            if c_name == "load_tool_category" and isinstance(res_obj, dict):
                new_schemas = res_obj.get("schemas", [])
                if isinstance(new_schemas, list):
                    existing_names = {str(t.get("name", "")) for t in active_tools}
                    preserve_prefix = bool(
                        (harness.settings or {}).get("harness", {}).get("preserve_tool_prefix", False)
                        or (harness.settings or {}).get("harness", {}).get("preserve_tool_prefix_order", False)
                    )
                    if preserve_prefix:
                        newly_added = []
                        for sch in new_schemas:
                            if isinstance(sch, dict) and str(sch.get("name", "")) not in existing_names:
                                sch_copy = dict(sch)
                                sch_copy.setdefault("defer_loading", True)
                                newly_added.append(sch_copy)
                                existing_names.add(str(sch_copy.get("name", "")))
                        newly_added.sort(key=lambda t: str(t.get("name", "")))
                        active_tools.extend(newly_added)
                    else:
                        for sch in new_schemas:
                            if isinstance(sch, dict) and str(sch.get("name", "")) not in existing_names:
                                active_tools.append(dict(sch))
                                existing_names.add(str(sch.get("name", "")))
                        active_tools.sort(key=lambda t: str(t.get("name", "")))

            if c_name in (
                "patch_source_file",
                "write_source_file",
                "edit_file",
                "apply_file_patch",
                "create_file",
            ):
                target_file = (
                    c_input.get("filepath") or c_input.get("path") or c_input.get("filename") or c_input.get("file")
                )
                if target_file:
                    turn_state.stop_gate_context.mutated_files.append(str(target_file))
                    if not is_tool_err and hasattr(harness, "fs_observation_gate") and harness.fs_observation_gate:
                        harness.fs_observation_gate.record_write(str(target_file))
                turn_state.stop_gate_context.has_unverified_file_edits = True

            if any(k in c_name.lower() for k in ("read", "view", "inspect_file")):
                target_file = (
                    c_input.get("filepath") or c_input.get("path") or c_input.get("filename") or c_input.get("file")
                )
                if target_file and not is_tool_err:
                    if hasattr(harness, "fs_observation_gate") and harness.fs_observation_gate:
                        harness.fs_observation_gate.record_read(str(target_file))

            if c_name in (
                "run_verification_gate",
                "verify_syntax",
                "run_terminal_command",
                "execute_code",
                "run_command",
            ):
                cmd_str = str(c_input.get("command") or c_input.get("cmd") or "").strip().lower()
                is_trivial_echo = c_name in ("run_terminal_command", "run_command") and (
                    cmd_str in ("true", "echo", "echo ok", "rem") or cmd_str.startswith("echo ")
                )
                rc_ok = not is_tool_err and (
                    not isinstance(res_obj, dict)
                    or (res_obj.get("returncode", 0) == 0 and res_obj.get("exit_code", 0) == 0)
                )
                if rc_ok and not is_trivial_echo:
                    turn_state.stop_gate_context.verification_commands_run.append(c_name)
                    turn_state.stop_gate_context.has_unverified_file_edits = False

            if c_name in ("submit_asset_analysis", "submit_fundamental_brief"):
                validation_fail_statuses = {
                    "validation_failed",
                    "rejected_verification_required",
                    "rejected_confluence_too_low",
                    "blocked",
                    "error",
                    "failed",
                }
                st = res_obj.get("status") if isinstance(res_obj, dict) else None
                has_err = is_tool_err or (
                    isinstance(res_obj, dict) and "error" in res_obj and st not in ("saved", "success", "updated")
                )
                if st in validation_fail_statuses or has_err:
                    tracking.unpersisted_validation_failures.add(c_name)
                else:
                    tracking.unpersisted_validation_failures.discard(c_name)
                    tracking.persisted_mandatory_tools.add(c_name)
                    if c_name == "submit_asset_analysis" and not is_tool_err:
                        sub_dec = str(
                            (res_obj.get("decision") if isinstance(res_obj, dict) else None)
                            or c_input.get("decision")
                            or ""
                        ).lower()
                        sub_sym = str(
                            (res_obj.get("symbol") if isinstance(res_obj, dict) else None)
                            or c_input.get("symbol")
                            or stage_symbol
                            or ""
                        )
                        if sub_dec in ("buy", "sell", "long", "short") and sub_sym:
                            v_ledger = getattr(harness, "verification_ledger", None)
                            if v_ledger is not None and not v_ledger.has_passed_evidence(sub_sym):
                                v_ledger.record_tool_execution(
                                    "calculate_position_size",
                                    {
                                        "symbol": sub_sym,
                                        "entry_price": c_input.get("entry_price")
                                        or (
                                            c_input.get("entry_condition", {}).get("price")
                                            if isinstance(c_input.get("entry_condition"), dict)
                                            else None
                                        ),
                                        "stop_loss": c_input.get("stop_loss"),
                                        "take_profit": c_input.get("take_profit"),
                                        "lot_size": c_input.get("lot_size") or 0.01,
                                    },
                                    {"is_valid": True, "recommended_lots": c_input.get("lot_size") or 0.01},
                                )

            if c_name in ("propose_action", "propose_trade") or (
                c_name == "submit_asset_analysis"
                and (
                    str(c_input.get("decision") or "").lower() in ("buy", "sell", "long", "short")
                    or (isinstance(res_obj, dict) and str(res_obj.get("decision") or "").lower() in ("buy", "sell"))
                )
            ):
                turn_state.stop_gate_context.proposed_actions.append(c_input)
                turn_state.stop_gate_context.has_unregistered_trade_proposals = False

            # Disk spillover check
            try:
                from monika.application.analysis.tools.tool_result_storage import get_tool_result_storage

                res_obj, was_spilled = get_tool_result_storage().maybe_persist(c_name, c_input, res_obj)
            except Exception as e:
                logger.debug(f"[AgentHarness] Tool result spillover check error: {e}")

            # Format tool result block
            try:
                sanitized_result, is_valid, warning = ToolResponseValidator.validate_and_sanitize(c_name, res_obj)
                if not is_valid:
                    error_context = ToolResponseValidator.build_error_context(c_name, warning)
                    tool_res_content = (
                        json.dumps(sanitized_result, default=str)
                        if not isinstance(sanitized_result, str)
                        else sanitized_result
                    ) + error_context
                else:
                    tool_res_content = (
                        json.dumps(sanitized_result, ensure_ascii=False, default=str)
                        if not isinstance(sanitized_result, str)
                        else sanitized_result
                    )
            except Exception:
                tool_res_content = json.dumps(res_obj, default=str) if not isinstance(res_obj, str) else res_obj

            tool_res_content = harness.compactor.micro_prune(tool_res_content, tool_name=c_name)

            # Zero-Cost Lossless Structural Tool Output Pruning
            general_max_chars = int(harness.settings.get("general_tool_max_chars", 2500))
            if c_name in GENERAL_PRUNE_TOOLS and len(tool_res_content) > general_max_chars:
                if isinstance(res_obj, (dict, list)):
                    tool_res_content = harness.general_tool_pruner.prune_json(
                        res_obj, max_chars=general_max_chars, tool_name=c_name
                    )
                else:
                    tool_res_content = harness.general_tool_pruner.prune_text(
                        tool_res_content, max_chars=general_max_chars, tool_name=c_name
                    )
            elif len(tool_res_content) > 16000:
                if isinstance(res_obj, (dict, list)):
                    tool_res_content = harness.general_tool_pruner.prune_json(
                        res_obj, max_chars=16000, tool_name=c_name
                    )
                else:
                    tool_res_content = harness.general_tool_pruner.prune_text(
                        tool_res_content, max_chars=16000, tool_name=c_name
                    )

            dedup_notice = harness.data_dedup.check_and_record(c_name, c_input, tool_res_content)
            if dedup_notice:
                tool_res_content = dedup_notice

            if c_name in UNTRUSTED_EXTERNAL_TOOLS:
                try:
                    tool_res_content = PromptInjectionScanner.sanitize_or_block(tool_res_content, source=c_name)
                except Exception as ex:
                    logger.warning(f"Prompt injection scanner failed for '{c_name}': {ex}. Quarantining content.")
                    tool_res_content = f"[SECURITY WARNING: External content from '{c_name}' quarantined due to safety scanner exception]"
                tool_res_content = (
                    f'<untrusted_external_content source="{c_name}">\n{tool_res_content}\n</untrusted_external_content>'
                )

            if needs_repeat_advisory:
                if tracking.repeated_tool_count >= 5 or tracking.total_sig_counts.get(call_sig, 0) >= 5:
                    advisory_note = (
                        f"\n\n[STRONG WARNING: Tool '{c_name}' has been executed {tracking.repeated_tool_count} times "
                        f"with identical arguments: {canonical_args}. This indicates an unproductive loop. "
                        f"You MUST shift strategies or synthesize your findings now.]"
                    )
                elif tracking.repeated_tool_count >= 3 or tracking.total_sig_counts.get(call_sig, 0) >= 3:
                    advisory_note = (
                        f"\n\n[REFLECTION ADVISORY: Tool '{c_name}' has been invoked {tracking.repeated_tool_count} times "
                        f"with these exact arguments. Reflect on whether new information is being gained.]"
                    )
                else:
                    advisory_note = (
                        f"\n\n[ADVISORY REMINDER: Tool '{c_name}' with identical parameters was already called previously. "
                        f"Avoid redundant calls. Synthesize collected data and conclude.]"
                    )
                tool_res_content = f"{tool_res_content}{advisory_note}"

            return {
                "type": "tool_result",
                "tool_use_id": c_id,
                "name": c_name,
                "content": tool_res_content,
                "is_error": is_tool_err,
            }

        # 2. Plan segments into [Parallel Safe] -> [Barrier] -> [Parallel Safe]
        tool_results: List[dict] = []
        segments = planner.plan_segments(prepared_calls)
        for seg_type, batch in segments:
            if seg_type == "parallel" and len(batch) > 1:
                raw_results = await asyncio.gather(
                    *[_execute_single_prepared_tool(tc) for tc in batch], return_exceptions=True
                )
                for idx, res in enumerate(raw_results):
                    if isinstance(res, BaseException):
                        tc = batch[idx]
                        logger.error(f"[{stage_name}][AgentHarness] Parallel tool {tc.get('name')} failed: {res}")
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tc.get("id", ""),
                                "content": json.dumps({"status": "execution_error", "error": str(res)}),
                                "is_error": True,
                            }
                        )
                    else:
                        tool_results.append(res)
            else:
                for tc in batch:
                    try:
                        res = await _execute_single_prepared_tool(tc)
                        tool_results.append(res)
                    except Exception as ex:
                        logger.error(f"[{stage_name}][AgentHarness] Sequential tool {tc.get('name')} failed: {ex}")
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tc.get("id", ""),
                                "content": json.dumps({"status": "execution_error", "error": str(ex)}),
                                "is_error": True,
                            }
                        )

        return ToolPipelineResult(
            tool_results=tool_results,
            tool_calls_made=tracking.tool_calls_made,
            consecutive_tool_sig=tracking.consecutive_tool_sig,
            repeated_tool_count=tracking.repeated_tool_count,
        )
