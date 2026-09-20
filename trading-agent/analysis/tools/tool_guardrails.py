# ==============================================================================
# File: analysis/tools/tool_guardrails.py
# ==============================================================================

"""
Unified Tool Guardrail Controller.

Consolidates tool execution safety guardrails into an independent controller layer
shared between the autonomous AgentHarness and interactive ChatAgent.

Key Protections:
1. ToolCallSignature: Deterministic hashing of tool_name + sorted_args to detect and suppress infinite loop repetitions (>2-3 identical calls).
2. MonotonicRiskGuard: Prohibits downstream execution if the cycle has already registered a risk denial or kill-switch activation.
3. ReadBeforeActGuard: Mandates that market/technical data must be retrieved prior to generating trade submissions.
4. MandatorySizingGuard: Verifies position sizing and lot parameters prior to order dispatch.
5. CategoryTurnCapGuard: Enforces per-category call quotas (macro, news, sentiment, technical, execution).
"""

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

logger = logging.getLogger("TradingAgent.ToolGuardrails")


# Category mapping for tools
DATA_READ_TOOLS: Set[str] = {
    "get_price_history", "get_technical_indicators", "get_atr",
    "get_swing_points", "get_structure_breaks", "get_smc_zones",
    "get_fibonacci_levels", "get_optimal_intraday_levels", "get_daily_range_context",
    "get_news_items", "get_news_digest", "get_retail_sentiment",
    "get_funding_rate", "get_fear_greed_index", "get_forex_sentiment",
    "get_fxssi_sentiment", "get_structured_sentiment", "get_dxy", "get_vix",
    "get_fedwatch_probabilities", "get_yield_data", "get_cot_report",
    "get_economic_calendar", "get_account_info", "get_open_positions", "get_trade_history",
    "get_active_triggers", "get_system_health", "get_paper_trading_performance",
    "get_verified_market_snapshot", "get_market_quote", "get_ohlcv", "get_rate", "get_tick", "get_candles",
    "inspect_database_schema", "read_database_records",
}

DATABASE_IMMUTABLE_TABLES: Set[str] = {
    "activity_log",
    "token_usage_log",
    "order_events",
    "trading_events",
    "telegram_conversations",
    "orders_log",
}

TERMINAL_ACTION_TOOLS: Set[str] = {
    "submit_asset_analysis", "submit_fundamental_brief",
}

TOOL_CATEGORIES: Dict[str, List[str]] = {
    "macro": [
        "get_dxy", "get_vix", "get_fedwatch_probabilities",
        "get_yield_data", "get_cot_report", "get_economic_calendar",
    ],
    "news": [
        "get_news_items", "get_news_digest", "search_financial_news",
    ],
    "sentiment": [
        "get_retail_sentiment", "get_funding_rate", "get_fear_greed_index",
        "get_forex_sentiment", "get_fxssi_sentiment", "get_structured_sentiment",
    ],
    "technical": [
        "get_price_history", "get_technical_indicators", "get_atr",
        "get_swing_points", "get_structure_breaks", "get_smc_zones",
        "get_fibonacci_levels", "get_optimal_intraday_levels", "get_daily_range_context",
        "get_verified_market_snapshot", "get_market_quote", "get_chart",
    ],
    "order": [
        "submit_asset_analysis", "place_order", "propose_action",
        "modify_position", "close_position",
    ],
    "database": [
        "inspect_database_schema", "read_database_records",
    ],
}


@dataclass(frozen=True)
class GuardrailVerdict:
    """Hasil evaluasi guardrail terhadap sebuah panggilan tool."""
    allowed: bool
    guard_name: str
    reason: str
    action: str = "allow"             # 'allow', 'suppress', 'reject', 'nudge'
    suggested_fix: Optional[str] = None
    modified_args: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        return self.allowed


class ToolCallSignature:
    """Helper untuk hashing deterministik nama dan argumen tool."""

    @staticmethod
    def compute(tool_name: str, tool_input: Any) -> str:
        try:
            if isinstance(tool_input, dict):
                sig_args = json.dumps(tool_input, sort_keys=True, default=str)
            else:
                sig_args = str(tool_input)
        except Exception:
            sig_args = str(tool_input)
        
        md5_hash = hashlib.md5(sig_args.encode("utf-8")).hexdigest()
        return f"{tool_name}:{md5_hash}"


