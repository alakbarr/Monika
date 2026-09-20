"""
Verification Evidence Ledger for Trading Agent Harness.
Tracks and records verifiable empirical evidence (risk gate checks, position sizing,
spread verification) executed during an agent's multi-turn reasoning cycle.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
import logging

logger = logging.getLogger("TradingAgent.Harness.VerificationEvidence")


@dataclass
class VerificationRecord:
    tool_name: str
    symbol: Optional[str]
    status: str  # "passed", "failed", "warning"
    details: Dict[str, Any]
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationEvidenceLedger:
    """
    In-memory ledger tracking verified mathematical and risk actions during an agent turn/cycle.
    Enforces that trade proposals cannot be emitted without empirical proof from verification tools.
    """

    VERIFICATION_TOOLS: Set[str] = {
        "calculate_position_size",
        "validate_risk_limits",
        "check_spread_and_slippage",
        "evaluate_risk_limits",
        "check_risk_gate",
        "verify_provenance_citations",
    }

    def __init__(self):
        self.records: List[VerificationRecord] = []

    def reset_turn(self) -> None:
        """Reset records for a fresh turn/cycle."""
        self.records.clear()

    def record_tool_execution(self, tool_name: str, tool_input: dict, result: dict) -> Optional[VerificationRecord]:
        """Record evidence from a tool execution if it is a verification tool."""
        if tool_name not in self.VERIFICATION_TOOLS:
            return None

        symbol = None
        if isinstance(tool_input, dict):
            symbol = tool_input.get("symbol")
        if not symbol and isinstance(result, dict):
            symbol = result.get("symbol")
        if symbol:
            symbol = str(symbol).upper()

        status = "passed"
        if isinstance(result, dict):
            if result.get("status") in ("failed", "rejected", "error"):
                status = "failed"
            elif result.get("approved") is False:
                status = "failed"
            elif "error" in result and not result.get("success", True):
                status = "failed"

        # Extract numerical parameters if available
        entry = None
        sl = None
        tp = None
        if isinstance(tool_input, dict):
            try:
                if "entry" in tool_input or "entry_price" in tool_input:
                    entry = float(tool_input.get("entry") or tool_input.get("entry_price"))
                if "sl" in tool_input or "stop_loss" in tool_input:
                    sl = float(tool_input.get("sl") or tool_input.get("stop_loss"))
                if "tp" in tool_input or "take_profit" in tool_input:
                    tp = float(tool_input.get("tp") or tool_input.get("take_profit"))
            except (ValueError, TypeError):
                pass

        record = VerificationRecord(
            tool_name=tool_name,
            symbol=symbol,
            status=status,
            details=result if isinstance(result, dict) else {"raw": str(result)},
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
        )
        self.records.append(record)
        logger.debug(f"[VerificationLedger] Recorded {tool_name} for symbol {symbol}: {status} (SL={sl}, TP={tp})")
        return record

    def has_passed_evidence(self, symbol: Optional[str] = None) -> bool:
        """Check if passing verification evidence exists (optionally for a specific symbol)."""
        clean_sym = str(symbol).upper() if symbol else None
        for r in self.records:
            if r.status == "passed":
                if clean_sym is None or r.symbol == clean_sym or r.symbol is None:
                    return True
        return False

    def verify_proposal_integrity(
        self, symbol: Optional[str], entry_price: Optional[float] = None, stop_loss: Optional[float] = None
    ) -> tuple[bool, str]:
        """
        Verifies that trade proposal parameters match verified risk calculation evidence.
        Prevents submitting modified stop_loss levels without re-calculating risk sizing.
        """
        clean_sym = str(symbol).upper() if symbol else None
        passed_sizing = [
            r for r in self.records
            if r.status == "passed" and r.tool_name in ("calculate_position_size", "validate_risk_limits")
            and (clean_sym is None or r.symbol == clean_sym or r.symbol is None)
        ]
        if not passed_sizing:
            return False, f"No verified sizing/risk evidence recorded for {clean_sym}."

        latest = passed_sizing[-1]
        if stop_loss is not None and latest.stop_loss is not None:
            denom = abs(latest.stop_loss) or 1.0
            if abs(latest.stop_loss - stop_loss) / denom > 0.005:  # >0.5% tolerance
                return False, (
                    f"Stop loss in proposal ({stop_loss}) deviates significantly from verified level ({latest.stop_loss}). "
                    f"Prior position sizing calculation is stale. Recalculate position size with new stop loss."
                )

        return True, "OK"

    def get_passed_records(self, symbol: Optional[str] = None) -> List[VerificationRecord]:
        """Return list of passed records for a symbol."""
        clean_sym = str(symbol).upper() if symbol else None
        return [
            r for r in self.records
            if r.status == "passed" and (clean_sym is None or r.symbol == clean_sym or r.symbol is None)
        ]
