import logging
from typing import Dict, Any
from analysis.schemas.pydantic_schemas import SentimentAnalysisSchema, SentimentBand, ConfidenceLevel

logger = logging.getLogger("TradingAgent.SentimentAggregator")

class SentimentAggregator:
    """
    Aggregates sentiment from multiple sources (COT, Retail, VIX, Funding Rates)
    into a single unified SentimentAnalysisSchema.
    """
    
    def __init__(self, settings: dict):
        self.settings = settings

    def aggregate_sentiment(self, cot_data: dict, retail_data: dict, risk_data: dict) -> SentimentAnalysisSchema:
        """
        Weights:
        - Institutional COT: 40% weight (trend-following)
        - Retail (FXSSI/MyFxBook/Binance): 30% weight (CONTRARIAN)
        - Risk appetite (VIX/FearGreed): 30% weight (market regime)
        """
        score = 5.0 # Neutral base
        confidence = ConfidenceLevel.LOW
        narrative_parts = []
        
        # 1. COT (Institutional) - 40% weight (0 to 4 points)
        # Assuming cot_data has a 'net_long' or 'bias' field
        cot_score = 5.0
        if cot_data and not cot_data.get("error"):
            # Mock logic based on net bias
            bias = cot_data.get("bias", "neutral")
            if bias == "net_long":
                cot_score = 8.0
                narrative_parts.append("Institutional positioning is net long.")
            elif bias == "net_short":
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
                
        # 3. Risk Appetite - 30% weight (0 to 3 points)
        risk_score = 5.0
        if risk_data and not risk_data.get("error"):
            vix = risk_data.get("close", 20)
            if vix > 30:
                risk_score = 2.0
                narrative_parts.append("High VIX indicates risk-off environment.")
            elif vix < 15:
                risk_score = 8.0
                narrative_parts.append("Low VIX indicates risk-on environment.")
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
