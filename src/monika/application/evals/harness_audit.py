# ==============================================================================
# File: application/evals/harness_audit.py
# ==============================================================================

"""
Hermetic Agent-Harness Audit Suite.

Measures safety, verification, routing, prompt, and delegation invariants without
LLM calls, network access, a database, or broker connectivity. Each check returns
``passed=True`` only when the desired invariant holds; failures are the actionable
output of the audit and become regression gates once Wave 1 fixes land.

The suite is intentionally behavior-first: it invokes the real ledger, deliverable
gate, router, prompt builder, delegation worker, safety guard, and tool catalog
instead of asserting on source strings wherever a behavior probe is possible.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List

AUDIT_VERSION = 1


@dataclass(frozen=True)
class AuditResult:
    """Outcome of one harness invariant probe."""

    check_id: str
    title: str
    passed: bool
    detail: str
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditReport:
    """Aggregated audit output suitable for CI artifacts and dashboards."""

    generated_at: str
    duration_ms: float
    checks: List[AuditResult]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": AUDIT_VERSION,
            "generated_at": self.generated_at,
            "duration_ms": self.duration_ms,
            "summary": {
                "total": len(self.checks),
                "passed": self.passed,
                "failed": self.failed,
                "all_passed": self.all_passed,
            },
            "checks": [
                {
                    "check_id": c.check_id,
                    "title": c.title,
                    "passed": c.passed,
                    "detail": c.detail,
                    "metrics": c.metrics,
                }
                for c in self.checks
            ],
        }


# ------------------------------------------------------------------------------
# Pure helpers (unit-testable without touching production components)
# ------------------------------------------------------------------------------


def count_macro_duplicate_headers(text: str) -> Dict[str, int]:
    """Counts macro skill headers that must appear at most once in a prompt."""
    return {
        "authoritative_event": text.count("## AUTHORITATIVE EVENT PROBABILITY PLAYBOOK"),
        "authoritative_central_banks": text.count("## AUTHORITATIVE CENTRAL BANKS FRAMEWORK"),
        "activated_event": text.count("ACTIVATED SPECIALIZATION SKILL: EVENT-PROBABILITY-PLAYBOOK"),
        "activated_central_banks": text.count("ACTIVATED SPECIALIZATION SKILL: CENTRAL-BANKS-FRAMEWORK"),
    }


def has_macro_duplication(text: str) -> bool:
    """True when a macro playbook is injected more than once in the same prompt."""
    counts = count_macro_duplicate_headers(text)
    return (
        counts["authoritative_event"] > 1
        or counts["authoritative_central_banks"] > 1
        or counts["activated_event"] > 0
        or counts["activated_central_banks"] > 0
    )


# ------------------------------------------------------------------------------
# Invariant probes
# ------------------------------------------------------------------------------


async def _check_ledger_proposal_integrity() -> AuditResult:
    from monika.application.agent.harness.verification_evidence_ledger import VerificationEvidenceLedger

    ledger = VerificationEvidenceLedger()
    ledger.record_tool_execution(
        "calculate_position_size",
        {
            "symbol": "EURUSD",
            "entry": 1.08,
            "stop_loss": 1.07,
            "take_profit": 1.10,
            "lot_size": 0.10,
        },
        {"status": "passed", "symbol": "EURUSD", "lot_size": 0.10},
    )

    tampered_tp, _ = ledger.verify_proposal_integrity(
        "EURUSD", entry_price=1.08, stop_loss=1.07, take_profit=9.99, lot_size=0.10
    )
    tampered_lot, _ = ledger.verify_proposal_integrity(
        "EURUSD", entry_price=1.08, stop_loss=1.07, take_profit=1.10, lot_size=9.99
    )
    missing_sl, _ = ledger.verify_proposal_integrity(
        "EURUSD", entry_price=1.08, stop_loss=None, take_profit=1.10, lot_size=0.10
    )

    accepted = [
        name
        for name, ok in (("tampered_tp", tampered_tp), ("tampered_lot", tampered_lot), ("missing_sl", missing_sl))
        if ok
    ]
    return AuditResult(
        check_id="ledger_proposal_integrity",
        title="Proposal verification binds entry/SL/TP/lot to sizing evidence",
        passed=not accepted,
        detail=(
            "Rejected all tampered proposals."
            if not accepted
            else f"Accepted tampered proposals: {', '.join(accepted)} (expected all rejected)."
        ),
        metrics={"accepted_tampered": accepted},
    )


async def _check_ledger_symbolless_evidence() -> AuditResult:
    from monika.application.agent.harness.verification_evidence_ledger import VerificationEvidenceLedger

    ledger = VerificationEvidenceLedger()
    ledger.record_tool_execution(
        "calculate_position_size",
        {"entry": 1.08, "stop_loss": 1.07, "lot_size": 0.10},
        {"status": "passed", "lot_size": 0.10},
    )
    # Same numeric levels as the symbol-less record: only symbol scoping can reject this.
    ok, reason = ledger.verify_proposal_integrity(
        "XAUUSD", entry_price=1.08, stop_loss=1.07, take_profit=1.10, lot_size=0.10
    )
    return AuditResult(
        check_id="ledger_symbol_scoping",
        title="Symbol-less sizing evidence cannot authorize a specific symbol",
        passed=ok is False,
        detail=(
            "Rejected symbol-less evidence for XAUUSD."
            if ok is False
            else f"Accepted symbol-less evidence for XAUUSD: {reason}"
        ),
        metrics={"accepted": bool(ok)},
    )


async def _check_file_tools_exposed() -> AuditResult:
    from monika.application.analysis.tools.definitions.groups import ALL_TOOLS

    names = {str(t.get("name", "")) for t in ALL_TOOLS}
    required = {"read_file", "write_file", "patch"}
    missing = sorted(required - names)
    return AuditResult(
        check_id="file_tools_exposed",
        title="General-purpose file tools are reachable from the tool catalog",
        passed=not missing,
        detail="All file tools exposed." if not missing else f"Missing file tools: {', '.join(missing)}.",
        metrics={"missing": missing, "catalog_size": len(names)},
    )


async def _check_router_coding_intent() -> AuditResult:
    from monika.application.agent.chat_tool_router import ChatToolRouter
    from monika.application.analysis.tools.definitions.groups import OPERATOR_INTERACTIVE_TOOLS

    router = ChatToolRouter(OPERATOR_INTERACTIVE_TOOLS)
    query = "fix the failing pytest test in src/monika/domain/risk/risk_gate.py"
    selected = {str(t.get("name", "")) for t in router.route_tools_for_query(query)}
    file_tools = {"read_file", "write_file", "patch"}
    wrong_system_tool = "restart_mt5_service"
    passed = bool(selected & file_tools) and wrong_system_tool not in selected
    return AuditResult(
        check_id="router_coding_intent",
        title="Coding intents route to file/test tools, not MT5 system tools",
        passed=passed,
        detail=(
            f"selected_file_tools={sorted(selected & file_tools)}, selected_system_tool={wrong_system_tool in selected}"
        ),
        metrics={"selected_count": len(selected), "selected": sorted(selected)},
    )


async def _check_router_multidomain_bounded() -> AuditResult:
    from monika.application.agent.chat_tool_router import ChatToolRouter
    from monika.application.analysis.tools.definitions.groups import OPERATOR_INTERACTIVE_TOOLS

    router = ChatToolRouter(OPERATOR_INTERACTIVE_TOOLS)
    query = "analyze gold setup today with macro news and my current pnl and generate a report"
    selected_count = len(router.route_tools_for_query(query))
    catalog_size = len(OPERATOR_INTERACTIVE_TOOLS)
    return AuditResult(
        check_id="router_multidomain_bounded",
        title="Multi-domain queries never fall back to the whole tool catalog",
        passed=selected_count < catalog_size,
        detail=f"selected={selected_count}, catalog={catalog_size}",
        metrics={"selected_count": selected_count, "catalog_size": catalog_size},
    )


async def _check_prompt_macro_duplicate() -> AuditResult:
    from monika.application.agent.chat.prompt_builder import PromptBuilderMixin

    class _Probe(PromptBuilderMixin):
        def _is_macro_event_query(self, text: str) -> bool:
            return True

    probe = _Probe()
    out = probe._inject_macro_playbooks(
        "STATIC_PREFIX_SENTINEL",
        "what will the fed do at the next FOMC meeting, will they hike or cut?",
    )
    text = out if isinstance(out, str) else "\n".join(str(part) for part in out)
    counts = count_macro_duplicate_headers(text)
    return AuditResult(
        check_id="prompt_macro_duplicate",
        title="Macro playbooks are injected exactly once",
        passed=not has_macro_duplication(text),
        detail=f"header_counts={counts}, injected_chars={len(text) - len('STATIC_PREFIX_SENTINEL')}",
        metrics={"header_counts": counts, "injected_chars": len(text) - len("STATIC_PREFIX_SENTINEL")},
    )


async def _check_prompt_static_prefix_stable() -> AuditResult:
    from monika.application.agent.chat.prompt_builder import PromptBuilderMixin

    class _Probe(PromptBuilderMixin):
        def _is_macro_event_query(self, text: str) -> bool:
            return True

    probe = _Probe()
    static = "STATIC_PREFIX_SENTINEL"
    first = probe._inject_macro_playbooks((static, "DYNAMIC"), "what will the fed do at the next FOMC meeting?")
    second = probe._inject_macro_playbooks((static, "DYNAMIC"), "gold order block setup today")
    first_static = first[0] if isinstance(first, tuple) else first
    second_static = second[0] if isinstance(second, tuple) else second
    passed = first_static == static and second_static == static
    return AuditResult(
        check_id="prompt_static_prefix_stable",
        title="Query-specific skills never mutate the cacheable static prefix",
        passed=passed,
        detail=(f"static_chars=({len(first_static)},{len(second_static)}), expected={len(static)}"),
        metrics={"first_static_chars": len(first_static), "second_static_chars": len(second_static)},
    )


async def _check_skill_index_core() -> AuditResult:
    from monika.application.skills.unified_runtime import get_skills_runtime

    runtime = get_skills_runtime()
    index = runtime.get_compact_prompt_index(max_skills=15)
    required = ("risk-management-principles", "smc-ict-playbook")
    missing = [name for name in required if name not in index]
    return AuditResult(
        check_id="skill_index_core",
        title="Core trading skills are present in the compact prompt index",
        passed=not missing,
        detail="Core skills present." if not missing else f"Missing core skills: {', '.join(missing)}.",
        metrics={"missing": missing, "index_chars": len(index)},
    )


async def _check_chat_memory_budget() -> AuditResult:
    from monika.application.agent.chat.constants import MAX_HISTORY_CHARS

    token_cap = MAX_HISTORY_CHARS // 4
    target = 8000
    return AuditResult(
        check_id="chat_memory_budget",
        title="Chat history budget meets the 8k-token target",
        passed=token_cap >= target,
        detail=f"token_cap={token_cap}, target={target}, max_history_chars={MAX_HISTORY_CHARS}",
        metrics={"token_cap": token_cap, "target": target},
    )


async def _check_delegation_success_truth() -> AuditResult:
    from monika.application.analysis.subagent_spawner import SubagentSpec, SubagentWorker

    class _FailingClient:
        async def run_chat_loop(self, **kwargs: Any) -> Dict[str, Any]:
            return {"success": False, "reply": "provider quota exhausted", "error": "quota"}

    spec = SubagentSpec(
        worker_id="audit-worker",
        role="risk",
        system_prompt="audit",
        query="audit",
        tools=[],
        timeout_seconds=5.0,
    )
    result = await SubagentWorker(spec, client=_FailingClient()).run()
    return AuditResult(
        check_id="delegation_success_truth",
        title="Delegated worker failures are reported as failures",
        passed=result.success is False,
        detail=f"worker_success={result.success}, error={result.error!r}, content={result.content!r}",
        metrics={"worker_success": bool(result.success)},
    )


async def _check_mcp_write_approval() -> AuditResult:
    from types import SimpleNamespace

    from monika.application.agent.chat.streaming import StreamingMixin

    class _Probe(StreamingMixin):
        def __init__(self) -> None:
            self.tool_event_listener = None
            self.pending_calls: List[Dict[str, Any]] = []
            self._last_intercepted_pending = None

        def _create_pending_action(self, proposed: Dict[str, Any]) -> Any:
            self.pending_calls.append(proposed)
            return SimpleNamespace(action_id="audit-pending")

    class _Executor:
        def __init__(self) -> None:
            self.executed: List[str] = []

        async def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
            self.executed.append(name)
            return {"ok": True}

    probe = _Probe()
    executor = _Executor()
    probe._instrument_executor(executor)
    await executor.execute("mcp_workspace_write_file", {"path": "notes.txt", "content": "x"})
    return AuditResult(
        check_id="mcp_write_approval",
        title="MCP write tools require operator approval before execution",
        passed=bool(probe.pending_calls) and not executor.executed,
        detail=f"pending_actions={probe.pending_calls}, executed={executor.executed}",
        metrics={"pending_count": len(probe.pending_calls), "executed": executor.executed},
    )


async def _check_terminal_secret_path() -> AuditResult:
    from monika.core.security.terminal_guard import is_hardline_blocked_command

    command = "python -c \"print(open('.env').read())\""
    blocked, reason = is_hardline_blocked_command(command)
    return AuditResult(
        check_id="terminal_secret_path",
        title="Secret-file reads are denied regardless of command form",
        passed=blocked,
        detail=f"blocked={blocked}, reason={reason!r}",
        metrics={"blocked": blocked},
    )


CHECKS: tuple[Callable[[], Awaitable[AuditResult]], ...] = (
    _check_ledger_proposal_integrity,
    _check_ledger_symbolless_evidence,
    _check_file_tools_exposed,
    _check_router_coding_intent,
    _check_router_multidomain_bounded,
    _check_prompt_macro_duplicate,
    _check_prompt_static_prefix_stable,
    _check_skill_index_core,
    _check_chat_memory_budget,
    _check_delegation_success_truth,
    _check_mcp_write_approval,
    _check_terminal_secret_path,
)


async def run_harness_audit() -> AuditReport:
    """Runs every invariant probe and returns a deterministic, serializable report."""
    started = time.monotonic()
    results: List[AuditResult] = []
    for check in CHECKS:
        try:
            result = await check()
        except Exception as exc:  # audit must never abort mid-suite; failures are data
            result = AuditResult(
                check_id=getattr(check, "__name__", "unknown").removeprefix("_check_"),
                title="Check raised an exception",
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
                metrics={"error": type(exc).__name__},
            )
        results.append(result)
    elapsed_ms = round((time.monotonic() - started) * 1000.0, 2)
    return AuditReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=elapsed_ms,
        checks=results,
    )


def report_to_json(report: AuditReport) -> str:
    """Serializes an audit report for CI artifacts without leaking non-JSON values."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)


def run_harness_audit_sync() -> AuditReport:
    """Convenience entry point for CLI scripts and synchronous callers."""
    return asyncio.run(run_harness_audit())


__all__ = [
    "AUDIT_VERSION",
    "AuditReport",
    "AuditResult",
    "CHECKS",
    "count_macro_duplicate_headers",
    "has_macro_duplication",
    "report_to_json",
    "run_harness_audit",
    "run_harness_audit_sync",
]
