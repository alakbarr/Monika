"""
DAG-based Scenario Tree for Multi-Hypothesis Trading Analysis.

Replaces single-thesis analysis with a 3-branch scenario tree:
- Bull Branch: Breakout/continuation thesis
- Bear Branch: Reversal/distribution thesis
- Chop Branch: Range-bound/mean-reversion thesis

Each branch is evaluated independently and converged into an Expected Value (EV) decision.
"""

import uuid
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.ScenarioTree")


@dataclass
class ScenarioNode:
    """Single node in the Scenario DAG."""
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_uuid: Optional[str] = None
    node_type: str = "root"  # root, bull, bear, chop, convergence
    symbol: str = ""
    thesis: str = ""
    catalysts: List[str] = field(default_factory=list)
    invalidation_level: float = 0.0
    invalidation_condition: str = ""
    target_level: float = 0.0
    reward_risk_ratio: float = 0.0
    probability: float = 0.0
    confidence: float = 0.0
    entry_plan: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: List[str] = field(default_factory=list)


@dataclass
class ScenarioTree:
    """Complete multi-hypothesis scenario tree for a symbol."""
    symbol: str
    root: ScenarioNode = field(default_factory=ScenarioNode)
    branches: Dict[str, ScenarioNode] = field(default_factory=dict)
    convergence: Optional[ScenarioNode] = None
    expected_value: float = 0.0
    final_decision: str = "WAIT"  # BUY, SELL, WAIT

    def serialize_jsonl(self) -> str:
        """Serializes scenario tree to Pi-compatible JSONL DAG format."""
        lines = [json.dumps(asdict(self.root))]
        for branch in self.branches.values():
            lines.append(json.dumps(asdict(branch)))
        if self.convergence:
            lines.append(json.dumps(asdict(self.convergence)))
        return "\n".join(lines)


