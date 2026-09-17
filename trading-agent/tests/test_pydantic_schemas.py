import pytest
from pydantic import ValidationError
from analysis.schemas.pydantic_schemas import FundamentalBriefSchema, TradeDirection, ConfidenceLevel

def test_fundamental_brief_schema_valid():
    data = {
        "macro_bias": "Bullish USD",
        "key_drivers": ["Fed hike"],
        "risk_events": ["CPI", "NFP"],
        "narrative_shift": False,
        "currency_bias": {"USD": "bullish"},
        "confidence": 0.85
    }
    obj = FundamentalBriefSchema(**data)
    assert obj.macro_bias == "Bullish USD"
    assert obj.currency_bias["USD"] == "bullish"
    assert obj.confidence == 0.85


def test_submit_asset_analysis_trade_validation():
    from analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema, EntryCondition

    # 1. Buy without stop_loss should fail
    with pytest.raises(ValidationError):
        SubmitAssetAnalysisSchema(
            symbol="EURUSD",
            decision="buy",
            confidence=0.8,
            rationale="Test bullish setup",
            invalidation="Invalid if closes below 1.0800",
            entry_condition=EntryCondition(type="market", detail="Market execution"),
            take_profit=1.0950,
            stop_loss=None
        )

    # 2. Buy with full trade parameters should pass
    schema = SubmitAssetAnalysisSchema(
        symbol="EURUSD",
        decision="buy",
        confidence=0.8,
        rationale="Test bullish setup",
        invalidation="Invalid if closes below 1.0800",
        invalidation_price=1.0800,
        invalidation_direction="below",
        confluence_score=8,
        priced_in_score=3,
        entry_condition=EntryCondition(type="market", detail="Market execution"),
        reevaluation_trigger={"type": "indicator", "detail": "RSI drops below 30"},
        stop_loss=1.0800,
        take_profit=1.0950
    )
    assert schema.decision == "buy"
    assert schema.stop_loss == 1.0800
    assert schema.take_profit == 1.0950
    assert schema.confluence_score == 8
    assert schema.priced_in_score == 3
    assert schema.invalidation_price == 1.0800
    assert schema.invalidation_direction == "below"

    # 3. Buy missing confluence_score / priced_in_score / invalidation_price should fail
    with pytest.raises(ValidationError) as excinfo:
        SubmitAssetAnalysisSchema(
            symbol="EURUSD",
            decision="buy",
            confidence=0.8,
            rationale="Test bullish setup",
            invalidation="Invalid if closes below 1.0800",
            entry_condition=EntryCondition(type="market", detail="Market execution"),
            reevaluation_trigger={"type": "indicator", "detail": "RSI drops below 30"},
            stop_loss=1.0800,
            take_profit=1.0950,
            confluence_score=None
        )
    assert "confluence_score" in str(excinfo.value)

    # 4. Avoid / Wait without stop_loss should pass
    avoid_schema = SubmitAssetAnalysisSchema(
        symbol="EURUSD",
        decision="avoid",
        confidence=0.5,
        rationale="Unclear market direction",
        invalidation="N/A"
    )
    assert avoid_schema.decision == "avoid"
    assert avoid_schema.stop_loss is None

def test_submit_asset_analysis_symbol_aliases_and_normalization():
    from analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema

    # Test alias resolution
    for alias_key in ("asset", "pair", "ticker", "instrument", "symbol_name", "target_asset", "currency_pair"):
        payload = {
            alias_key: "gbpusd",
            "decision": "wait",
            "confidence": 0.6,
            "rationale": "Testing alias",
            "invalidation": "Invalid if structure breaks",
            "reevaluation_trigger": {"type": "time", "detail": "Wait 4h"}
        }
        obj = SubmitAssetAnalysisSchema.model_validate(payload)
        assert obj.symbol == "GBPUSD"

    # Test slash and whitespace stripping
    payload_slash = {
        "symbol": " EUR/USD ",
        "decision": "avoid",
        "confidence": 0.5,
        "rationale": "Testing slash",
        "invalidation": "N/A"
    }
    obj_slash = SubmitAssetAnalysisSchema.model_validate(payload_slash)
    assert obj_slash.symbol == "EURUSD"