class BatchCycleGuard:
    """Mendeteksi perulangan siklus pemanggilan tool multi-langkah (periode 2 s/d 4: A->B->A->B)."""

    def __init__(self, max_period: int = 4, history_len: int = 32):
        self.max_period = max_period
        self._history: deque[str] = deque(maxlen=history_len)

    def record(self, sig: str) -> None:
        self._history.append(sig)

    def detect_cycle(self) -> Optional[tuple[int, int]]:
        """Mengembalikan (period, laps) jika siklus berulang >= 2 lap penuh (3x putaran)."""
        n = len(self._history)
        for period in range(2, self.max_period + 1):
            if n < period * 3:
                continue
            laps = 1
            while True:
                base = n - period * (laps + 1)
                if base < 0:
                    break
                is_equal = all(
                    self._history[base + i] == self._history[n - period + i]
                    for i in range(period)
                )
                if not is_equal:
                    break
                laps += 1
            if laps >= 3:
                return period, laps
        return None

    def reset(self) -> None:
        self._history.clear()


class AntiOscillationGuard:
    """Mendeteksi dan menekan perulangan panggilan tool identik serta siklus multi-tool bergantian."""

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._history: deque[str] = deque(maxlen=window_size)
        self._counts: Dict[str, int] = {}
        self._last_sig: Optional[str] = None
        self._consecutive_count: int = 0
        self._batch_cycle_guard = BatchCycleGuard(max_period=4, history_len=32)

    def evaluate(self, sig: str, tool_name: str) -> GuardrailVerdict:
        # 1. Deteksi siklus bergantian (A->B->A->B)
        cycle = self._batch_cycle_guard.detect_cycle()
        if cycle:
            period, laps = cycle
            return GuardrailVerdict(
                allowed=False,
                guard_name="AntiOscillationGuard",
                reason=(
                    f"Multi-step batch cycle loop detected (period={period}, repeated {laps} laps). "
                    f"Agent is alternating between tools without advancing analysis. "
                    f"Do not cycle calls. Conclude analysis immediately."
                ),
                action="suppress",
                suggested_fix="Synthesize existing observation and conclude analysis.",
            )

        if sig == self._last_sig:
            self._consecutive_count += 1
        else:
            self._last_sig = sig
            self._consecutive_count = 1

        recent_count = self._history.count(sig)
        total_count = self._counts.get(sig, 0) + 1

        if self._consecutive_count >= 2 or recent_count >= 2 or total_count >= 3:
            return GuardrailVerdict(
                allowed=False,
                guard_name="AntiOscillationGuard",
                reason=(
                    f"Tool '{tool_name}' with identical parameters was already executed "
                    f"(consecutive={self._consecutive_count}, recent={recent_count}, total={total_count}). "
                    f"Do not repeat identical calls. Synthesize collected data and conclude."
                ),
                action="suppress",
                suggested_fix="Synthesize existing observation without repeating call.",
            )

        return GuardrailVerdict(allowed=True, guard_name="AntiOscillationGuard", reason="OK")

    def record(self, sig: str) -> None:
        self._history.append(sig)
        self._counts[sig] = self._counts.get(sig, 0) + 1
        self._batch_cycle_guard.record(sig)

    def reset(self) -> None:
        self._history.clear()
        self._counts.clear()
        self._last_sig = None
        self._consecutive_count = 0
        self._batch_cycle_guard.reset()


