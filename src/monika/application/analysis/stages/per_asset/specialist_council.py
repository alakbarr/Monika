"""
File: analysis/stages/per_asset/specialist_council.py
Institutional 5-Specialist Council for Per-Asset Trade Decisions.
Orchestrates Macro, Technical, News/Sentiment, Risk Arbitrator (with dynamic negative constraints),
and Execution Strategist to reach high-conviction, risk-guarded trading decisions.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from monika.application.analysis.memory.failure_taxonomy import get_negative_constraints_for_regime

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
    synergy_state: str = "neutral_or_mixed"
    consensus_summary: Dict[str, Any] = field(default_factory=dict)


def _normalize_specialist_bias(raw_bias: Any) -> str:
    """Normalize a specialist vote or string bias into 'bullish', 'bearish', or 'neutral'."""
    if isinstance(raw_bias, SpecialistVote):
        raw_str = str(raw_bias.bias or "").lower().strip()
    elif isinstance(raw_bias, dict):
        raw_str = str(raw_bias.get("directional_bias") or raw_bias.get("bias") or "").lower().strip()
    else:
        raw_str = str(raw_bias or "").lower().strip()
    if raw_str in ("bullish", "strong_bullish", "buy", "long"):
        return "bullish"
    if raw_str in ("bearish", "strong_bearish", "sell", "short"):
        return "bearish"
    return "neutral"


def format_specialist_consensus_summary(summary: Dict[str, Any]) -> str:
    """Format human-readable specialist consensus summary highlighting synergy vs crowding."""
    biases = summary.get("biases", {})
    t_b = str(biases.get("technical", "neutral")).upper()
    m_b = str(biases.get("macro", "neutral")).upper()
    s_b = str(biases.get("sentiment", "neutral")).upper()
    synergy = str(summary.get("synergy_state", "neutral_or_mixed"))
    dom = str(summary.get("dominant_bias", "neutral")).upper()

    if synergy == "uncrowded_institutional_synergy":
        badge = "UNCROWDED_INSTITUTIONAL_SYNERGY"
        guidance = (
            f"High-Conviction Institutional Synergy ({dom}): Technical & Macro align ({t_b}) "
            f"while Sentiment remains uncrowded ({s_b})."
        )
    elif synergy == "crowded_unanimous_exhaustion":
        badge = "CROWDED_3_OF_3_CAUTION"
        guidance = (
            f"Crowded 3-of-3 Caution ({dom}): Technical, Macro, and Sentiment are unanimously {t_b}. "
            f"Guard against late-stage trend exhaustion."
        )
    elif synergy == "technical_macro_conflict":
        badge = "TECHNICAL_MACRO_CONFLICT"
        guidance = f"Direct Institutional Conflict: Technical ({t_b}) opposes Macro ({m_b})."
    else:
        badge = "NEUTRAL_OR_MIXED_CONSENSUS"
        guidance = f"Mixed/Neutral Specialist Posture: Technical={t_b}, Macro={m_b}, Sentiment={s_b}."

    return (
        f"[SPECIALIST SYNERGY STATE: {badge} | consensus={summary.get('consensus')} | "
        f"synergy_state={synergy}] {guidance}"
    )


def compute_specialist_consensus_summary(
    biases: Dict[str, Any],
    dealing_range_pos: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute specialist consensus and institutional synergy classification.

     Classifications for `synergy_state`:
      - 'uncrowded_institutional_synergy': technical and macro agree ('bullish' or 'bearish')
        AND sentiment is NOT in that same direction ('neutral' or opposite).
      - 'crowded_unanimous_exhaustion': all 3 (technical, macro, sentiment) are identical ('bullish' or 'bearish').
      - 'technical_macro_conflict': technical and macro are both non-neutral and opposite.
      - 'neutral_or_mixed': any other combination.
    """
    src = biases.get("biases") if isinstance(biases, dict) and isinstance(biases.get("biases"), dict) else biases
    if not isinstance(src, dict):
        src = {}

    tech_b = _normalize_specialist_bias(src.get("technical"))
    macro_b = _normalize_specialist_bias(src.get("macro"))
    sent_raw = src.get("sentiment") if "sentiment" in src else src.get("news_sentiment")
    sent_b = _normalize_specialist_bias(sent_raw)

    triple = (tech_b, macro_b, sent_b)
    bull_count = sum(1 for b in triple if b == "bullish")
    bear_count = sum(1 for b in triple if b == "bearish")

    unanimous = tech_b in ("bullish", "bearish") and tech_b == macro_b == sent_b
    majority = bull_count >= 2 or bear_count >= 2

    if tech_b in ("bullish", "bearish") and tech_b == macro_b:
        dominant_bias = tech_b
        if sent_b != tech_b:
            synergy_state = "uncrowded_institutional_synergy"
            consensus_label = "majority_agreement"
        else:
            synergy_state = "crowded_unanimous_exhaustion"
            consensus_label = "unanimous_agreement"
    elif tech_b in ("bullish", "bearish") and macro_b in ("bullish", "bearish") and tech_b != macro_b:
        synergy_state = "technical_macro_conflict"
        if bull_count >= 2:
            dominant_bias = "bullish"
            consensus_label = "majority_agreement"
        elif bear_count >= 2:
            dominant_bias = "bearish"
            consensus_label = "majority_agreement"
        else:
            dominant_bias = "neutral"
            consensus_label = "split_conflict"
    else:
        synergy_state = "neutral_or_mixed"
        if bull_count >= 2:
            dominant_bias = "bullish"
            consensus_label = "majority_agreement"
        elif bear_count >= 2:
            dominant_bias = "bearish"
            consensus_label = "majority_agreement"
        else:
            dominant_bias = (
                tech_b
                if tech_b in ("bullish", "bearish")
                else (macro_b if macro_b in ("bullish", "bearish") else "neutral")
            )
            consensus_label = "no_consensus"

    summary: Dict[str, Any] = {
        "consensus": consensus_label,
        "unanimous_agreement": unanimous,
        "majority_agreement": majority,
        "synergy_state": synergy_state,
        "dominant_bias": dominant_bias,
        "dominant_direction": dominant_bias,
        "biases": {
            "technical": tech_b,
            "macro": macro_b,
            "sentiment": sent_b,
        },
        "dealing_range_pos": dealing_range_pos,
    }
    summary["formatted_summary"] = format_specialist_consensus_summary(summary)
    return summary


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

    def _evaluate_macro(
        self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.MACRO,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Macro evaluation provided via override."),
                metadata=override.get("metadata", {}),
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
            role=SpecialistRole.MACRO, bias=bias, confidence=conf, rationale=f"Macro score: {macro_score:.2f}."
        )

    def _evaluate_technical(
        self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.TECHNICAL,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Technical evaluation provided via override."),
                metadata=override.get("metadata", {}),
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
            role=SpecialistRole.TECHNICAL, bias=bias, confidence=conf, rationale=f"Market regime: {regime}."
        )

    def _evaluate_news_sentiment(
        self, symbol: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.NEWS_SENTIMENT,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "News/Sentiment evaluation provided via override."),
                metadata=override.get("metadata", {}),
            )
        retail_sentiment = bundle_data.get("retail_sentiment", {})
        long_pct = retail_sentiment.get("long_percentage", 50.0) if isinstance(retail_sentiment, dict) else 50.0

        # Trend momentum check: during explosive impulse (ADX > 32), retail crowding can represent trend continuation
        adx_val = 0.0
        tech_ind = bundle_data.get("get_technical_indicators_H4") or bundle_data.get("get_technical_indicators") or {}
        if isinstance(tech_ind, dict):
            try:
                adx_val = float(tech_ind.get("adx_14", 0.0) or tech_ind.get("adx", 0.0) or 0.0)
            except ValueError, TypeError:
                adx_val = 0.0

        # Contrarian retail sentiment logic with trend exhaustion guard
        if adx_val > 25.0 and 28.0 < long_pct < 72.0:
            bias = "NEUTRAL"
            conf = 0.55
            rationale_str = f"Retail long: {long_pct:.1f}%, but ADX={adx_val:.1f} indicates strong trend impulse (contrarian penalty suspended)."
        elif long_pct >= 72.0:
            bias = "BEARISH"  # Extreme retail long in non-trending -> contrarian short
            conf = 0.65
            rationale_str = f"Retail long: {long_pct:.1f}% (Contrarian bias: BEARISH)."
        elif long_pct <= 28.0:
            bias = "BULLISH"  # Extreme retail short in non-trending -> contrarian long
            conf = 0.65
            rationale_str = f"Retail long: {long_pct:.1f}% (Contrarian bias: BULLISH)."
        else:
            bias = "NEUTRAL"
            conf = 0.5
            rationale_str = f"Retail long: {long_pct:.1f}% (Balanced sentiment)."

        return SpecialistVote(
            role=SpecialistRole.NEWS_SENTIMENT,
            bias=bias,
            confidence=conf,
            rationale=rationale_str,
        )

    def _evaluate_risk_arbitrator(
        self,
        symbol: str,
        regime: str,
        tentative_action: str,
        negative_constraints: List[str],
        bundle_data: Dict[str, Any],
        override: Optional[Dict[str, Any]] = None,
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.RISK_ARBITRATOR,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Risk Arbitrator evaluation provided via override."),
                veto=override.get("veto", False),
                veto_reason=override.get("veto_reason"),
                metadata=override.get("metadata", {}),
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
                veto_reason="News embargo window active: entries prohibited.",
            )

        # Invariant checks: minimum R:R >= configured min_rr (Fix 6.3)
        min_rr = float(self.settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.5))
        est_rr = bundle_data.get("estimated_rr", 2.0)
        if tentative_action != "HOLD" and est_rr < min_rr:
            return SpecialistVote(
                role=SpecialistRole.RISK_ARBITRATOR,
                bias="NEUTRAL",
                confidence=0.85,
                rationale=f"Estimated R:R ratio ({est_rr:.2f}) is below mandatory minimum {min_rr:.1f}.",
                veto=True,
                veto_reason=f"Sub-optimal risk-to-reward ratio: {est_rr:.2f} < {min_rr:.1f}",
            )

        return SpecialistVote(
            role=SpecialistRole.RISK_ARBITRATOR,
            bias="NEUTRAL",
            confidence=0.8,
            rationale=f"Risk parameters approved with {len(negative_constraints)} negative constraints applied.",
        )

    def _evaluate_execution_strategist(
        self, symbol: str, action: str, bundle_data: Dict[str, Any], override: Optional[Dict[str, Any]] = None
    ) -> SpecialistVote:
        if override:
            return SpecialistVote(
                role=SpecialistRole.EXECUTION_STRATEGIST,
                bias=override.get("bias", "NEUTRAL").upper(),
                confidence=float(override.get("confidence", 0.5)),
                rationale=override.get("rationale", "Execution Strategist evaluation provided via override."),
                metadata=override.get("metadata", {}),
            )

        # Determine optimal entry order type
        atr = bundle_data.get("get_atr_H4", 0.0015)
        spread = bundle_data.get("spread_pips", 1.2)

        # Default execution params
        exec_params = {"order_type": "LIMIT", "pullback_target_atr": 0.3, "max_slippage_pips": 2.0, "session_ok": True}

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
            metadata=exec_params,
        )

    def evaluate(
        self,
        symbol: str,
        regime: str,
        bundle_data: Dict[str, Any],
        specialist_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
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

        for vote, role in [
            (macro_vote, SpecialistRole.MACRO),
            (tech_vote, SpecialistRole.TECHNICAL),
            (news_vote, SpecialistRole.NEWS_SENTIMENT),
        ]:
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
            override=overrides.get("risk_arbitrator"),
        )

        # 4. Execution Strategist Deliberation
        exec_vote = self._evaluate_execution_strategist(
            symbol=symbol,
            action=tentative_action,
            bundle_data=bundle_data,
            override=overrides.get("execution_strategist"),
        )

        votes = {
            SpecialistRole.MACRO.value: macro_vote,
            SpecialistRole.TECHNICAL.value: tech_vote,
            SpecialistRole.NEWS_SENTIMENT.value: news_vote,
            SpecialistRole.RISK_ARBITRATOR.value: risk_vote,
            SpecialistRole.EXECUTION_STRATEGIST.value: exec_vote,
        }

        consensus_summary = compute_specialist_consensus_summary(
            {
                "technical": tech_vote.bias,
                "macro": macro_vote.bias,
                "sentiment": news_vote.bias,
            },
            dealing_range_pos=bundle_data.get("dealing_range_pos") if isinstance(bundle_data, dict) else None,
        )
        synergy_state = str(consensus_summary.get("synergy_state", "neutral_or_mixed"))
        exec_params_out = dict(exec_vote.metadata)
        exec_params_out["synergy_state"] = synergy_state
        exec_params_out["consensus"] = consensus_summary.get("consensus")

        # Check for Vetoes
        if risk_vote.veto:
            logger.info(f"[SpecialistCouncil] Risk Arbitrator VETO for {symbol}: {risk_vote.veto_reason}")
            return CouncilVerdict(
                symbol=symbol,
                action=TradeAction.HOLD,
                consensus_score=0.0,
                is_approved=False,
                rationale=f"VETO by Risk Arbitrator: {risk_vote.veto_reason} | {consensus_summary['formatted_summary']}",
                specialist_votes=votes,
                negative_constraints_applied=negative_constraints,
                execution_parameters=exec_params_out,
                synergy_state=synergy_state,
                consensus_summary=consensus_summary,
            )

        # Calculate final consensus score
        total_consensus = 0.0
        aligned_weight = 0.0

        target_bias = (
            "BULLISH" if tentative_action == "BUY" else ("BEARISH" if tentative_action == "SELL" else "NEUTRAL")
        )

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
            f"Risk Arbitrator: Approved with {len(negative_constraints)} negative constraints. "
            f"{consensus_summary['formatted_summary']}"
        )

        return CouncilVerdict(
            symbol=symbol,
            action=final_action,
            consensus_score=round(total_consensus, 3),
            is_approved=is_approved,
            rationale=rationale,
            specialist_votes=votes,
            negative_constraints_applied=negative_constraints,
            execution_parameters=exec_params_out,
            synergy_state=synergy_state,
            consensus_summary=consensus_summary,
        )

    @staticmethod
    def summarize_consensus(
        biases: Dict[str, Any],
        dealing_range_pos: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Expose consensus summary dictionary with synergy_state and formatted_summary."""
        return compute_specialist_consensus_summary(biases=biases, dealing_range_pos=dealing_range_pos)
