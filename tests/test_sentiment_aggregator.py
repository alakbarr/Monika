import pytest
from monika.application.analysis.prefetch.sentiment_aggregator import SentimentAggregator
from monika.application.analysis.schemas.pydantic_schemas import SentimentBand, ConfidenceLevel


def test_sentiment_aggregator():
    agg = SentimentAggregator({})

    cot_data = {"bias": "net_long"}
    retail_data = {"long_pct": 75}  # heavily long -> contrarian bearish
    risk_data = {"close": 12}  # Low VIX -> risk on bullish

    # Weights: COT(40% of 8=3.2), Retail(30% of 2=0.6), Risk(30% of 8=2.4)
    # Total = 6.2

    res = agg.aggregate_sentiment(cot_data, retail_data, risk_data)

    assert res.overall_score == 6.2
    assert res.overall_band == SentimentBand.MILDLY_BULLISH
    assert res.confidence == ConfidenceLevel.HIGH
    assert "Divergence" in res.retail_vs_institutional
    assert "Institutional positioning is net long" in res.narrative
    assert "Retail is extremely long" in res.narrative


def test_sentiment_aggregator_nested_cot_payload():
    agg = SentimentAggregator({})

    nested_cot = {
        "status": "success",
        "cot_signals": {
            "EURUSD": {
                "signal": "strong_bullish",
                "flag": "extreme_long",
                "percentile_rank": 95.0,
            }
        },
    }
    retail_data = {"long_pct": 50}
    risk_data = {"close": 20}

    res = agg.aggregate_sentiment(nested_cot, retail_data, risk_data, symbol="EURUSD")

    # COT extreme long = 9.0 (40% = 3.6), Retail 50% = 5.0 (30% = 1.5), Risk = 5.0 (30% = 1.5) -> Total = 6.6
    assert res.overall_score == 6.6
    assert "Institutional positioning is extreme long" in res.narrative


def test_sentiment_aggregator_crypto_funding():
    agg = SentimentAggregator({})

    cot_data = {"bias": "bullish"}
    retail_data = {"long_pct": 50}
    risk_data = {"close": 20}
    funding_data = {"funding_rate": 0.0005}  # Excessively crowded long -> contrarian bearish (score=2.0)

    res = agg.aggregate_sentiment(cot_data, retail_data, risk_data, symbol="BTCUSD", funding_data=funding_data)

    # Weights: COT(35% of 8 = 2.8), Retail(25% of 5 = 1.25), Risk(20% of 5 = 1.0), Funding(20% of 2 = 0.4) -> 5.45 -> 5.5
    assert res.overall_score == 5.5
    assert "liquidation risk" in res.narrative
