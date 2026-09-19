"""
Trade Stop Gates for Trading Agent Harness.
Evaluates agent conclusions when LLM attempts to stop without tool calls.
Enforces the Verification Invariant: any directional trade recommendation
MUST be backed by verified risk/sizing evidence from VerificationEvidenceLedger.
"""

from dataclasses import dataclass
from typing import Optional
import re
import logging
from analysis.harness.verification_evidence_ledger import VerificationEvidenceLedger

logger = logging.getLogger("TradingAgent.Harness.TradeStopGate")

# Patterns indicating an explicit trade order proposal
_TRADE_PROPOSAL_PATTERNS = [
    re.compile(r'["\']action["\']\s*:\s*["\'](BUY|SELL|LONG|SHORT)["\']', re.IGNORECASE),
    re.compile(r'["\']direction["\']\s*:\s*["\'](BUY|SELL|LONG|SHORT)["\']', re.IGNORECASE),
    re.compile(r'\b(RECOMMEND|EXECUTE|PROPOSE|ORDER)\s*:\s*(BUY|SELL|LONG|SHORT)\b', re.IGNORECASE),
    re.compile(r'\b(OPEN|ENTER)\s+(BUY|SELL|LONG|SHORT)\s+POSITION\b', re.IGNORECASE),
    re.compile(r'\bDECISION\s*:\s*(BUY|SELL)\b', re.IGNORECASE),
]

_WAIT_PATTERNS = [
    re.compile(r'["\']action["\']\s*:\s*["\'](WAIT|HOLD|NEUTRAL|PASS|NO_TRADE)["\']', re.IGNORECASE),
    re.compile(r'\bDECISION\s*:\s*(WAIT|HOLD|NEUTRAL|PASS|NO_TRADE)\b', re.IGNORECASE),
    re.compile(r'\bRECOMMEND(?:ATION)?\s*:\s*(WAIT|HOLD|NEUTRAL|PASS|NO_TRADE)\b', re.IGNORECASE),
]


@dataclass
class TradeStopVerdict:
    should_stop: bool
    nudge_text: Optional[str] = None
    detected_action: Optional[str] = None
    detected_symbol: Optional[str] = None
    rejection_reason: Optional[str] = None


class TradeStopGate:
    """Evaluates whether an agent's conclusion meets verification evidence criteria."""

    @staticmethod
    def evaluate(
        text_content: str,
        ledger: VerificationEvidenceLedger,
        stage_name: str = "unknown",
        stage_symbol: Optional[str] = None,
    ) -> TradeStopVerdict:
        if not text_content:
            return TradeStopVerdict(should_stop=True)

        # Check explicit WAIT / NO_TRADE first
        for pat in _WAIT_PATTERNS:
            if pat.search(text_content):
                logger.debug(f"[{stage_name}][TradeStopGate] Detected WAIT/HOLD conclusion. Stop allowed.")
                return TradeStopVerdict(should_stop=True, detected_action="WAIT", detected_symbol=stage_symbol)

        # Check if text proposes a directional trade
        detected_action = None
        for pat in _TRADE_PROPOSAL_PATTERNS:
            match = pat.search(text_content)
            if match:
                detected_action = match.group(1).upper()
                break

        if not detected_action:
            # No explicit trade proposal detected; allow clean stop
            return TradeStopVerdict(should_stop=True)

        target_symbol = stage_symbol or "the target asset"

        # Check if ledger has passing verification evidence
        has_evidence = ledger.has_passed_evidence(stage_symbol)
        if has_evidence:
            logger.info(
                f"[{stage_name}][TradeStopGate] Trade proposal ({detected_action} {target_symbol}) "
                f"has verified risk/sizing evidence. Stop allowed."
            )
            return TradeStopVerdict(
                should_stop=True,
                detected_action=detected_action,
                detected_symbol=stage_symbol,
            )

        # BLOCKED: Trade proposed without empirical verification
        logger.warning(
            f"[{stage_name}][TradeStopGate] Trade proposal ({detected_action} {target_symbol}) "
            f"BLOCKED: No passing verification evidence recorded in this turn."
        )

        nudge_text = (
            f"[TRADE VERIFICATION STOP GATE]: You recommended a directional {detected_action} trade for {target_symbol}, "
            f"but no passing RiskGate or PositionSize verification evidence was recorded in this cycle. "
            f"You MUST call a verification tool (`calculate_position_size` or `validate_risk_limits`) now with exact "
            f"entry, stop-loss, and take-profit parameters before concluding. Unverified trade signals cannot be executed."
        )

        return TradeStopVerdict(
            should_stop=False,
            nudge_text=nudge_text,
            detected_action=detected_action,
            detected_symbol=stage_symbol,
            rejection_reason="No passing risk/sizing verification evidence recorded in ledger",
        )
