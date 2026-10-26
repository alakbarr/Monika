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
from typing import Any, Dict, List, Optional, Tuple

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

    @classmethod
    def extract_claim_metadata(cls, claim: Optional[Dict[str, Any]]) -> Tuple[List[float], List[str]]:
        """
        Extracts numeric price levels and falsification triggers from a claim dictionary.
        Inspects key_levels, invalidation_price, key_catalysts, core_risk_factors,
        and falsification_triggers, invalidation_trigger, Primary_Risk_Trigger.
        """
        if not claim or not isinstance(claim, dict):
            return [], []

        levels: List[float] = []
        raw_levels = claim.get("key_levels")
        if isinstance(raw_levels, (list, tuple)):
            for x in raw_levels:
                try:
                    levels.append(float(x))
                except ValueError, TypeError:
                    pass

        # Invalidation price / level
        inv_price = claim.get("invalidation_price") or claim.get("invalidation_level")
        if inv_price is not None:
            try:
                f_inv = float(inv_price)
                if f_inv not in levels:
                    levels.append(f_inv)
            except ValueError, TypeError:
                pass

        # Regex extract numbers from catalysts / risk factors / evidence if key_levels is empty
        if not levels:
            import re

            scan_texts: List[str] = []
            for k in (
                "key_catalysts",
                "core_risk_factors",
                "evidence_cited",
                "thesis",
                "bull_thesis",
                "bear_dissent",
            ):
                val = claim.get(k)
                if isinstance(val, (list, tuple)):
                    scan_texts.extend([str(item) for item in val])
                elif isinstance(val, str):
                    scan_texts.append(val)
            for txt in scan_texts:
                matches = re.findall(r"\b(?:\d{1,6}\.\d{2,5}|\d{4,6})\b", txt)
                for m in matches:
                    try:
                        f = float(m)
                        if f not in levels:
                            levels.append(f)
                    except ValueError, TypeError:
                        pass

        triggers: List[str] = []
        raw_trigs = (
            claim.get("falsification_triggers")
            or claim.get("invalidation_trigger")
            or claim.get("Primary_Risk_Trigger")
            or claim.get("primary_risk_trigger")
        )
        if isinstance(raw_trigs, (list, tuple)):
            triggers.extend([str(t) for t in raw_trigs if t])
        elif isinstance(raw_trigs, str) and raw_trigs.strip():
            triggers.append(raw_trigs.strip())

        return levels, triggers

    def add_bull_thesis(
        self,
        thesis: str,
        key_levels: Optional[List[float]] = None,
        confidence: float = 0.5,
        falsification_triggers: Optional[List[str]] = None,
        claim_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Appends concise bull claim and falsification criteria to blackboard."""
        with self._lock:
            extracted_levels, extracted_trigs = self.extract_claim_metadata(claim_dict)
            final_levels = key_levels if key_levels is not None else extracted_levels
            final_trigs = falsification_triggers if falsification_triggers is not None else extracted_trigs

            self.bull_claims.append(
                {
                    "thesis": thesis[:400],
                    "key_levels": final_levels,
                    "confidence": confidence,
                    "falsification_triggers": final_trigs,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            for trig in final_trigs:
                self.falsification_triggers.append({"side": "bull", "trigger": trig})

    def add_bear_thesis(
        self,
        thesis: str,
        key_levels: Optional[List[float]] = None,
        confidence: float = 0.5,
        falsification_triggers: Optional[List[str]] = None,
        claim_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Appends concise bear counter-claim and falsification criteria to blackboard."""
        with self._lock:
            extracted_levels, extracted_trigs = self.extract_claim_metadata(claim_dict)
            final_levels = key_levels if key_levels is not None else extracted_levels
            final_trigs = falsification_triggers if falsification_triggers is not None else extracted_trigs

            self.bear_claims.append(
                {
                    "thesis": thesis[:400],
                    "key_levels": final_levels,
                    "confidence": confidence,
                    "falsification_triggers": final_trigs,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            for trig in final_trigs:
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