class MonotonicRiskGuard:
    """Memblokir tindakan eksekusi jika status risiko sistem telah menandai penolakan/pause."""

    def evaluate(self, tool_name: str, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> GuardrailVerdict:
        ctx = context or {}
        is_risk_denied = bool(ctx.get("risk_denied") or ctx.get("is_risk_denied"))
        is_trading_paused = bool(ctx.get("trading_paused") or ctx.get("system_paused") or ctx.get("kill_switch"))

        # Cek apakah tool mencoba melakukan transaksi aktif
        is_active_order = False
        if tool_name == "submit_asset_analysis":
            decision = str(args.get("decision") or "").lower().strip()
            if decision in ("buy", "sell"):
                is_active_order = True
        elif tool_name in ("place_order", "propose_action"):
            act_type = str(args.get("action_type") or args.get("action") or "").lower().strip()
            if act_type in ("place_order", "buy", "sell", ""):
                is_active_order = True

        if is_active_order:
            if is_trading_paused:
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="MonotonicRiskGuard",
                    reason="Trading system is currently PAUSED or under circuit breaker. Order proposals are strictly blocked.",
                    action="reject",
                )
            if is_risk_denied:
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="MonotonicRiskGuard",
                    reason="RiskGate has already monotonic-denied trade execution for this cycle. Active order blocked.",
                    action="reject",
                )

        return GuardrailVerdict(allowed=True, guard_name="MonotonicRiskGuard", reason="OK")


class ReadBeforeActGuard:
    """Memastikan agen membaca data pasar/teknikal sebelum menyerahkan kesimpulan analisis atau order."""

    def __init__(self):
        self._read_tools_called: Set[str] = set()

    def record_call(self, tool_name: str) -> None:
        if (
            tool_name in DATA_READ_TOOLS
            or tool_name.startswith(("get_", "read_", "query_", "fetch_", "search_"))
        ) and tool_name not in TERMINAL_ACTION_TOOLS:
            self._read_tools_called.add(tool_name)

    def evaluate(self, tool_name: str, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> GuardrailVerdict:
        if tool_name in TERMINAL_ACTION_TOOLS:
            # Pengecualian jika keputusan hanya 'avoid' atau 'wait'
            decision = str(args.get("decision") or args.get("action") or "").lower().strip()
            if decision in ("avoid", "wait") and len(self._read_tools_called) > 0:
                return GuardrailVerdict(allowed=True, guard_name="ReadBeforeActGuard", reason="OK")

            if len(self._read_tools_called) == 0:
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="ReadBeforeActGuard",
                    reason=(
                        f"Action '{tool_name}' invoked without any prior market/technical data reads. "
                        f"You MUST query real-time data (e.g. get_price_history, get_open_positions, get_atr) "
                        f"before submitting analysis or proposing trades."
                    ),
                    action="nudge",
                    suggested_fix="Call a market data tool first before taking action.",
                )

        return GuardrailVerdict(allowed=True, guard_name="ReadBeforeActGuard", reason="OK")

    def reset(self) -> None:
        self._read_tools_called.clear()


class MandatorySizingGuard:
    """Memastikan parameter ukuran lot atau kalkulasi sizing valid saat mengajukan order."""

    def evaluate(self, tool_name: str, args: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> GuardrailVerdict:
        if tool_name == "place_order":
            params = args.get("params") or args
            lots = params.get("lot_size") or params.get("lots")
            risk_pct = params.get("risk_percent") or params.get("risk_pct")

            # If both are missing or zero
            if lots is None and risk_pct is None:
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="MandatorySizingGuard",
                    reason="Order proposal lacks mandatory position sizing parameters ('lot_size' or 'risk_percent').",
                    action="reject",
                    suggested_fix="Specify valid lot_size (>0.01) or risk_percent (e.g. 1.0%).",
                )
            if lots is not None:
                try:
                    lot_val = float(lots)
                    if lot_val <= 0:
                        return GuardrailVerdict(
                            allowed=False,
                            guard_name="MandatorySizingGuard",
                            reason=f"Invalid lot_size {lot_val}: must be strictly positive.",
                            action="reject",
                        )
                except (ValueError, TypeError):
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="MandatorySizingGuard",
                        reason=f"Malformed lot_size: {lots}",
                        action="reject",
                    )
        elif tool_name == "propose_action":
            params = args.get("params") or args
            lots = params.get("lot_size") or params.get("lots")
            if lots is not None:
                try:
                    lot_val = float(lots)
                    if lot_val <= 0:
                        return GuardrailVerdict(
                            allowed=False,
                            guard_name="MandatorySizingGuard",
                            reason=f"Invalid lot_size {lot_val}: must be strictly positive.",
                            action="reject",
                        )
                except (ValueError, TypeError):
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="MandatorySizingGuard",
                        reason=f"Malformed lot_size: {lots}",
                        action="reject",
                    )

        return GuardrailVerdict(allowed=True, guard_name="MandatorySizingGuard", reason="OK")