def test_coerce_float_and_coerce_int_helpers():
    from analysis.schemas.pydantic_schemas import coerce_float, coerce_int

    # Float coercion
    assert coerce_float(58.4) == 58.4
    assert coerce_float("58.4%") == 58.4
    assert coerce_float("+15%") == 15.0
    assert coerce_float("-12.5%") == -12.5
    assert coerce_float("~4.25") == 4.25
    assert coerce_float(">80%") == 80.0
    assert coerce_float("58.4% long") == 58.4
    assert coerce_float("15.2 pts") == 15.2
    assert coerce_float("N/A") is None
    assert coerce_float("None") is None
    assert coerce_float("null") is None
    assert coerce_float("not quoted") is None
    assert coerce_float("-") is None
    assert coerce_float("") is None
    assert coerce_float(None) is None

    # Int coercion
    assert coerce_int(8) == 8
    assert coerce_int("8") == 8
    assert coerce_int("8/10") == 8
    assert coerce_int("8.0") == 8
    assert coerce_int("N/A") is None
    assert coerce_int("none") is None
    assert coerce_int(None) is None


def test_key_data_points_used_string_and_percentage_coercion():
    from analysis.schemas.pydantic_schemas import KeyDataPointsUsed

    # 1. String with %, N/A, and +/-
    kdp = KeyDataPointsUsed.model_validate({
        "dxy_trend_5d": "strengthening +0.8%",
        "vix_close": "15.5",
        "fedwatch_dominant_pct": "85.0%",
        "treasury_10y_yield_pct": "4.25%",
        "cot_leveraged_long_pct": "58.4%"
    })
    assert kdp.vix_close == 15.5
    assert kdp.fedwatch_dominant_pct == 85.0
    assert kdp.treasury_10y_yield_pct == 4.25
    assert kdp.cot_leveraged_long_pct == 58.4

    # 2. Placeholders N/A, not quoted, None
    kdp2 = KeyDataPointsUsed.model_validate({
        "dxy_trend_5d": "weakening -0.4%",
        "vix_close": 18.2,
        "fedwatch_dominant_pct": "N/A",
        "treasury_10y_yield_pct": "none",
        "cot_leveraged_long_pct": "not quoted"
    })
    assert kdp2.vix_close == 18.2
    assert kdp2.fedwatch_dominant_pct is None
    assert kdp2.treasury_10y_yield_pct is None
    assert kdp2.cot_leveraged_long_pct is None


def test_priced_in_assessment_coercion():
    from analysis.schemas.pydantic_schemas import PricedInAssessment

    pi = PricedInAssessment.model_validate({
        "dominant_driver": "Rate cut",
        "priced_in_score": "7/10",
        "sell_the_news_risk": "medium",
        "cot_positioning_percentile": "65%",
        "retail_sentiment_percentile": "40.5%"
    })
    assert pi.priced_in_score == 7
    assert pi.cot_positioning_percentile == 65.0
    assert pi.retail_sentiment_percentile == 40.5


def test_submit_fundamental_brief_full_coercion():
    from analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    payload = {
        "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
        "key_data_points_used": {
            "dxy_trend_5d": "strengthening +0.8%",
            "vix_close": "15.5",
            "fedwatch_dominant_pct": "85%",
            "treasury_10y_yield_pct": "4.25%",
            "cot_leveraged_long_pct": "58.4%"
        },
        "macro_narrative": "Detailed macro narrative describing the economic drivers...",
        "currency_bias": {
            "USD": "bullish", "EUR": "bearish", "GBP": "neutral",
            "JPY": "neutral", "AUD": "neutral", "XAU": "bearish"
        },
        "currency_confidence": {
            "USD": "80%",
            "EUR": "0.7",
            "XAU": 0.9
        },
        "confidence": "85%",
        "risk_sentiment": "risk-on",
        "macro_regime": "mixed",
        "priced_in_assessment": {
            "dominant_driver": "Fed cut",
            "priced_in_score": "6",
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": "75.0%"
        }
    }

    brief = SubmitFundamentalBriefSchema.model_validate(payload)
    assert brief.confidence == 0.85
    assert brief.currency_confidence["USD"] == 0.80
    assert brief.currency_confidence["EUR"] == 0.70
    assert brief.currency_confidence["XAU"] == 0.90
    assert brief.key_data_points_used.cot_leveraged_long_pct == 58.4
    assert brief.key_data_points_used.treasury_10y_yield_pct == 4.25
    assert brief.key_data_points_used.vix_close == 15.5
    assert brief.priced_in_assessment.priced_in_score == 6
    assert brief.priced_in_assessment.cot_positioning_percentile == 75.0