class ScenarioTreeEngine:
    """Generates, evaluates, and converges scenario trees for trading assets."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        st_cfg = self.settings.get("scenario_tree", {})
        self.ev_threshold: float = float(st_cfg.get("ev_threshold", 1.3) or 1.3)
        self.min_dominant_prob: float = float(st_cfg.get("min_dominant_prob", 0.45) or 0.45)

    @staticmethod
    def compute_empirical_probabilities(
        d1_trend: str,
        macro_bias: str,
        confluence_score: int = 8,
        spread_drift: float = 1.0,
        rsi: Optional[float] = None,
        timesfm_skew: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Computes dynamic empirical branch probabilities (Bull, Bear, Chop)
        using logistic multi-factor scaling based on technical indicators and spread dynamics.
        Replaces static 0.55/0.40/0.25 heuristics (Phase 5).
        """
        trend = (d1_trend or "").upper()
        macro = (macro_bias or "").upper()
        
        # Base logit scores for bull, bear, chop
        bull_logit = 0.0
        bear_logit = 0.0
        chop_logit = 0.0

        # 1. Trend alignment
        if trend == "BULLISH":
            bull_logit += 0.85
            bear_logit -= 0.85
        elif trend == "BEARISH":
            bear_logit += 0.85
            bull_logit -= 0.85
        else:
            chop_logit += 0.5

        # 2. Macro bias alignment
        if macro == "BULLISH":
            bull_logit += 0.65
            bear_logit -= 0.65
        elif macro == "BEARISH":
            bear_logit += 0.65
            bull_logit -= 0.65
        else:
            chop_logit += 0.3

        # 3. Confluence score scaling (baseline 7)
        conf_factor = (max(0, min(14, confluence_score)) - 7) * 0.12
        if bull_logit > bear_logit:
            bull_logit += conf_factor
        elif bear_logit > bull_logit:
            bear_logit += conf_factor

        # 4. Spread dynamics (Spread Drift Ratio = current_spread / median_spread)
        # If spread expands (drift > 1.0), execution drag increases and chop/mean-reversion probability rises
        if spread_drift > 1.0:
            drift_penalty = min(1.0, (spread_drift - 1.0) * 0.5)
            chop_logit += drift_penalty
            bull_logit -= drift_penalty * 0.5
            bear_logit -= drift_penalty * 0.5

        # 5. Optional RSI momentum
        if rsi is not None:
            if rsi > 60:
                bull_logit += 0.25
            elif rsi < 40:
                bear_logit += 0.25
            elif 45 <= rsi <= 55:
                chop_logit += 0.2

        # 6. Optional TimesFM quantile skew
        if timesfm_skew is not None:
            if timesfm_skew > 0.15:
                bull_logit += 0.3
            elif timesfm_skew < -0.15:
                bear_logit += 0.3

        # Softmax normalization
        import math
        exp_bull = math.exp(max(-10.0, min(10.0, bull_logit)))
        exp_bear = math.exp(max(-10.0, min(10.0, bear_logit)))
        exp_chop = math.exp(max(-10.0, min(10.0, chop_logit)))
        total_exp = exp_bull + exp_bear + exp_chop

        # Format rounded to 2 decimals ensuring all non-negative and sum == 1.0
        p_b = round(exp_bull / total_exp, 2)
        p_be = round(exp_bear / total_exp, 2)
        p_ch = round(max(0.01, 1.0 - (p_b + p_be)), 2)
        if p_b + p_be + p_ch != 1.0 or p_ch < 0.01:
            p_ch = 0.01
            if p_b >= p_be:
                p_b = round(1.0 - p_be - p_ch, 2)
            else:
                p_be = round(1.0 - p_b - p_ch, 2)

        return {"bull": p_b, "bear": p_be, "chop": p_ch}

    def create_deterministic_tree(
        self,
        symbol: str,
        current_price: float,
        d1_trend: str = "BULLISH",
        atr_14: float = 0.0050,
        macro_bias: str = "BULLISH",
        confluence_score: int = 8,
        spread_drift: float = 1.0,
        rsi: Optional[float] = None,
        timesfm_skew: Optional[float] = None,
        **kwargs
    ) -> ScenarioTree:
        """
        Builds a deterministic 3-branch scenario tree from market context and indicators.
        Probabilities are calculated dynamically using compute_empirical_probabilities.
        """
        tree = ScenarioTree(symbol=symbol)
        
        # 1. Root context node
        tree.root = ScenarioNode(
            node_type="root",
            symbol=symbol,
            thesis=f"Market Structure Context for {symbol} at {current_price:.5f}",
            evidence=[
                f"D1 Trend: {d1_trend}",
                f"Macro Bias: {macro_bias}",
                f"ATR(14): {atr_14:.5f}"
            ]
        )

        probs = self.compute_empirical_probabilities(
            d1_trend=d1_trend,
            macro_bias=macro_bias,
            confluence_score=confluence_score,
            spread_drift=spread_drift,
            rsi=rsi,
            timesfm_skew=timesfm_skew
        )
        bull_prob = probs["bull"]
        bear_prob = probs["bear"]
        chop_prob = probs["chop"]

        # 2. Bull Scenario (Breakout / SMC Bullish OB)
        bull_sl = current_price - (atr_14 * 1.2)
        bull_tp = current_price + (atr_14 * 2.4)
        bull_rr = (bull_tp - current_price) / max(current_price - bull_sl, 1e-5)

        bull_node = ScenarioNode(
            node_type="bull",
            symbol=symbol,
            parent_uuid=tree.root.uuid,
            thesis=f"Bullish continuation above {current_price:.5f} targeting FVG/Liquidity at {bull_tp:.5f}",
            invalidation_level=bull_sl,
            invalidation_condition=f"D1 candle closes below {bull_sl:.5f}",
            target_level=bull_tp,
            reward_risk_ratio=round(bull_rr, 2),
            probability=bull_prob,
            confidence=0.75,
            entry_plan={"action": "BUY", "entry": current_price, "sl": bull_sl, "tp": bull_tp}
        )
        tree.branches["bull"] = bull_node

        # 3. Bear Scenario (Distribution / Liquidity Sweep Reversal)
        bear_sl = current_price + (atr_14 * 1.2)
        bear_tp = current_price - (atr_14 * 2.4)
        bear_rr = (current_price - bear_tp) / max(bear_sl - current_price, 1e-5)

        bear_node = ScenarioNode(
            node_type="bear",
            symbol=symbol,
            parent_uuid=tree.root.uuid,
            thesis=f"Bearish rejection from supply zone at {current_price:.5f} targeting {bear_tp:.5f}",
            invalidation_level=bear_sl,
            invalidation_condition=f"D1 candle closes above {bear_sl:.5f}",
            target_level=bear_tp,
            reward_risk_ratio=round(bear_rr, 2),
            probability=bear_prob,
            confidence=0.70,
            entry_plan={"action": "SELL", "entry": current_price, "sl": bear_sl, "tp": bear_tp}
        )
        tree.branches["bear"] = bear_node

        # 4. Chop / Range Scenario (Mean-Reversion)
        chop_node = ScenarioNode(
            node_type="chop",
            symbol=symbol,
            parent_uuid=tree.root.uuid,
            thesis=f"Consolidation inside {bull_sl:.5f} - {bear_sl:.5f} range. Avoid high-risk breakout entries.",
            invalidation_level=bull_sl,
            invalidation_condition="High-volume momentum breakout",
            target_level=current_price,
            reward_risk_ratio=1.0,
            probability=chop_prob,
            confidence=0.60
        )
        tree.branches["chop"] = chop_node

        # 5. Convergence & Expected Value Calculation
        # EV = P(Bull)*RR(Bull) - P(Bear)*1.0 (for long) OR P(Bear)*RR(Bear) - P(Bull)*1.0 (for short)
        ev_bull = (bull_node.probability * bull_node.reward_risk_ratio) - (bear_node.probability * 1.0)
        ev_bear = (bear_node.probability * bear_node.reward_risk_ratio) - (bull_node.probability * 1.0)

        if ev_bull > ev_bear and ev_bull >= self.ev_threshold and bull_node.probability >= self.min_dominant_prob:
            tree.expected_value = round(ev_bull, 2)
            tree.final_decision = "BUY"
        elif ev_bear > ev_bull and ev_bear >= self.ev_threshold and bear_node.probability >= self.min_dominant_prob:
            tree.expected_value = round(ev_bear, 2)
            tree.final_decision = "SELL"
        else:
            tree.expected_value = round(max(ev_bull, ev_bear, 0.0), 2)
            tree.final_decision = "WAIT"

        tree.convergence = ScenarioNode(
            node_type="convergence",
            symbol=symbol,
            parent_uuid=tree.root.uuid,
            thesis=f"Scenario Convergence -> EV={tree.expected_value:.2f}, Decision={tree.final_decision}"
        )

        return tree
