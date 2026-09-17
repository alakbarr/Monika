import pytest
from analysis.prefetch.sentiment_aggregator import SentimentAggregator
from analysis.schemas.pydantic_schemas import SentimentBand, ConfidenceLevel

def test_sentiment_aggregator():
    agg = SentimentAggregator({})
    
    cot_data = {"bias": "net_long"}
    retail_data = {"long_pct": 75} # heavily long -> contrarian bearish
    risk_data = {"close": 12} # Low VIX -> risk on bullish
    
    # Weights: COT(40% of 8=3.2), Retail(30% of 2=0.6), Risk(30% of 8=2.4)
    # Total = 6.2
    
    res = agg.aggregate_sentiment(cot_data, retail_data, risk_data)
    
    assert res.overall_score == 6.2
    assert res.overall_band == SentimentBand.MILDLY_BULLISH
    assert res.confidence == ConfidenceLevel.HIGH
    assert "Divergence" in res.retail_vs_institutional
    assert "Institutional positioning is net long" in res.narrative
    assert "Retail is extremely long" in res.narrative
