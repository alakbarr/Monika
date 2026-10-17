import logging
from typing import Any, Dict, Optional

from monika.application.analysis.schemas.pydantic_schemas import ConfidenceLevel, SentimentAnalysisSchema, SentimentBand
from monika.domain.market.instrument_identity import get_cot_code_for_symbol

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

    def aggregate_sentiment(
        self,
        cot_data: dict,
        retail_data: dict,
        risk_data: dict,
        symbol: str = "",
        funding_data: Optional[dict] = None,
    ) -> SentimentAnalysisSchema:
        """
        Weights:
        - Non-crypto: Institutional COT (40%), Retail (30%), Risk appetite (30%)
        - Crypto: Institutional COT (35%), Retail (25%), Risk appetite (20%), Perpetual Funding (20%)
        """
        score = 5.0  # Neutral base
        confidence = ConfidenceLevel.LOW
        narrative_parts = []

        # 1. COT (Institutional) - 40% weight (or 35% for crypto)
        cot_score = 5.0
        if cot_data and not cot_data.get("error"):
            sym_clean = symbol.upper().replace("/", "").replace("-", "").strip() if symbol else ""
            actual_cot = None
            if isinstance(cot_data, dict):
                # Unpack nested payload from handle_get_precomputed_cot_signals if wrapped
                unwrapped_cot = cot_data["cot_signals"] if isinstance(cot_data.get("cot_signals"), dict) else cot_data
                cftc_code = get_cot_code_for_symbol(sym_clean) or SYMBOL_TO_CFTC_CODE.get(sym_clean)
                if sym_clean and sym_clean in unwrapped_cot:
                    actual_cot = unwrapped_cot[sym_clean]
                elif cftc_code and cftc_code in unwrapped_cot:
                    actual_cot = unwrapped_cot[cftc_code]
                elif "signal" in cot_data or "bias" in cot_data:
                    actual_cot = cot_data
                elif "signal" in unwrapped_cot or "bias" in unwrapped_cot:
                    actual_cot = unwrapped_cot
                else:
                    actual_cot = unwrapped_cot.get(cftc_code, unwrapped_cot) if cftc_code else unwrapped_cot
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

        # 2. Retail - 30% weight (or 25% for crypto, CONTRARIAN)
        retail_score = 5.0
        if retail_data and not retail_data.get("error"):
            long_pct = retail_data.get("long_pct", 50)
            if long_pct > 70:
                retail_score = 2.0  # Contrarian: heavily long retail -> bearish signal
                narrative_parts.append("Retail is extremely long (contrarian bearish).")
            elif long_pct < 30:
                retail_score = 8.0
                narrative_parts.append("Retail is extremely short (contrarian bullish).")
            else:
                narrative_parts.append("Retail positioning is balanced.")

        # 3. Risk Appetite - 30% weight (or 20% for crypto, Safe-Haven aware)
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
                    narrative_parts.append(
                        "High VIX indicates risk-off environment (safe-haven inflows strengthen JPY/CHF, bearish pair)."
                    )
                else:
                    risk_score = 2.0
                    narrative_parts.append("High VIX indicates risk-off environment (bearish risk assets).")
            elif vix < 15:
                if is_safe_haven_asset:
                    risk_score = 3.0
                    narrative_parts.append("Low VIX indicates risk-on environment (soft safe-haven demand).")
                elif is_safe_haven_quote:
                    risk_score = 8.0
                    narrative_parts.append(
                        "Low VIX indicates risk-on environment (carry trade expansion, bullish USDJPY/crosses)."
                    )
                else:
                    risk_score = 8.0
                    narrative_parts.append("Low VIX indicates risk-on environment (bullish risk assets).")
            else:
                narrative_parts.append("VIX indicates moderate risk environment.")

        # 4. Crypto Perpetual Funding Rate (if crypto symbol and funding_data provided)
        funding_score: Optional[float] = None
        is_crypto = any(c in sym_upper for c in ["BTC", "ETH", "SOL", "CRYPTO"])
        if is_crypto and funding_data and not funding_data.get("error"):
            fr_raw = funding_data.get("funding_rate") or funding_data.get("average_funding_rate")
            if fr_raw is not None:
                try:
                    fr_val = float(fr_raw)
                    if fr_val > 0.0003:
                        funding_score = 2.0  # Heavily long -> contrarian liquidation risk
                        narrative_parts.append(
                            f"Crypto funding rate ({fr_val:+.4f}) is crowded long (liquidation risk)."
                        )
                    elif fr_val < -0.0001:
                        funding_score = 8.0  # Crowded short -> short squeeze potential
                        narrative_parts.append(
                            f"Crypto funding rate ({fr_val:+.4f}) is negative (short squeeze potential)."
                        )
                    else:
                        funding_score = 5.0
                        narrative_parts.append(f"Crypto funding rate ({fr_val:+.4f}) is neutral.")
                except Exception:
                    funding_score = None

        # Aggregate (Scale 0-10)
        if funding_score is not None:
            overall_score = (cot_score * 0.35) + (retail_score * 0.25) + (risk_score * 0.20) + (funding_score * 0.20)
        else:
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
        check_sources = [cot_data, retail_data, risk_data]
        if funding_data is not None:
            check_sources.append(funding_data)
        sources_avail = sum([1 for d in check_sources if d and not d.get("error")])

        if sources_avail >= 3:
            confidence = ConfidenceLevel.HIGH
        elif sources_avail == 2:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        return SentimentAnalysisSchema(
            overall_band=band,
            overall_score=round(overall_score, 1),
            confidence=confidence,
            narrative=" ".join(narrative_parts),
            retail_vs_institutional="Alignment"
            if (cot_score > 5 and retail_score > 5) or (cot_score < 5 and retail_score < 5)
            else "Divergence",
        )