class CategoryTurnCapGuard:
    """Membatasi frekuensi pemanggilan tool per kategori dalam satu giliran."""

    def __init__(self, caps: Optional[Dict[str, int]] = None):
        self.caps = caps or {
            "macro": 15,
            "news": 15,
            "sentiment": 15,
            "technical": 25,
            "order": 10,
        }
        self._category_counts: Dict[str, int] = {k: 0 for k in self.caps}

    def _get_category(self, tool_name: str) -> Optional[str]:
        for cat, tools in TOOL_CATEGORIES.items():
            if tool_name in tools:
                return cat
        return None

    def evaluate(self, tool_name: str) -> GuardrailVerdict:
        cat = self._get_category(tool_name)
        if cat and cat in self.caps:
            current = self._category_counts.get(cat, 0)
            max_allowed = self.caps[cat]
            if current >= max_allowed:
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="CategoryTurnCapGuard",
                    reason=f"Turn quota exceeded for '{cat}' tools ({current}/{max_allowed}). Proceed to synthesis.",
                    action="suppress",
                )
        return GuardrailVerdict(allowed=True, guard_name="CategoryTurnCapGuard", reason="OK")

    def record_call(self, tool_name: str) -> None:
        cat = self._get_category(tool_name)
        if cat and cat in self._category_counts:
            self._category_counts[cat] = self._category_counts.get(cat, 0) + 1

    def reset(self) -> None:
        for k in self._category_counts:
            self._category_counts[k] = 0


class DenialCircuitBreakerGuard:
    """
    Tracks consecutive rejections or guardrail denials within a cycle.
    If the agent triggers threshold (default: 3) consecutive rejections without an advancing successful step,
    it trips the circuit breaker to force a WAIT decision and prevent oscillation.
    """

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._consecutive_denials: int = 0
        self._is_tripped: bool = False

    def evaluate(self, tool_name: str) -> GuardrailVerdict:
        if self._is_tripped:
            return GuardrailVerdict(
                allowed=False,
                guard_name="DenialCircuitBreakerGuard",
                reason=(
                    f"Circuit breaker tripped after {self.threshold} consecutive denials/rejections. "
                    f"Further tool calls for '{tool_name}' are blocked. Finalize analysis with WAIT verdict."
                ),
                action="reject",
                suggested_fix="Conclude analysis cycle and submit WAIT verdict.",
            )
        return GuardrailVerdict(allowed=True, guard_name="DenialCircuitBreakerGuard", reason="OK")

    def record_denial(self) -> bool:
        """Record a denial/rejection event. Returns True if breaker just tripped."""
        self._consecutive_denials += 1
        if self._consecutive_denials >= self.threshold:
            self._is_tripped = True
            logger.warning(
                f"[DenialCircuitBreakerGuard] Tripped: {self._consecutive_denials} consecutive rejections reached."
            )
            return True
        return False

    def record_success(self) -> None:
        """Reset consecutive denials upon successful action."""
        self._consecutive_denials = 0

    def reset(self) -> None:
        self._consecutive_denials = 0
        self._is_tripped = False


