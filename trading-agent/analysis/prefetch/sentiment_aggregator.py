import logging
from typing import Dict, Any
from analysis.schemas.pydantic_schemas import SentimentAnalysisSchema, SentimentBand, ConfidenceLevel

logger = logging.getLogger("TradingAgent.SentimentAggregator")

SYMBOL_TO_CFTC_CODE = {
    "XAUUSD": "088691",
    "GOLD": "088691",
    "EURUSD": "099741",
    "GBPUSD": "096742",
    "USDJPY": "097741",
    "AUDUSD": "232741",
    "XTIUSD": "067651",
    "USOIL": "067651",
    "CRUDE_OIL": "067651",
    "XBRUSD": "067651",
    "UKOIL": "067651",
    "BTCUSD": "133741",
}

class SentimentAggregator:
    """
    Aggregates sentiment from multiple sources (COT, Retail, VIX, Funding Rates)
    into a single unified SentimentAnalysisSchema.
    """
    
    def __init__(self, settings: dict):
        self.settings = settings

    def aggregate_sentiment(self, cot_data: dict, retail_data: dict, risk_data: dict, symbol: str = "") -> SentimentAnalysisSchema:
        """
        Weights:
        - Institutional COT: 40% weight (trend-following)
        - Retail (FXSSI/MyFxBook/Binance): 30% weight (CONTRARIAN)
        - Risk appetite (VIX/FearGreed): 30% weight (market regime, aware of Safe-Haven assets)
        """
        score = 5.0 # Neutral base
        confidence = ConfidenceLevel.LOW
        narrative_parts = []
        
        # 1. COT (Institutional) - 40% weight (0 to 4 points)
        cot_score = 5.0
        if cot_data and not cot_data.get("error"):
            sym_clean = symbol.upper().replace("/", "").replace("-", "").strip() if symbol else ""
            actual_cot = None
            if isinstance(cot_data, dict):
                if sym_clean and sym_clean in cot_data:
                    actual_cot = cot_data[sym_clean]
                elif sym_clean and sym_clean in SYMBOL_TO_CFTC_CODE and SYMBOL_TO_CFTC_CODE[sym_clean] in cot_data:
                    actual_cot = cot_data[SYMBOL_TO_CFTC_CODE[sym_clean]]
                elif "signal" in cot_data or "bias" in cot_data:
                    actual_cot = cot_data
                else:
                    cftc_code = SYMBOL_TO_CFTC_CODE.get(sym_clean)
                    actual_cot = cot_data.get(cftc_code, cot_data) if cftc_code else cot_data
            else:
                actual_cot = cot_data

            if not isinstance(actual_cot, dict):
                actual_cot = {}

            signal = str(actual_cot.get("signal") or actual_cot.get("bias") or "").lower()
            flag = str(actual_cot.get("flag") or "").lower()

            # Handle contract-to-pair directional inversion for USDJPY:
            # CME 097741 is JPY futures. Long JPY = JPY strengthens = USDJPY falls (Bearish pair).
            if sym_clean in ("USDJPY", "097741") and "pair_signal" not in actual_cot:
                if "extreme_long" in flag or signal in ("extreme_long", "strong_bullish"):
                    signal = "strong_bearish"
                    flag = "extreme_short"
                elif "extreme_short" in flag or signal in ("extreme_short", "strong_bearish"):
                    signal = "strong_bullish"
                    flag = "extreme_long"
                elif "bull" in signal or "long" in signal:
                    signal = "bearish"
                elif "bear" in signal or "short" in signal:
                    signal = "bullish"
            
            if "extreme_long" in flag or signal in ("extreme_long", "strong_bullish"):
                cot_score = 9.0
                narrative_parts.append("Institutional positioning is extreme long (strong bullish momentum).")
            elif "extreme_short" in flag or signal in ("extreme_short", "strong_bearish"):
                cot_score = 1.0
                narrative_parts.append("Institutional positioning is extreme short (strong bearish momentum).")
            elif "bull" in signal or "long" in signal:
                cot_score = 8.0
                narrative_parts.append("Institutional positioning is net long.")
            elif "bear" in signal or "short" in signal:
                cot_score = 2.0
                narrative_parts.append("Institutional positioning is net short.")
            else:
                narrative_parts.append("Institutional positioning is neutral.")
        
        # 2. Retail - 30% weight (0 to 3 points, CONTRARIAN)
        retail_score = 5.0
        if retail_data and not retail_data.get("error"):
            long_pct = retail_data.get("long_pct", 50)
            if long_pct > 70:
                retail_score = 2.0 # Contrarian: heavily long retail -> bearish signal
                narrative_parts.append("Retail is extremely long (contrarian bearish).")
            elif long_pct < 30:
                retail_score = 8.0
                narrative_parts.append("Retail is extremely short (contrarian bullish).")
            else:
                narrative_parts.append("Retail positioning is balanced.")
                
        # 3. Risk Appetite - 30% weight (0 to 3 points, Safe-Haven aware)
        risk_score = 5.0
        sym_upper = (symbol or "").upper()
        is_safe_haven_asset = any(s in sym_upper for s in ["XAU", "GOLD", "XAG"])
        is_safe_haven_quote = any(sym_upper.endswith(s) for s in ["JPY", "CHF"])

        if risk_data and not risk_data.get("error"):
            vix = risk_data.get("close", 20)
            if vix > 30:
                if is_safe_haven_asset:
                    risk_score = 8.0
                    narrative_parts.append("High VIX indicates risk-off environment (bullish safe-haven gold/silver).")
                elif is_safe_haven_quote:
                    risk_score = 2.0
                    narrative_parts.append("High VIX indicates risk-off environment (safe-haven inflows strengthen JPY/CHF, bearish pair).")
                else:
                    risk_score = 2.0
                    narrative_parts.append("High VIX indicates risk-off environment (bearish risk assets).")
            elif vix < 15:
                if is_safe_haven_asset:
                    risk_score = 3.0
                    narrative_parts.append("Low VIX indicates risk-on environment (soft safe-haven demand).")
                elif is_safe_haven_quote:
                    risk_score = 8.0
                    narrative_parts.append("Low VIX indicates risk-on environment (carry trade expansion, bullish USDJPY/crosses).")
                else:
                    risk_score = 8.0
                    narrative_parts.append("Low VIX indicates risk-on environment (bullish risk assets).")
            else:
                narrative_parts.append("VIX indicates moderate risk environment.")

        # Aggregate (Scale 0-10)
        overall_score = (cot_score * 0.4) + (retail_score * 0.3) + (risk_score * 0.3)
        overall_score = max(0.0, min(10.0, overall_score))
        
        # Determine Band
        if overall_score >= 8.0:
            band = SentimentBand.BULLISH
        elif overall_score >= 6.0:
            band = SentimentBand.MILDLY_BULLISH
        elif overall_score >= 4.5:
            band = SentimentBand.NEUTRAL
        elif overall_score >= 3.5:
            band = SentimentBand.MIXED
        elif overall_score >= 2.0:
            band = SentimentBand.MILDLY_BEARISH
        else:
            band = SentimentBand.BEARISH
            
        # Determine confidence based on data availability
        sources_avail = sum([1 for d in [cot_data, retail_data, risk_data] if d and not d.get("error")])
        if sources_avail == 3:
            confidence = ConfidenceLevel.HIGH
        elif sources_avail == 2:
            confidence = ConfidenceLevel.MEDIUM
            
        return SentimentAnalysisSchema(
            overall_band=band,
            overall_score=round(overall_score, 1),
            confidence=confidence,
            narrative=" ".join(narrative_parts),
            retail_vs_institutional="Alignment" if (cot_score > 5 and retail_score > 5) or (cot_score < 5 and retail_score < 5) else "Divergence"
        )
