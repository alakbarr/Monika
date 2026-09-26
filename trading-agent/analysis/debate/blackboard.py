"""
S²-MAD Sparse Multi-Agent Debate Blackboard Architecture.

Replaces quadratic O(N^2) multi-turn debate transcripts with an O(N) shared structured blackboard:
1. Bull and Bear analysts read structured market facts and append concise claims (<=150 tokens).
2. Deterministic cleaner extracts direct structural contradictions without burning LLM tokens.
3. Investment Judge evaluates the clean, unified blackboard state directly.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

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
        self.contradictions: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc).isoformat()

    def add_bull_thesis(self, thesis: str, key_levels: Optional[List[float]] = None, confidence: float = 0.5) -> None:
        """Appends concise bull claim to blackboard."""
        self.bull_claims.append({
            "thesis": thesis[:400],
            "key_levels": key_levels or [],
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def add_bear_thesis(self, thesis: str, key_levels: Optional[List[float]] = None, confidence: float = 0.5) -> None:
        """Appends concise bear counter-claim to blackboard."""
        self.bear_claims.append({
            "thesis": thesis[:400],
            "key_levels": key_levels or [],
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def extract_sparse_contradictions(self) -> List[Dict[str, Any]]:
        """
        Deterministic Python extractor: Identifies direct opposing friction points
        between bull and bear claims without requiring intermediate LLM calls.
        """
        contradictions = []
        if not self.bull_claims or not self.bear_claims:
            return contradictions

        latest_bull = self.bull_claims[-1]
        latest_bear = self.bear_claims[-1]

        # 1. Directional friction
        b_conf = latest_bull.get("confidence", 0.5)
        br_conf = latest_bear.get("confidence", 0.5)
        divergence = abs(b_conf - br_conf)

        contradictions.append({
            "type": "conviction_divergence",
            "bull_confidence": b_conf,
            "bear_confidence": br_conf,
            "divergence_score": round(divergence, 2)
        })

        # 2. Structural price level conflicts
        bull_levels = set(latest_bull.get("key_levels", []))
        bear_levels = set(latest_bear.get("key_levels", []))
        level_overlap = bull_levels & bear_levels
        if level_overlap:
            contradictions.append({
                "type": "contested_price_levels",
                "levels": list(level_overlap),
                "note": "Both sides targeting identical structural levels with opposing biases."
            })

        self.contradictions = contradictions
        return contradictions

    def render_sparse_summary(self, max_tokens: int = 400) -> str:
        """
        Renders dense, telegraphic summary for the Investment Judge.
        Replaces 10k token raw debate transcript with a 250-token structured board.
        """
        latest_bull = self.bull_claims[-1]["thesis"] if self.bull_claims else "No bullish thesis"
        latest_bear = self.bear_claims[-1]["thesis"] if self.bear_claims else "No bearish counter-thesis"
        
        contradictions = self.extract_sparse_contradictions()
        
        board = (
            f"=== S²-MAD SPARSE DEBATE BLACKBOARD [{self.symbol}] ===\n"
            f"[BULL ADVOCATE THESIS]: {latest_bull}\n"
            f"[BEAR DISSENT THESIS]: {latest_bear}\n"
            f"[KEY CONTRADICTIONS]: {json.dumps(contradictions, default=str)}\n"
            f"=== END BLACKBOARD ==="
        )
        return board

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "fact_sheet": self.fact_sheet,
            "bull_claims": self.bull_claims,
            "bear_claims": self.bear_claims,
            "contradictions": self.contradictions,
            "created_at": self.created_at
        }