class ToolGuardrailController:
    """
    Unified Tool Guardrail Controller.
    Mengorkestrasi seluruh guard keselamatan tool untuk AgentHarness dan ChatAgent.
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.anti_oscillation = AntiOscillationGuard()
        self.monotonic_risk = MonotonicRiskGuard()
        self.read_before_act = ReadBeforeActGuard()
        self.mandatory_sizing = MandatorySizingGuard()
        self.category_turn_cap = CategoryTurnCapGuard()
        self.denial_breaker = DenialCircuitBreakerGuard(
            threshold=int(self.settings.get("denial_breaker_threshold", 3))
        )

    def record_denial(self) -> bool:
        """Record an external or internal denial/rejection event."""
        return self.denial_breaker.record_denial()

    def record_success(self) -> None:
        """Record a successful advancing tool execution."""
        self.denial_breaker.record_success()

    def validate_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailVerdict:
        """
        Validasi menyeluruh panggilan tool sebelum dieksekusi.
        Evaluasi guard dilakukan secara sekuensial.
        """
        # -1. Denial Circuit Breaker Guard (Hard stop if threshold tripped)
        v_breaker = self.denial_breaker.evaluate(tool_name)
        if not v_breaker.allowed:
            logger.warning(f"[Guardrails] BLOCKED by {v_breaker.guard_name}: {v_breaker.reason}")
            return v_breaker

        # 0. Database Access & Mutation Guard
        if tool_name in ("inspect_database_schema", "read_database_records"):
            if context and not context.get("is_admin", False):
                return GuardrailVerdict(
                    allowed=False,
                    guard_name="AdminOnlyGuard",
                    reason=f"Tool '{tool_name}' is strictly restricted to Admin.",
                    action="reject",
                )

        if tool_name == "propose_action":
            action_type = args.get("action_type")
            params = args.get("params") or {}
            if action_type == "db_mutation":
                if context and not context.get("is_admin", False):
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="AdminOnlyGuard",
                        reason="Database mutation proposals are strictly restricted to Admin.",
                        action="reject",
                    )
                table_name = str(params.get("table_name", "")).strip().lower()
                op = str(params.get("operation", "")).strip().lower()
                if table_name in DATABASE_IMMUTABLE_TABLES:
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="ImmutableTableGuard",
                        reason=f"Table '{table_name}' is an immutable audit trail and cannot be modified or deleted.",
                        action="reject",
                    )
                if op not in ("insert", "update", "delete"):
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="ValidOperationGuard",
                        reason=f"Unsupported database operation '{op}'. Supported: insert, update, delete.",
                        action="reject",
                    )
                if op in ("update", "delete") and not params.get("target_id"):
                    return GuardrailVerdict(
                        allowed=False,
                        guard_name="TargetIdRequiredGuard",
                        reason=f"Operation '{op}' on table '{table_name}' requires explicit 'target_id'.",
                        action="reject",
                    )

        # 1. Monotonic Risk Guard
        v_risk = self.monotonic_risk.evaluate(tool_name, args, context)
        if not v_risk.allowed:
            logger.warning(f"[Guardrails] BLOCKED by {v_risk.guard_name}: {v_risk.reason}")
            return v_risk

        # 2. Category Turn Cap Guard
        v_cap = self.category_turn_cap.evaluate(tool_name)
        if not v_cap.allowed:
            logger.warning(f"[Guardrails] BLOCKED by {v_cap.guard_name}: {v_cap.reason}")
            return v_cap

        # 3. Read Before Act Guard
        v_read = self.read_before_act.evaluate(tool_name, args, context)
        if not v_read.allowed:
            logger.warning(f"[Guardrails] BLOCKED by {v_read.guard_name}: {v_read.reason}")
            return v_read

        # 4. Mandatory Sizing Guard
        v_size = self.mandatory_sizing.evaluate(tool_name, args, context)
        if not v_size.allowed:
            logger.warning(f"[Guardrails] BLOCKED by {v_size.guard_name}: {v_size.reason}")
            return v_size

        # 5. Anti-Oscillation Guard
        sig = ToolCallSignature.compute(tool_name, args)
        v_osc = self.anti_oscillation.evaluate(sig, tool_name)
        if not v_osc.allowed:
            logger.warning(f"[Guardrails] SUPPRESSED by {v_osc.guard_name}: {v_osc.reason}")
            return v_osc

        return GuardrailVerdict(allowed=True, guard_name="AllGuards", reason="Passed all guardrails")

    def record_tool_call(self, tool_name: str, args: Dict[str, Any], result: Any = None) -> None:
        """Catat eksekusi tool untuk memperbarui state pembacaan dan penghitungan kuota."""
        sig = ToolCallSignature.compute(tool_name, args)
        self.anti_oscillation.record(sig)
        self.read_before_act.record_call(tool_name)
        self.category_turn_cap.record_call(tool_name)

    def reset_turn(self) -> None:
        """Reset per-turn counters."""
        self.category_turn_cap.reset()

    def reset_all(self) -> None:
        """Reset seluruh guard (misal: siklus baru dimulai)."""
        self.anti_oscillation.reset()
        self.read_before_act.reset()
        self.category_turn_cap.reset()
