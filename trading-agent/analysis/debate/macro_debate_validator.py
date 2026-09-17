import logging
from typing import Dict, Any, List

logger = logging.getLogger("TradingAgent.MacroDebateValidator")

WINNER_MAPPING = {
    "BULL": "RISK_ON_USD_BEAR",
    "RISK_ON": "RISK_ON_USD_BEAR",
    "RISK_ON_USD_BEAR": "RISK_ON_USD_BEAR",
    "BEAR": "RISK_OFF_USD_BULL",
    "RISK_OFF": "RISK_OFF_USD_BULL",
    "RISK_OFF_USD_BULL": "RISK_OFF_USD_BULL",
    "TIE": "TIE",
    "NEUTRAL": "TIE",
}

LEGACY_WINNER_MAPPING = {
    "RISK_ON_USD_BEAR": "BULL",
    "RISK_OFF_USD_BULL": "BEAR",
    "TIE": "TIE",
}


def normalize_winner(winner_raw: str) -> str:
    """Normalize raw winner string to standard canonical representation."""
    if not winner_raw:
        return "TIE"
    key = str(winner_raw).strip().upper()
    return WINNER_MAPPING.get(key, "TIE")


def validate_macro_judge_output(
    judge_result: Dict[str, Any],
    bull_claim: Any = None,
    bear_claim: Any = None
) -> Dict[str, Any]:
    """
    Validates Macro Judge output for internal coherence, schema compliance,
    and semantic consistency between winner, dxy_bias, and risk_asset_bias.
    
    Detects inversions/hallucinations and sets escalation_required accordingly.
    """
    validated = dict(judge_result or {})
    
    raw_winner = validated.get("winner", "TIE")
    canonical_winner = normalize_winner(raw_winner)
    validated["winner"] = canonical_winner
    validated["legacy_winner"] = LEGACY_WINNER_MAPPING.get(canonical_winner, "TIE")
    
    dxy_bias = str(validated.get("dxy_bias", "NEUTRAL") or "NEUTRAL").upper()
    if dxy_bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
        dxy_bias = "NEUTRAL"
    validated["dxy_bias"] = dxy_bias
    
    risk_asset_bias = str(validated.get("risk_asset_bias", "NEUTRAL") or "NEUTRAL").upper()
    if risk_asset_bias not in ("BULLISH", "BEARISH", "NEUTRAL"):
        risk_asset_bias = "NEUTRAL"
    validated["risk_asset_bias"] = risk_asset_bias
    
    try:
        bull_score = int(validated.get("bull_arguments_score", 5))
    except (ValueError, TypeError):
        bull_score = 5
    try:
        bear_score = int(validated.get("bear_arguments_score", 5))
    except (ValueError, TypeError):
        bear_score = 5
        
    bull_score = max(1, min(10, bull_score))
    bear_score = max(1, min(10, bear_score))
    validated["bull_arguments_score"] = bull_score
    validated["bear_arguments_score"] = bear_score
    
    escalation_required = bool(validated.get("escalation_required", False))
    hallucination_detected = False
    hallucination_reasons: List[str] = []
    
    # 1. Check Score vs Winner Consistency
    if canonical_winner == "RISK_ON_USD_BEAR" and bear_score > bull_score:
        hallucination_detected = True
        hallucination_reasons.append(
            f"Winner declared RISK_ON_USD_BEAR but Bear score ({bear_score}) > Bull score ({bull_score})"
        )
    elif canonical_winner == "RISK_OFF_USD_BULL" and bull_score > bear_score:
        hallucination_detected = True
        hallucination_reasons.append(
            f"Winner declared RISK_OFF_USD_BULL but Bull score ({bull_score}) > Bear score ({bear_score})"
        )
        
    # 2. Check Winner vs Directional Biases Consistency
    if canonical_winner == "RISK_ON_USD_BEAR":
        if dxy_bias == "BULLISH":
            hallucination_detected = True
            hallucination_reasons.append("Inversion: Winner is RISK_ON_USD_BEAR but dxy_bias is BULLISH")
        if risk_asset_bias == "BEARISH":
            hallucination_detected = True
            hallucination_reasons.append("Inversion: Winner is RISK_ON_USD_BEAR but risk_asset_bias is BEARISH")
    elif canonical_winner == "RISK_OFF_USD_BULL":
        if dxy_bias == "BEARISH":
            hallucination_detected = True
            hallucination_reasons.append("Inversion: Winner is RISK_OFF_USD_BULL but dxy_bias is BEARISH")
        if risk_asset_bias == "BULLISH":
            hallucination_detected = True
            hallucination_reasons.append("Inversion: Winner is RISK_OFF_USD_BULL but risk_asset_bias is BULLISH")
            
    # 3. Check Tight Score / Uncertainty Escalation
    if abs(bull_score - bear_score) <= 1 or canonical_winner == "TIE":
        escalation_required = True
        
    if hallucination_detected:
        escalation_required = True
        logger.warning(
            f"[MacroDebateValidator] Internal hallucination detected in Judge output: {'; '.join(hallucination_reasons)}"
        )
        
    validated["escalation_required"] = escalation_required
    validated["internal_hallucination_detected"] = hallucination_detected
    validated["hallucination_reasons"] = hallucination_reasons
    
    return validated
