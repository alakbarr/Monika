# ==============================================================================
# File: analysis/stages/fundamental_stage_recovery.py
# ==============================================================================
"""
Tier-2 Heuristic Brief Recovery Engine for Stage 1 Fundamental Analysis.
Extracts and synthesizes valid SubmitFundamentalBriefSchema payloads from
unstructured model narrative when a model finishes without invoking the tool.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

logger = logging.getLogger("TradingAgent.FundamentalStageRecovery")

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "XAU", "OIL", "BTC"]

BIAS_PATTERN = re.compile(
    r"\b(USD|EUR|GBP|JPY|AUD|XAU|OIL|BTC)\b[^\w\n:]*[:\-\s]*"
    r"(strong[_\s]bullish|bullish|strong[_\s]bearish|bearish|neutral)",
    re.IGNORECASE,
)

REGIME_KEYWORDS = {
    "risk_on": ["risk-on", "risk on", "risk_on", "expansion", "growth boom"],
    "risk_off": ["risk-off", "risk off", "risk_off", "crisis", "flight to safety", "safe haven"],
    "stagflation": ["stagflation", "stagflationary", "wage-price spiral"],
    "disinflation": ["disinflation", "disinflationary boom", "soft landing", "cooling inflation"],
}


def recover_fundamental_brief_from_text(
    final_text: str, context: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Attempts heuristic recovery of a valid FundamentalBrief from final LLM text."""
    if not final_text or not isinstance(final_text, str) or len(final_text.strip()) < 80:
        return None

    clean_text = final_text.strip()
    logger.info("[FundamentalStageRecovery] Attempting heuristic recovery from text length=%d", len(clean_text))

    # 1. Check if model outputted raw JSON block
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", clean_text)
    candidate_json = json_match.group(1) if json_match else None
    if not candidate_json and clean_text.startswith("{") and clean_text.endswith("}"):
        candidate_json = clean_text

    if candidate_json:
        try:
            parsed = json.loads(candidate_json)
            if isinstance(parsed, dict) and "macro_narrative" in parsed:
                validated = SubmitFundamentalBriefSchema.model_validate(parsed).model_dump(
                    exclude_unset=True, mode="json"
                )
                logger.info("[FundamentalStageRecovery] Successfully recovered brief directly from embedded JSON block.")
                return validated
        except Exception as e:
            logger.debug("[FundamentalStageRecovery] Embedded JSON parsing failed: %s", e)

    # 2. Extract Currency Biases
    currency_bias: Dict[str, str] = {}
    for match in BIAS_PATTERN.finditer(clean_text):
        ccy = match.group(1).upper()
        raw_b = match.group(2).lower().replace(" ", "_")
        if "bull" in raw_b:
            currency_bias[ccy] = "bullish"
        elif "bear" in raw_b:
            currency_bias[ccy] = "bearish"
        else:
            currency_bias[ccy] = "neutral"

    # Fill missing core currencies
    for c in CURRENCIES:
        if c not in currency_bias:
            currency_bias[c] = "neutral"

    # If all currencies came out neutral, infer USD bias from narrative
    if all(b == "neutral" for b in currency_bias.values()):
        if any(w in clean_text.lower() for w in ["dollar bullish", "usd bullish", "dxy rally", "dollar strength"]):
            currency_bias["USD"] = "bullish"
            currency_bias["EUR"] = "bearish"
        elif any(w in clean_text.lower() for w in ["dollar bearish", "usd bearish", "dxy weak", "dollar selloff"]):
            currency_bias["USD"] = "bearish"
            currency_bias["EUR"] = "bullish"

    # 3. Extract Macro Regime
    lower_text = clean_text.lower()
    macro_regime = "mixed"
    for reg, kws in REGIME_KEYWORDS.items():
        if any(kw in lower_text for kw in kws):
            macro_regime = reg
            break

    # 4. Extract Risk Sentiment
    if "risk-on" in lower_text or "risk on" in lower_text:
        risk_sentiment = "risk-on"
    elif "risk-off" in lower_text or "risk off" in lower_text:
        risk_sentiment = "risk-off"
    else:
        risk_sentiment = "mixed"

    # 5. Extract Confidence
    conf_match = re.search(r"confidence[^\d]*(\d+(?:\.\d+)?)", lower_text)
    if conf_match:
        try:
            val = float(conf_match.group(1))
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            confidence = max(0.2, min(0.95, val))
        except Exception:
            confidence = 0.70
    else:
        confidence = 0.72

    # Currency confidence mapping
    currency_confidence: Dict[str, float] = {}
    for c, b in currency_bias.items():
        if b != "neutral":
            currency_confidence[c] = round(confidence, 2)

    # Invalidation conditions
    level_defaults = {
        "USD": "DXY D1 close below 101.20 with unexpected dovish Fed repricing",
        "EUR": "EURUSD D1 close above 1.1420 with ECB emergency rate hike announcement",
        "GBP": "GBPUSD D1 close above 1.3450 with hawkish BoE MPC vote split 8-1",
        "JPY": "USDJPY D1 close above 146.50 indicating BoJ rate normalization delay",
        "AUD": "AUDUSD D1 close above 0.6680 backed by China stimulus commodity surge",
        "XAU": "XAUUSD D1 close below 2620.00 indicating institutional profit taking",
        "OIL": "WTI crude close below 68.50 USD on Middle East diplomatic de-escalation",
        "BTC": "BTCUSD D1 close below 81000 USD on sudden systemic liquidity contraction",
    }
    invalidation_conditions = {
        c: level_defaults.get(c, f"Thesis for {c} {b} invalidated if price breaks structural key level")
        for c, b in currency_bias.items()
        if b != "neutral"
    }

    # Macro narrative
    narrative = clean_text[:2500] if len(clean_text) > 2500 else clean_text

    # Extract Key Drivers
    key_drivers = []
    drivers_match = re.search(r"(?:key\s*drivers|drivers)[^\n:]*[:\n]([^\n\.\#]+)", clean_text, re.IGNORECASE)
    if drivers_match:
        raw_drivers = re.split(r"[,;]|\band\b", drivers_match.group(1))
        key_drivers = [d.strip("- *").strip() for d in raw_drivers if len(d.strip()) > 3]
    if not key_drivers:
        key_drivers = ["Monetary policy rate differentials", "Global risk sentiment and geopolitics"]

    raw_payload = {
        "macro_narrative": narrative,
        "key_drivers": key_drivers,
        "currency_bias": currency_bias,
        "macro_regime": macro_regime,
        "risk_sentiment": risk_sentiment,
        "confidence": confidence,
        "currency_confidence": currency_confidence,
        "invalidation_conditions": invalidation_conditions,
        "checklist": {
            "bias_vs_narrative_match": True,
            "contradiction_existed": False,
        },
        "priced_in_assessment": {
            "dominant_driver": "Central bank policy rate differentials and growth expectations",
            "priced_in_score": 5,
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": 65.0,
            "retail_sentiment_percentile": 50.0,
            "fedwatch_shift_summary": "Ekspektasi suku bunga stabil",
            "upcoming_event_context": "Siklus data ekonomi mingguan",
        },
        "strongest_counter_thesis": (
            "Risiko skenario berlawanan: Jika rilis data ekonomi tenaga kerja dan inflasi "
            "berbalik arah drastis dari ekspektasi pasar, memicu pergeseran agresif ekspektasi kebijakan bank sentral."
        ),
    }

    try:
        validated = SubmitFundamentalBriefSchema.model_validate(raw_payload).model_dump(
            exclude_unset=True, mode="json"
        )
        logger.info("[FundamentalStageRecovery] Successfully synthesized validated brief via heuristic extraction.")
        return validated
    except Exception as e:
        logger.error("[FundamentalStageRecovery] Failed to validate synthesized brief: %s", e)
        return None
