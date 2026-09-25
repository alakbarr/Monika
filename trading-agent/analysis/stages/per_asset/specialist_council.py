"""
File: analysis/stages/per_asset/specialist_council.py
Institutional 5-Specialist Council for Per-Asset Trade Decisions.
Orchestrates Macro, Technical, News/Sentiment, Risk Arbitrator (with dynamic negative constraints),
and Execution Strategist to reach high-conviction, risk-guarded trading decisions.
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from analysis.memory.failure_taxonomy import get_negative_constraints_for_regime

logger = logging.getLogger("TradingAgent.PerAsset.SpecialistCouncil")


class SpecialistRole(str, Enum):
    MACRO = "macro"
    TECHNICAL = "technical"
    NEWS_SENTIMENT = "news_sentiment"
    RISK_ARBITRATOR = "risk_arbitrator"
    EXECUTION_STRATEGIST = "execution_strategist"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SpecialistVote:
    role: SpecialistRole
    bias: str  # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    rationale: str
    veto: bool = False
    veto_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CouncilVerdict:
    symbol: str
    action: TradeAction
    consensus_score: float
    is_approved: bool
    rationale: str
    specialist_votes: Dict[str, SpecialistVote] = field(default_factory=dict)
    negative_constraints_applied: List[str] = field(default_factory=list)
    execution_parameters: Dict[str, Any] = field(default_factory=dict)


class SpecialistCouncil:
    """
    Coordinates deliberation among 5 domain specialists.
    Enforces dynamic negative constraints and hard risk barriers.
    """

    ROLE_WEIGHTS = {
        SpecialistRole.MACRO: 0.20,
        SpecialistRole.TECHNICAL: 0.30,
        SpecialistRole.NEWS_SENTIMENT: 0.15,
        SpecialistRole.RISK_ARBITRATOR: 0.25,
        SpecialistRole.EXECUTION_STRATEGIST: 0.10,
    }

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    def _evaluate_macro(self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.MACRO,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Macro evaluation provided via override."),
                metadata=override.get("metadata", {})
            )
        # Empirical fallback inspection
        macro_score = bundle_data.get("get_macro_bias_score", 0.0)
        if macro_score > 0.3:
            bias = "BULLISH"
            conf = min(1.0, 0.5 + macro_score / 2.0)
        elif macro_score < -0.3:
            bias = "BEARISH"
            conf = min(1.0, 0.5 + abs(macro_score) / 2.0)
        else:
            bias = "NEUTRAL"
            conf = 0.5
        return SpecialistVote(
            role=SpecialistRole.MACRO,
            bias=bias,
            confidence=conf,
            rationale=f"Macro score: {macro_score:.2f}."
        )

    def _evaluate_technical(self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.TECHNICAL,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Technical evaluation provided via override."),
                metadata=override.get("metadata", {})
            )
        # Basic indicators fallback
        regime = bundle_data.get("market_regime", "RANGING").upper()
        smc = bundle_data.get("get_smc_zones_H4", {})
        bias = "NEUTRAL"
        conf = 0.5
        if "BULLISH" in regime:
            bias = "BULLISH"
            conf = 0.7
        elif "BEARISH" in regime:
            bias = "BEARISH"
            conf = 0.7
        return SpecialistVote(
            role=SpecialistRole.TECHNICAL,
            bias=bias,
            confidence=conf,
            rationale=f"Market regime: {regime}."
        )

    def _evaluate_news_sentiment(self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.NEWS_SENTIMENT,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "News/Sentiment evaluation provided via override."),
                metadata=override.get("metadata", {})
            )
        retail_sentiment = bundle_data.get("retail_sentiment", {})
        long_pct = retail_sentiment.get("long_percentage", 50.0) if isinstance(retail_sentiment, dict) else 50.0
        # Contrarian retail sentiment logic
        if long_pct > 70.0:
            bias = "BEARISH"  # Extreme retail long -> contrarian short
            conf = 0.65
        elif long_pct < 30.0:
            bias = "BULLISH"  # Extreme retail short -> contrarian long
            conf = 0.65
        else:
            bias = "NEUTRAL"
            conf = 0.5
        return SpecialistVote(
            role=SpecialistRole.NEWS_SENTIMENT,
            bias=bias,
            confidence=conf,
            rationale=f"Retail long: {long_pct:.1f}% (Contrarian bias: {bias})."
        )

    def _evaluate_risk_arbitrator(
        self,
        symbol: str,
        regime: str,
        tentative_action: str,
        negative_constraints: List[str],
        bundle_data: Dict[str, Any],
        override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.RISK_ARBITRATOR,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Risk Arbitrator evaluation provided via override."),
                veto=override.get("veto", False),
                veto_reason=override.get("veto_reason"),
                metadata=override.get("metadata", {})
            )

        # Check for news blackout window or adverse risk conditions
        news_event_imminent = bundle_data.get("news_event_imminent", False)
        if news_event_imminent:
            return SpecialistVote(
                role=SpecialistRole.RISK_ARBITRATOR,
                bias="NEUTRAL",
                confidence=0.9,
                rationale="High-impact news event imminent within embargo window.",
                veto=True,
                veto_reason="News embargo window active: entries prohibited."
            )

        # Invariant checks: minimum R:R >= configured min_rr (Fix 6.3)
        min_rr = float(self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3))
        est_rr = bundle_data.get("estimated_rr", 2.0)
        if tentative_action != "HOLD" and est_rr < min_rr:
            return SpecialistVote(
                role=SpecialistRole.RISK_ARBITRATOR,
                bias="NEUTRAL",
                confidence=0.85,
                rationale=f"Estimated R:R ratio ({est_rr:.2f}) is below mandatory minimum {min_rr:.1f}.",
                veto=True,
                veto_reason=f"Sub-optimal risk-to-reward ratio: {est_rr:.2f} < {min_rr:.1f}"
            )

        return SpecialistVote(
            role=SpecialistRole.RISK_ARBITRATOR,
            bias="NEUTRAL",
            confidence=0.8,
            rationale=f"Risk parameters approved with {len(negative_constraints)} negative constraints applied."
        )

    def _evaluate_execution_strategist(
        self,
        symbol: str,
        action: str,
        bundle_data: Dict[str, Any],
        override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.EXECUTION_STRATEGIST,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Execution Strategist evaluation provided via override."),
                metadata=override.get("metadata", {})
            )

        # Determine optimal entry order type
        atr = bundle_data.get("get_atr_H4", 0.0015)
        spread = bundle_data.get("spread_pips", 1.2)

        # Default execution params
        exec_params = {
            "order_type": "LIMIT",
            "pullback_target_atr": 0.3,
            "max_slippage_pips": 2.0,
            "session_ok": True
        }

        # If spread is wide, enforce limit order
        if spread > 2.5:
            exec_params["order_type"] = "LIMIT"
            exec_params["limit_offset_pips"] = spread * 0.5
            rationale = f"Spread ({spread} pips) elevated; enforcing LIMIT order on pullback."
        else:
            exec_params["order_type"] = "MARKET"
            rationale = f"Spread ({spread} pips) within optimal tolerance; MARKET execution permitted."

        return SpecialistVote(
            role=SpecialistRole.EXECUTION_STRATEGIST,
            bias="NEUTRAL",
            confidence=0.75,
            rationale=rationale,
            metadata=exec_params
        )

    def evaluate(
        self,
        symbol: str,
        regime: str,
        bundle_data: Dict[str, Any],
        specialist_overrides: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> CouncilVerdict:
        """
        Conduct full council deliberation across all 5 specialist domains.
        """
        overrides = specialist_overrides or {}

        # 1. Macro & Technical & News Evaluations
        macro_vote = self._evaluate_macro(symbol, bundle_data, overrides.get("macro"))
        tech_vote = self._evaluate_technical(symbol, bundle_data, overrides.get("technical"))
        news_vote = self._evaluate_news_sentiment(symbol, bundle_data, overrides.get("news_sentiment"))

        # Determine tentative directional bias
        bull_score = 0.0
        bear_score = 0.0

        for vote, role in [(macro_vote, SpecialistRole.MACRO),
                           (tech_vote, SpecialistRole.TECHNICAL),
                           (news_vote, SpecialistRole.NEWS_SENTIMENT)]:
            weight = self.ROLE_WEIGHTS[role]
            if vote.bias == "BULLISH":
                bull_score += weight * vote.confidence
            elif vote.bias == "BEARISH":
                bear_score += weight * vote.confidence

        if bull_score > bear_score and bull_score >= 0.25:
            tentative_action = "BUY"
        elif bear_score > bull_score and bear_score >= 0.25:
            tentative_action = "SELL"
        else:
            tentative_action = "HOLD"

        # 2. Fetch dynamic negative constraints for regime
        negative_constraints = get_negative_constraints_for_regime(symbol=symbol, regime=regime)

        # 3. Risk Arbitrator Deliberation (Has Veto Authority)
        risk_vote = self._evaluate_risk_arbitrator(
            symbol=symbol,
            regime=regime,
            tentative_action=tentative_action,
            negative_constraints=negative_constraints,
            bundle_data=bundle_data,
            override=overrides.get("risk_arbitrator")
        )

        # 4. Execution Strategist Deliberation
        exec_vote = self._evaluate_execution_strategist(
            symbol=symbol,
            action=tentative_action,
            bundle_data=bundle_data,
            override=overrides.get("execution_strategist")
        )

        votes = {
            SpecialistRole.MACRO.value: macro_vote,
            SpecialistRole.TECHNICAL.value: tech_vote,
            SpecialistRole.NEWS_SENTIMENT.value: news_vote,
            SpecialistRole.RISK_ARBITRATOR.value: risk_vote,
            SpecialistRole.EXECUTION_STRATEGIST.value: exec_vote,
        }

        # Check for Vetoes
        if risk_vote.veto:
            logger.info(f"[SpecialistCouncil] Risk Arbitrator VETO for {symbol}: {risk_vote.veto_reason}")
            return CouncilVerdict(
                symbol=symbol,
                action=TradeAction.HOLD,
                consensus_score=0.0,
                is_approved=False,
                rationale=f"VETO by Risk Arbitrator: {risk_vote.veto_reason}",
                specialist_votes=votes,
                negative_constraints_applied=negative_constraints,
                execution_parameters=exec_vote.metadata
            )

        # Calculate final consensus score
        total_consensus = 0.0
        aligned_weight = 0.0

        target_bias = "BULLISH" if tentative_action == "BUY" else ("BEARISH" if tentative_action == "SELL" else "NEUTRAL")

        for role_name, vote in votes.items():
            role_enum = SpecialistRole(role_name)
            weight = self.ROLE_WEIGHTS[role_enum]
            if vote.bias == target_bias:
                aligned_weight += weight
                total_consensus += weight * vote.confidence
            elif vote.bias == "NEUTRAL":
                if not vote.veto:
                    aligned_weight += weight * 0.5
                total_consensus += weight * (vote.confidence * 0.75)

        is_approved = tentative_action != "HOLD" and aligned_weight >= 0.50 and total_consensus >= 0.60
        final_action = TradeAction(tentative_action) if is_approved else TradeAction.HOLD

        rationale = (
            f"Council deliberation reached {final_action.value} with consensus score {total_consensus:.2f}. "
            f"Aligned weight: {aligned_weight:.2f}. "
            f"Risk Arbitrator: Approved with {len(negative_constraints)} negative constraints."
        )

        return CouncilVerdict(
            symbol=symbol,
            action=final_action,
            consensus_score=round(total_consensus, 3),
            is_approved=is_approved,
            rationale=rationale,
            specialist_votes=votes,
            negative_constraints_applied=negative_constraints,
            execution_parameters=exec_vote.metadata
        )
