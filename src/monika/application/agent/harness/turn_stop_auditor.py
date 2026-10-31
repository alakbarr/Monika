"""
File: src/monika/application/agent/harness/turn_stop_auditor.py

Audits claimed turn completion and evaluates stop gates within AgentHarness.
Handles:
1. Mandatory tool invocation and persistence verification.
2. Trade proposal verification stop gate (TradeStopGate).
3. Modular risk and code verification stop gates (apply_stop_gates).
4. Physical deliverable audit (Anti-Hallucination & file integrity).
5. Interactive TODO list completion audit.
6. Anti-Slop quality gate enforcement.
7. Dual-queue follow-up task draining.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple

from monika.application.agent.harness.anti_slop_gate import AntiSlopQualityGate
from monika.application.agent.harness.trade_stop_gates import TradeStopGate
from monika.application.agent.harness.turn_failure_diagnostics import TurnFailureDiagnosticBuilder
from monika.application.agent.turn_phase_machine import TurnPhase, TurnState
from monika.application.agent.turn_stop_gates import apply_stop_gates

logger = logging.getLogger("TradingAgent.AgentHarness.TurnStopAuditor")


@dataclass
class StopAuditVerdict:
    """Verdict on whether agent is allowed to finalize and exit or must be nudged."""

    can_break: bool
    final_text: str
    unverified_stop_gate_error: Optional[str] = None
    emergency_recovery_turns_added: int = 0


class TurnStopAuditor:
    """Audits completion claims when LLM provides text without tool calls."""

    @staticmethod
    def audit_completion(
        harness: Any,
        current_messages: List[dict],
        final_text: str,
        stage_name: str,
        stage_symbol: Optional[str],
        turns: int,
        effective_max_turns: int,
        called_tools: Set[str],
        unpersisted_validation_failures: Set[str],
        turn_state: TurnState,
        tool_calls_made: int,
        emergency_recovery_turns_used: int,
        max_emergency_recovery_turns: int,
        current_unverified_error: Optional[str] = None,
    ) -> StopAuditVerdict:
        unverified_stop_gate_error = current_unverified_error
        turns_added = 0

        # 1. Mandatory Tool Enforcement
        mandatory_tool = harness.get_mandatory_tool_for_stage(stage_name)
        is_mandatory_unpersisted = mandatory_tool in unpersisted_validation_failures
        if (
            mandatory_tool
            and (mandatory_tool not in called_tools or is_mandatory_unpersisted)
            and turns < effective_max_turns
        ):
            target_sym = stage_symbol or "this asset"
            if is_mandatory_unpersisted and mandatory_tool in called_tools:
                nudge_text = (
                    f"CRITICAL MANDATORY INSTRUCTION: Your previous attempt to invoke '{mandatory_tool}' "
                    f"failed validation and was NOT saved to the database. "
                    f"You MUST call '{mandatory_tool}' again NOW with corrected parameters or change decision to 'wait' for {target_sym}. "
                    f"Plain text conclusions cannot be accepted while mandatory submission is unpersisted."
                )
            else:
                nudge_text = (
                    f"CRITICAL MANDATORY INSTRUCTION: You concluded your turn without invoking '{mandatory_tool}'. "
                    f"You MUST call '{mandatory_tool}' now with your final structured analysis and decision for {target_sym}. "
                    f"Plain text conclusions without invoking '{mandatory_tool}' cannot be processed."
                )
            logger.info(
                f"[{stage_name}][AgentHarness] Mandatory tool '{mandatory_tool}' "
                f"{'unpersisted/validation_failed' if is_mandatory_unpersisted else 'missing'} "
                f"on turn {turns}/{effective_max_turns}. Nudging agent..."
            )
            current_messages.append({"role": "user", "content": nudge_text})
            return StopAuditVerdict(
                can_break=False,
                final_text=final_text,
                unverified_stop_gate_error=unverified_stop_gate_error,
            )
        elif mandatory_tool and (mandatory_tool not in called_tools or is_mandatory_unpersisted):
            logger.warning(
                f"[{stage_name}][AgentHarness] Reached max turns ({effective_max_turns}) "
                f"without {'persisting' if is_mandatory_unpersisted else 'calling'} mandatory tool '{mandatory_tool}'."
            )

        turn_state.current_phase = TurnPhase.FINALIZE
        turn_state.stop_gate_context.pending_response = final_text

        # ── 2. Trade Proposal Verification Stop Gate ──
        trade_verdict = TradeStopGate.evaluate(
            final_text,
            harness.verification_ledger,
            stage_name=stage_name,
            stage_symbol=stage_symbol,
        )
        if not trade_verdict.should_stop:
            if turns < effective_max_turns:
                logger.info(
                    f"[{stage_name}][AgentHarness] Trade Stop Gate triggered for {trade_verdict.detected_symbol}. "
                    f"Nudging agent for risk/sizing verification..."
                )
                current_messages.append({"role": "user", "content": trade_verdict.nudge_text})
                return StopAuditVerdict(
                    can_break=False,
                    final_text=final_text,
                    unverified_stop_gate_error=unverified_stop_gate_error,
                )
            else:
                logger.warning(
                    f"[{stage_name}][AgentHarness] Reached max turns ({effective_max_turns}) without "
                    f"verified risk sizing. Candidate Preservation: safely downgrading decision to WAIT."
                )
                final_text = json.dumps(
                    {
                        "decision": "WAIT",
                        "confidence": 0.0,
                        "rationale": f"Downgraded to defensive WAIT: {trade_verdict.rejection_reason or 'Risk/sizing unverified before turn limit'}",
                        "downgraded_by_stop_gate": True,
                    }
                )

        # ── 3. Modular Financial & Verification Stop Gates (TradingRiskStopGate + CodeVerifyStopGate) ──
        can_stop_modular, modular_nudge = apply_stop_gates(final_text, turn_state.stop_gate_context)
        if not can_stop_modular and modular_nudge:
            unverified_stop_gate_error = modular_nudge
            current_effective_max = effective_max_turns
            if (
                turns >= current_effective_max
                and (emergency_recovery_turns_used + turns_added) < max_emergency_recovery_turns
            ):
                turns_added += 1
                current_effective_max += 1
            if turns < current_effective_max:
                diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                    turn_number=turns,
                    gate_name="ModularStopGate",
                    reason=modular_nudge,
                    remaining_turns=max(1, current_effective_max - turns),
                )
                logger.info(f"[{stage_name}][AgentHarness] Modular Stop Gate intercepted: {modular_nudge}")
                current_messages.append({"role": "user", "content": f"{modular_nudge}\n\n{diag.format_directive()}"})
                return StopAuditVerdict(
                    can_break=False,
                    final_text=final_text,
                    unverified_stop_gate_error=unverified_stop_gate_error,
                    emergency_recovery_turns_added=turns_added,
                )

        # ── 4. Physical Deliverable Gate (Anti-Hallucination & File Integrity Audit) ──
        deliverable_verdict = harness.physical_deliverable_gate.audit_claimed_completion(
            final_text,
            touched_files=turn_state.stop_gate_context.mutated_files,
            ledger=harness.verification_ledger,
        )
        if not deliverable_verdict.is_valid and deliverable_verdict.message:
            unverified_stop_gate_error = deliverable_verdict.message
            current_effective_max = effective_max_turns + turns_added
            if (
                turns >= current_effective_max
                and (emergency_recovery_turns_used + turns_added) < max_emergency_recovery_turns
            ):
                turns_added += 1
                current_effective_max += 1
            if turns < current_effective_max:
                diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                    turn_number=turns,
                    gate_name="PhysicalDeliverableGate",
                    reason=deliverable_verdict.message,
                    remaining_turns=max(1, current_effective_max - turns),
                )
                logger.info(
                    f"[{stage_name}][AgentHarness] Physical deliverable stop gate intercepted: "
                    f"{deliverable_verdict.message}"
                )
                current_messages.append(
                    {"role": "user", "content": f"{deliverable_verdict.message}\n\n{diag.format_directive()}"}
                )
                return StopAuditVerdict(
                    can_break=False,
                    final_text=final_text,
                    unverified_stop_gate_error=unverified_stop_gate_error,
                    emergency_recovery_turns_added=turns_added,
                )

        # ── 5. Interactive TODO List Audit (Ensure no unfinished tasks before exit) ──
        if hasattr(harness, "todo_state") and harness.todo_state and harness.todo_state.has_items():
            all_done, todo_audit_msg = harness.todo_state.audit_completion()
            if not all_done:
                unverified_stop_gate_error = f"Unfinished TODO items: {todo_audit_msg}"
                current_effective_max = effective_max_turns + turns_added
                if (
                    turns >= current_effective_max
                    and (emergency_recovery_turns_used + turns_added) < max_emergency_recovery_turns
                ):
                    turns_added += 1
                    current_effective_max += 1
                if turns < current_effective_max:
                    diag = TurnFailureDiagnosticBuilder.from_stop_gate_rejection(
                        turn_number=turns,
                        gate_name="InteractiveTodoAudit",
                        reason=todo_audit_msg,
                        remaining_turns=max(1, current_effective_max - turns),
                    )
                    logger.info(
                        f"[{stage_name}][AgentHarness] Active TODOs incomplete: {todo_audit_msg}. "
                        f"Nudging agent on turn {turns}/{current_effective_max}..."
                    )
                    current_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"[CRITICAL TODO AUDIT]: You have unfinished items in your TODO list:\n"
                                f"{todo_audit_msg}\n"
                                f"Please finish the in-progress tasks or mark them completed/cancelled using 'todo_write'.\n\n"
                                f"{diag.format_directive()}"
                            ),
                        }
                    )
                    return StopAuditVerdict(
                        can_break=False,
                        final_text=final_text,
                        unverified_stop_gate_error=unverified_stop_gate_error,
                        emergency_recovery_turns_added=turns_added,
                    )

        # ── 6. Anti-Slop Quality Gate (Enforce Professional Zero-Slop Output) ──
        if final_text and len(final_text.strip()) >= 80:
            slop_verdict = AntiSlopQualityGate.evaluate(
                final_text,
                stage_name=stage_name,
                require_quantitative_grounding=False,
            )
            if not slop_verdict.passed:
                if turns < effective_max_turns + turns_added:
                    diag = TurnFailureDiagnosticBuilder.from_slop_rejection(
                        turn_number=turns,
                        violations=slop_verdict.violations,
                        stage_name=stage_name,
                    )
                    logger.info(
                        f"[{stage_name}][AgentHarness] AntiSlopQualityGate intercepted final response on turn {turns}: "
                        f"{slop_verdict.violations}"
                    )
                    current_messages.append({"role": "user", "content": diag.format_directive()})
                    return StopAuditVerdict(
                        can_break=False,
                        final_text=final_text,
                        unverified_stop_gate_error=unverified_stop_gate_error,
                        emergency_recovery_turns_added=turns_added,
                    )
                else:
                    final_text = AntiSlopQualityGate.sanitize_surface_slop(final_text)

        if (
            can_stop_modular
            and deliverable_verdict.is_valid
            and (
                not hasattr(harness, "todo_state")
                or not harness.todo_state
                or not harness.todo_state.has_items()
                or harness.todo_state.audit_completion()[0]
            )
            and ((final_text or "").strip() or called_tools)
        ):
            unverified_stop_gate_error = None

        logger.info(
            f"[{stage_name}][AgentHarness] Agent completed in {turns} turns with {tool_calls_made} tool executions."
        )

        # ── 7. Dual-Queue Follow-Up Processing ──
        if harness._follow_up_queue:
            f_msg = harness._follow_up_queue.popleft()
            logger.info(f"[{stage_name}][AgentHarness] Draining follow-up directive from '{f_msg.sender}'.")
            current_messages.append(
                {"role": "user", "content": f"[{f_msg.sender.upper()} FOLLOW-UP TASK]: {f_msg.content}"}
            )
            return StopAuditVerdict(
                can_break=False,
                final_text=final_text,
                unverified_stop_gate_error=unverified_stop_gate_error,
                emergency_recovery_turns_added=1 if turns >= (effective_max_turns + turns_added) else turns_added,
            )

        return StopAuditVerdict(
            can_break=True,
            final_text=final_text,
            unverified_stop_gate_error=unverified_stop_gate_error,
            emergency_recovery_turns_added=turns_added,
        )
