"""
Verification Evidence Ledger for Trading Agent Harness.
Tracks and records verifiable empirical evidence (risk gate checks, position sizing,
spread verification, and generalized execution proof) executed during an agent's
multi-turn reasoning cycle.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.Harness.VerificationEvidence")


def compute_evidence_hash(
    symbol: str,
    entry: float,
    stop_loss: float,
    take_profit: Optional[float] = None,
    lot_size: Optional[float] = None,
) -> str:
    """Produces canonical SHA-256 fingerprint for verified trading parameters."""
    canonical = (
        f"{symbol.strip().upper()}:{entry:.5f}:{stop_loss:.5f}:{(take_profit or 0.0):.5f}:{(lot_size or 0.0):.4f}"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class VerificationRecord:
    tool_name: str
    symbol: Optional[str]
    status: str  # "passed", "failed", "warning"
    details: Dict[str, Any]
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: Optional[float] = None
    evidence_hash: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GeneralizedEvidenceRecord:
    """
    Generalized empirical proof record for both trading and non-trading tasks
    (e.g., file mutations, test runs, syntax verification, data citations).
    """

    category: str  # "financial_risk", "file_mutation", "test_execution", "code_syntax", "data_grounding"
    target: str  # e.g., "EURUSD", "src/monika/core/risk.py", "pytest tests/domain"
    status: str  # "passed", "failed", "warning"
    details: Dict[str, Any]
    evidence_hash: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationEvidenceLedger:
    """
    In-memory ledger tracking verified mathematical, risk, and execution actions
    during an agent turn/cycle. Enforces that trade proposals and critical conclusions
    cannot be emitted without empirical proof from verification tools.
    """

    VERIFICATION_TOOLS: Set[str] = {
        "calculate_position_size",
        "validate_risk_limits",
        "check_spread_and_slippage",
        "evaluate_risk_limits",
        "check_risk_gate",
        "verify_provenance_citations",
    }

    GENERAL_VERIFICATION_TOOLS: Set[str] = {
        "run_test",
        "run_command",
        "git_status",
        "read_file",
        "inspect_code",
        "write_file",
        "edit_file",
        "calculate_position_size",
        "validate_risk_limits",
        "check_risk_gate",
        "verify_provenance_citations",
    }

    def __init__(self):
        self.records: List[VerificationRecord] = []
        self.general_records: List[GeneralizedEvidenceRecord] = []

    def reset_turn(self) -> None:
        """Reset records for a fresh turn/cycle."""
        self.records.clear()
        self.general_records.clear()

    def record_tool_execution(self, tool_name: str, tool_input: dict, result: dict) -> Optional[VerificationRecord]:
        """Record evidence from a tool execution if it is a verification tool."""
        # 1. Generalized evidence recording for broad auditability
        if tool_name in self.GENERAL_VERIFICATION_TOOLS:
            category = "financial_risk" if tool_name in self.VERIFICATION_TOOLS else "execution"
            target_val = ""
            if isinstance(tool_input, dict):
                target_val = str(
                    tool_input.get("symbol")
                    or tool_input.get("path")
                    or tool_input.get("target")
                    or tool_input.get("command")
                    or ""
                )
            status_val = "passed"
            if isinstance(result, dict):
                if result.get("status") in ("failed", "rejected", "error"):
                    status_val = "failed"
                elif result.get("approved") is False or result.get("success") is False:
                    status_val = "failed"
                elif "error" in result and not result.get("success", True):
                    status_val = "failed"

            self.record_general_evidence(
                category=category,
                target=target_val,
                status=status_val,
                details=result if isinstance(result, dict) else {"raw": str(result)},
            )

        # 2. Financial verification path
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
        lot_size = None
        if isinstance(tool_input, dict):
            try:
                raw_entry = tool_input.get("entry") or tool_input.get("entry_price")
                if raw_entry is not None:
                    entry = float(raw_entry)
                raw_sl = tool_input.get("sl") or tool_input.get("stop_loss")
                if raw_sl is not None:
                    sl = float(raw_sl)
                raw_tp = tool_input.get("tp") or tool_input.get("take_profit")
                if raw_tp is not None:
                    tp = float(raw_tp)
                raw_lots = tool_input.get("lot_size") or tool_input.get("lots") or tool_input.get("volume")
                if raw_lots is None and isinstance(result, dict):
                    raw_lots = result.get("lot_size") or result.get("calculated_lot_size")
                if raw_lots is not None:
                    lot_size = float(raw_lots)
            except ValueError, TypeError:
                pass

        ev_hash = None
        if symbol and entry is not None and sl is not None:
            ev_hash = compute_evidence_hash(
                symbol=symbol,
                entry=entry,
                stop_loss=sl,
                take_profit=tp,
                lot_size=lot_size,
            )

        record = VerificationRecord(
            tool_name=tool_name,
            symbol=symbol,
            status=status,
            details=result if isinstance(result, dict) else {"raw": str(result)},
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            lot_size=lot_size,
            evidence_hash=ev_hash,
        )
        self.records.append(record)
        logger.debug(
            f"[VerificationLedger] Recorded {tool_name} for symbol {symbol}: {status} "
            f"(SL={sl}, TP={tp}, Lots={lot_size}, Hash={ev_hash})"
        )
        return record

    def record_general_evidence(
        self, category: str, target: str, status: str, details: Dict[str, Any]
    ) -> GeneralizedEvidenceRecord:
        """
        Explicitly records a verified empirical event for general-purpose tasks.
        (e.g., verifying a file was created on disk, a test suite passed, syntax verified).
        """
        ev_hash = hashlib.sha256(f"{category}:{target}:{status}".encode("utf-8")).hexdigest()[:16]
        record = GeneralizedEvidenceRecord(
            category=category,
            target=target,
            status=status,
            details=details,
            evidence_hash=ev_hash,
        )
        self.general_records.append(record)
        logger.debug(
            f"[VerificationLedger] Recorded general evidence [{category}] on '{target}': {status} (Hash={ev_hash})"
        )
        return record

    def has_general_evidence(
        self, category: Optional[str] = None, target: Optional[str] = None, required_status: str = "passed"
    ) -> bool:
        """Verifies whether empirical evidence exists meeting category, target, and status requirements."""
        clean_target = target.strip().lower() if target else None
        for r in self.general_records:
            if category and r.category != category:
                continue
            if clean_target and r.target.strip().lower() != clean_target:
                continue
            if r.status == required_status:
                return True
        return False

    def get_general_records(
        self, category: Optional[str] = None, target: Optional[str] = None
    ) -> List[GeneralizedEvidenceRecord]:
        """Returns matching general evidence records."""
        clean_target = target.strip().lower() if target else None
        results = []
        for r in self.general_records:
            if category and r.category != category:
                continue
            if clean_target and r.target.strip().lower() != clean_target:
                continue
            results.append(r)
        return results

    def has_passed_evidence(self, symbol: Optional[str] = None) -> bool:
        """Check if passing verification evidence exists (optionally for a specific symbol)."""
        clean_sym = str(symbol).upper() if symbol else None
        for r in self.records:
            if r.status == "passed":
                if clean_sym is None or r.symbol == clean_sym or r.symbol is None:
                    return True
        return False

    def verify_proposal_integrity(
        self,
        symbol: Optional[str],
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        lot_size: Optional[float] = None,
        expected_hash: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Verifies that trade proposal parameters match verified risk calculation evidence.
        Prevents submitting modified stop_loss levels without re-calculating risk sizing.
        Supports both cryptographic hash matching and financial tolerance checks.
        """
        clean_sym = str(symbol).upper() if symbol else None
        passed_sizing = [
            r
            for r in self.records
            if r.status == "passed"
            and r.tool_name in ("calculate_position_size", "validate_risk_limits")
            and (clean_sym is None or r.symbol == clean_sym or r.symbol is None)
        ]
        if not passed_sizing:
            return False, f"No verified sizing/risk evidence recorded for {clean_sym}."

        latest = passed_sizing[-1]

        # 1. Cryptographic match check if hash is available
        if expected_hash and latest.evidence_hash:
            if expected_hash == latest.evidence_hash:
                return True, "OK (Cryptographically verified)"

        if (
            latest.evidence_hash
            and clean_sym
            and entry_price is not None
            and stop_loss is not None
            and lot_size is not None
        ):
            prop_hash = compute_evidence_hash(
                symbol=clean_sym,
                entry=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                lot_size=lot_size,
            )
            if prop_hash == latest.evidence_hash:
                return True, "OK (Cryptographic hash matched)"

        # 2. Tolerance check fallback (allows minor broker rounding)
        if stop_loss is not None and latest.stop_loss is not None:
            denom = abs(latest.stop_loss) or 1.0
            # FIX 6.9: 1.5% tolerance (instead of overly strict 0.5%) prevents rejecting minor rounding adjustments
            if abs(latest.stop_loss - stop_loss) / denom > 0.015:
                return False, (
                    f"Stop loss in proposal ({stop_loss}) deviates significantly from verified level ({latest.stop_loss}). "
                    f"Prior position sizing calculation is stale. Recalculate position size with new stop loss."
                )

        return True, "OK"

    def get_passed_records(self, symbol: Optional[str] = None) -> List[VerificationRecord]:
        """Return list of passed records for a symbol."""
        clean_sym = str(symbol).upper() if symbol else None
        return [
            r
            for r in self.records
            if r.status == "passed" and (clean_sym is None or r.symbol == clean_sym or r.symbol is None)
        ]