def test_coerce_string_list_and_str_helpers():
    from analysis.schemas.pydantic_schemas import coerce_str, coerce_string_list

    # 1. coerce_str
    assert coerce_str("  plain text  ") == "plain text"
    assert coerce_str({"event_name": "US CPI", "impact": "high"}) == "US CPI"
    assert coerce_str({"detail": "Invalid below 1.0800"}) == "Invalid below 1.0800"
    assert coerce_str(["tag1", "tag2"]) == "tag1; tag2"
    assert coerce_str(12345) == "12345"
    assert coerce_str(None) == ""

    # 2. coerce_string_list
    mixed_list = [
        "FOMC Rate Decision",
        {"event_name": "US CPI", "currency": "USD", "impact": "high"},
        {"title": "Crude Oil Inventory Draw", "source": "EIA"},
        {"driver": "Fed Hawkish Repricing"},
        123,
        None,
        "NFP Surprise"
    ]
    res = coerce_string_list(mixed_list)
    assert len(res) == 6
    assert res[0] == "FOMC Rate Decision"
    assert "US CPI" in res[1] and "USD" in res[1] and "high" in res[1]
    assert "Crude Oil Inventory Draw" in res[2]
    assert "Fed Hawkish Repricing" in res[3]
    assert res[4] == "123"
    assert res[5] == "NFP Surprise"

    # Multiline string coercion
    assert coerce_string_list("1. US CPI\n2. FOMC Decision\n3. NFP") == ["US CPI", "FOMC Decision", "NFP"]


def test_submit_asset_analysis_key_news_events_considered_dict_at_index_5():
    """Exact reproduction test for the reported log warning: dictionary at index 5."""
    from analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema, EntryCondition

    payload = {
        "symbol": "XAUUSD",
        "decision": "buy",
        "confidence": "0.85",
        "rationale": {"technical": "Bullish OB mitigated", "macro": "DXY weakening"},
        "invalidation": "Thesis invalid if XAUUSD D1 closes below 2400",
        "invalidation_price": 2400.0,
        "invalidation_direction": "below",
        "confluence_score": 8,
        "priced_in_score": 3,
        "entry_condition": {"type": "market", "detail": "Market entry"},
        "reevaluation_trigger": {"type": "time", "detail": "Wait 4 hours"},
        "stop_loss": 2400.0,
        "take_profit": 2460.0,
        "confluence_factors": ["fundamental_bias", "d1_trend", "near_fvg", "near_order_block"],
        "key_news_events_considered": [
            "US CPI YoY 3.1%",
            "FOMC Minutes Release",
            "Fed Powell Speech",
            "US Initial Jobless Claims",
            "Retail Sales MoM",
            {"event_name": "Jackson Hole Symposium", "currency": "USD", "impact": "high"}  # Index 5 is dict!
        ],
        "news_impact_assessment": {"impact": "High volatility expected around speech"}
    }

    schema = SubmitAssetAnalysisSchema.model_validate(payload)
    assert schema.symbol == "XAUUSD"
    assert len(schema.key_news_events_considered) == 6
    assert schema.key_news_events_considered[0] == "US CPI YoY 3.1%"
    assert "Jackson Hole Symposium" in schema.key_news_events_considered[5]
    assert "USD" in schema.key_news_events_considered[5]
    assert "Bullish OB mitigated" in schema.rationale or "macro" in schema.rationale


def test_upcoming_risk_events_coercion_robustness():
    from analysis.schemas.pydantic_schemas import UpcomingRiskEvent

    # 1. Plain string
    evt1 = UpcomingRiskEvent.model_validate("US CPI Release (high impact)")
    assert evt1.event == "US CPI Release (high impact)"
    assert evt1.expected_impact == "high"
    assert evt1.time == "upcoming"

    # 2. Incomplete dict
    evt2 = UpcomingRiskEvent.model_validate({"name": "Fed Rate Decision", "impact": "high"})
    assert evt2.event == "Fed Rate Decision"
    assert evt2.expected_impact == "high"
    assert evt2.time == "upcoming"



