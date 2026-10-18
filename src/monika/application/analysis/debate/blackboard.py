"""
S²-MAD Sparse Multi-Agent Debate Blackboard Architecture.

Replaces quadratic O(N^2) multi-turn debate transcripts with an O(N) shared structured blackboard:
1. Bull and Bear analysts read structured market facts and append concise claims (<=150 tokens).
2. Deterministic cleaner extracts direct structural contradictions without burning LLM tokens.
3. Investment Judge evaluates the clean, unified blackboard state directly.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Debate.Blackboard")


class DebateBlackboard:
    """
    Central structured blackboard for adversarial multi-agent debate.
    """

    def __init__(self, symbol: str, fact_sheet: Optional[dict] = None):
        self.symbol = symbol.upper().replace("/", "")
        self.fact_sheet = fact_sheet or {}
        self.bull_claims: List[Dict[str, Any]] = []
        self.bear_claims: List[Dict[str, Any]] = []
        self.falsification_triggers: List[Dict[str, Any]] = []
        self.contradictions: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._lock = threading.RLock()

    def add_bull_thesis(
        self,
        thesis: str,
        key_levels: Optional[List[float]] = None,
        confidence: float = 0.5,
        falsification_triggers: Optional[List[str]] = None,
    ) -> None:
        """Appends concise bull claim and falsification criteria to blackboard."""
        with self._lock:
            triggers = falsification_triggers or []
            self.bull_claims.append(
                {
                    "thesis": thesis[:400],
                    "key_levels": key_levels or [],
                    "confidence": confidence,
                    "falsification_triggers": triggers,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            for trig in triggers:
                self.falsification_triggers.append({"side": "bull", "trigger": trig})

    def add_bear_thesis(
        self,
        thesis: str,
        key_levels: Optional[List[float]] = None,
        confidence: float = 0.5,
        falsification_triggers: Optional[List[str]] = None,
    ) -> None:
        """Appends concise bear counter-claim and falsification criteria to blackboard."""
        with self._lock:
            triggers = falsification_triggers or []
            self.bear_claims.append(
                {
                    "thesis": thesis[:400],
                    "key_levels": key_levels or [],
                    "confidence": confidence,
                    "falsification_triggers": triggers,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            for trig in triggers:
                self.falsification_triggers.append({"side": "bear", "trigger": trig})

    def extract_sparse_contradictions(self) -> List[Dict[str, Any]]:
        """
        Deterministic Python extractor: Identifies direct opposing friction points
        between bull and bear claims without requiring intermediate LLM calls.
        """
        with self._lock:
            return self._extract_sparse_contradictions_locked()

    def _extract_sparse_contradictions_locked(self) -> List[Dict[str, Any]]:
        contradictions = []
        if not self.bull_claims or not self.bear_claims:
            return contradictions

        latest_bull = self.bull_claims[-1]
        latest_bear = self.bear_claims[-1]

        # 1. Directional friction
        b_conf = latest_bull.get("confidence", 0.5)
        br_conf = latest_bear.get("confidence", 0.5)
        divergence = abs(b_conf - br_conf)

        contradictions.append(
            {
                "type": "conviction_divergence",
                "bull_confidence": b_conf,
                "bear_confidence": br_conf,
                "divergence_score": round(divergence, 2),
            }
        )

        # 2. Structural price level conflicts with pip distance tolerance
        raw_bull_lvls = latest_bull.get("key_levels", []) or []
        raw_bear_lvls = latest_bear.get("key_levels", []) or []

        bull_levels = []
        for lvl in raw_bull_lvls:
            try:
                bull_levels.append(float(lvl))
            except ValueError, TypeError:
                pass

        bear_levels = []
        for lvl in raw_bear_lvls:
            try:
                bear_levels.append(float(lvl))
            except ValueError, TypeError:
                pass

        pip_size = 0.0001
        sym = self.symbol.upper()
        if "JPY" in sym:
            pip_size = 0.01
        elif "XAU" in sym or "GOLD" in sym:
            pip_size = 0.10
        elif "BTC" in sym or "ETH" in sym:
            pip_size = 1.0
        elif "XBR" in sym or "OIL" in sym:
            pip_size = 0.01

        threshold = 2.0 * pip_size
        contested_pairs = []
        matched_bear_indices = set()
        for bl in bull_levels:
            for idx, brl in enumerate(bear_levels):
                if idx not in matched_bear_indices and abs(bl - brl) <= threshold:
                    matched_bear_indices.add(idx)
                    contested_pairs.append(
                        {
                            "bull_level": bl,
                            "bear_level": brl,
                            "mid_point": round((bl + brl) / 2.0, 5),
                        }
                    )
                    break

        if contested_pairs:
            contradictions.append(
                {
                    "type": "contested_price_levels",
                    "contested_zones": contested_pairs,
                    "levels": [p["mid_point"] for p in contested_pairs],
                    "note": "Both sides targeting identical structural zones with opposing biases.",
                }
            )

        self.contradictions = contradictions
        return contradictions

    def render_sparse_summary(self, max_tokens: int = 400) -> str:
        """
        Renders dense, telegraphic summary for the Investment Judge.
        Replaces 10k token raw debate transcript with a 250-token structured board.
        """
        with self._lock:
            latest_bull = self.bull_claims[-1]["thesis"] if self.bull_claims else "No bullish thesis"
            latest_bear = self.bear_claims[-1]["thesis"] if self.bear_claims else "No bearish counter-thesis"

            contradictions = self._extract_sparse_contradictions_locked()

            triggers_summary = (
                "\n".join(f"  - [{t['side'].upper()}]: {t['trigger']}" for t in self.falsification_triggers)
                if self.falsification_triggers
                else "None specified"
            )

            board = (
                f"=== S²-MAD SPARSE DEBATE BLACKBOARD [{self.symbol}] ===\n"
                f"[BULL ADVOCATE THESIS]: {latest_bull}\n"
                f"[BEAR DISSENT THESIS]: {latest_bear}\n"
                f"[FALSIFICATION TRIGGERS]:\n{triggers_summary}\n"
                f"[KEY CONTRADICTIONS]: {json.dumps(contradictions, default=str)}\n"
                f"=== END BLACKBOARD ==="
            )
            return board

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "symbol": self.symbol,
                "fact_sheet": dict(self.fact_sheet),
                "bull_claims": list(self.bull_claims),
                "bear_claims": list(self.bear_claims),
                "falsification_triggers": list(self.falsification_triggers),
                "contradictions": list(self.contradictions),
                "created_at": self.created_at,
            }
