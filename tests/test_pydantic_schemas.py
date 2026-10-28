import pytest
from pydantic import ValidationError
from monika.application.analysis.schemas.pydantic_schemas import FundamentalBriefSchema, TradeDirection, ConfidenceLevel


def test_fundamental_brief_schema_valid():
    data = {
        "macro_bias": "Bullish USD",
        "key_drivers": ["Fed hike"],
        "risk_events": ["CPI", "NFP"],
        "narrative_shift": False,
        "currency_bias": {"USD": "bullish"},
        "confidence": 0.85,
    }
    obj = FundamentalBriefSchema(**data)
    assert obj.macro_bias == "Bullish USD"
    assert obj.currency_bias["USD"] == "bullish"
    assert obj.confidence == 0.85


def test_submit_asset_analysis_trade_validation():
    from monika.application.analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema, EntryCondition

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
            stop_loss=None,
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
        take_profit=1.0950,
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
            confluence_score=None,
        )
    assert "confluence_score" in str(excinfo.value)

    # 4. Avoid / Wait without stop_loss should pass
    avoid_schema = SubmitAssetAnalysisSchema(
        symbol="EURUSD", decision="avoid", confidence=0.5, rationale="Unclear market direction", invalidation="N/A"
    )
    assert avoid_schema.decision == "avoid"
    assert avoid_schema.stop_loss is None


def test_submit_asset_analysis_symbol_aliases_and_normalization():
    from monika.application.analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema

    # Test alias resolution
    for alias_key in ("asset", "pair", "ticker", "instrument", "symbol_name", "target_asset", "currency_pair"):
        payload = {
            alias_key: "gbpusd",
            "decision": "wait",
            "confidence": 0.6,
            "rationale": "Testing alias",
            "invalidation": "Invalid if structure breaks",
            "reevaluation_trigger": {"type": "time", "detail": "Wait 4h"},
        }
        obj = SubmitAssetAnalysisSchema.model_validate(payload)
        assert obj.symbol == "GBPUSD"

    # Test slash and whitespace stripping
    payload_slash = {
        "symbol": " EUR/USD ",
        "decision": "avoid",
        "confidence": 0.5,
        "rationale": "Testing slash",
        "invalidation": "N/A",
    }
    obj_slash = SubmitAssetAnalysisSchema.model_validate(payload_slash)
    assert obj_slash.symbol == "EURUSD"


def test_coerce_float_and_coerce_int_helpers():
    from monika.application.analysis.schemas.pydantic_schemas import coerce_float, coerce_int

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
    from monika.application.analysis.schemas.pydantic_schemas import KeyDataPointsUsed

    # 1. String with %, N/A, and +/-
    kdp = KeyDataPointsUsed.model_validate(
        {
            "dxy_trend_5d": "strengthening +0.8%",
            "vix_close": "15.5",
            "fedwatch_dominant_pct": "85.0%",
            "treasury_10y_yield_pct": "4.25%",
            "cot_leveraged_long_pct": "58.4%",
        }
    )
    assert kdp.vix_close == 15.5
    assert kdp.fedwatch_dominant_pct == 85.0
    assert kdp.treasury_10y_yield_pct == 4.25
    assert kdp.cot_leveraged_long_pct == 58.4

    # 2. Placeholders N/A, not quoted, None
    kdp2 = KeyDataPointsUsed.model_validate(
        {
            "dxy_trend_5d": "weakening -0.4%",
            "vix_close": 18.2,
            "fedwatch_dominant_pct": "N/A",
            "treasury_10y_yield_pct": "none",
            "cot_leveraged_long_pct": "not quoted",
        }
    )
    assert kdp2.vix_close == 18.2
    assert kdp2.fedwatch_dominant_pct is None
    assert kdp2.treasury_10y_yield_pct is None
    assert kdp2.cot_leveraged_long_pct is None


def test_priced_in_assessment_coercion():
    from monika.application.analysis.schemas.pydantic_schemas import PricedInAssessment

    pi = PricedInAssessment.model_validate(
        {
            "dominant_driver": "Rate cut",
            "priced_in_score": "7/10",
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": "65%",
            "retail_sentiment_percentile": "40.5%",
        }
    )
    assert pi.priced_in_score == 7
    assert pi.cot_positioning_percentile == 65.0
    assert pi.retail_sentiment_percentile == 40.5


def test_submit_fundamental_brief_full_coercion():
    from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    payload = {
        "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
        "key_data_points_used": {
            "dxy_trend_5d": "strengthening +0.8%",
            "vix_close": "15.5",
            "fedwatch_dominant_pct": "85%",
            "treasury_10y_yield_pct": "4.25%",
            "cot_leveraged_long_pct": "58.4%",
        },
        "macro_narrative": "Detailed macro narrative describing the economic drivers...",
        "currency_bias": {
            "USD": "bullish",
            "EUR": "bearish",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "bearish",
        },
        "currency_confidence": {"USD": "80%", "EUR": "0.7", "XAU": 0.9},
        "confidence": "85%",
        "risk_sentiment": "risk-on",
        "macro_regime": "mixed",
        "priced_in_assessment": {
            "dominant_driver": "Fed cut",
            "priced_in_score": "6",
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": "75.0%",
        },
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
    from monika.application.analysis.schemas.pydantic_schemas import coerce_str, coerce_string_list

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
        "NFP Surprise",
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
    from monika.application.analysis.schemas.pydantic_schemas import SubmitAssetAnalysisSchema, EntryCondition

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
            {"event_name": "Jackson Hole Symposium", "currency": "USD", "impact": "high"},  # Index 5 is dict!
        ],
        "news_impact_assessment": {"impact": "High volatility expected around speech"},
    }

    schema = SubmitAssetAnalysisSchema.model_validate(payload)
    assert schema.symbol == "XAUUSD"
    assert len(schema.key_news_events_considered) == 6
    assert schema.key_news_events_considered[0] == "US CPI YoY 3.1%"
    assert "Jackson Hole Symposium" in schema.key_news_events_considered[5]
    assert "USD" in schema.key_news_events_considered[5]
    assert "Bullish OB mitigated" in schema.rationale or "macro" in schema.rationale


def test_upcoming_risk_events_coercion_robustness():
    from monika.application.analysis.schemas.pydantic_schemas import UpcomingRiskEvent

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


def test_inline_refs_preserves_nullable_numbers_for_gemini_tools():
    import jsonschema
    from monika.application.analysis.schemas import SubmitFundamentalBriefSchema, _inline_refs

    raw_schema = SubmitFundamentalBriefSchema.model_json_schema()
    inlined = _inline_refs(raw_schema)

    # Check that fedwatch_dominant_pct allows null / None
    fedwatch_prop = inlined["properties"]["key_data_points_used"]["properties"]["fedwatch_dominant_pct"]
    assert "type" in fedwatch_prop
    assert isinstance(fedwatch_prop["type"], list)
    assert "number" in fedwatch_prop["type"]
    assert "null" in fedwatch_prop["type"]

    # Validate a payload with None for nullable number fields using jsonschema
    payload = {
        "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
        "key_data_points_used": {
            "dxy_trend_5d": "strengthening +0.8%",
            "fedwatch_dominant_pct": None,
            "treasury_10y_yield_pct": None,
            "cot_leveraged_long_pct": 55.0,
            "vix_close": 16.0,
        },
        "macro_narrative": "Detailed macro narrative describing the economic drivers...",
        "currency_bias": {
            "USD": "bullish",
            "EUR": "bearish",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "bearish",
        },
        "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.9},
        "confidence": 0.85,
        "risk_sentiment": "risk-on",
        "macro_regime": "mixed",
        "priced_in_assessment": {
            "dominant_driver": "Fed cut",
            "priced_in_score": 6,
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": 75.0,
        },
        "strongest_counter_thesis": "Risiko skenario berlawanan: Jika kejutan data ekonomi riil berbalik arah drastis dari konsensus dan memicu repricing agresif ekspektasi kebijakan moneter.",
    }
    jsonschema.validate(instance=payload, schema=inlined)


def test_reevaluation_trigger_and_entry_condition_xml_and_string_coercion():
    from monika.application.analysis.schemas.pydantic_schemas import (
        ReevaluationTrigger,
        EntryCondition,
        SubmitAssetAnalysisSchema,
    )

    # 1. XML parameter string in ReevaluationTrigger
    xml_trig = '<parameter name="type">\nprice_level</parameter>\n<parameter name="detail">Wait until price breaks above 2450</parameter>'
    t1 = ReevaluationTrigger.model_validate(xml_trig)
    assert t1.type == "price_level"
    assert t1.price == 2450.0
    assert t1.direction == "above"

    # 2. Plain string in EntryCondition
    e1 = EntryCondition.model_validate("Wait for pullback to 1.0850")
    assert e1.type == "market"
    assert e1.detail == "Wait for pullback to 1.0850"

    # 3. SubmitAssetAnalysisSchema with XML trigger and string key news
    payload = {
        "symbol": "AUDUSD",
        "decision": "wait",
        "confidence": 0.65,
        "rationale": "Clear calendar, waiting for price structure breakout at lower levels.",
        "invalidation": "Thesis invalid if AUDUSD closes above 0.6700",
        "reevaluation_trigger": '<parameter name="type">\nprice_level',
        "key_news_events_considered": "No major news in last 6 hours. Economic calendar clear for AUD/USD.",
    }
    schema = SubmitAssetAnalysisSchema.model_validate(payload)
    assert schema.symbol == "AUDUSD"
    assert schema.decision == "wait"
    assert schema.reevaluation_trigger is not None
    assert schema.reevaluation_trigger.type == "time"
    assert schema.key_news_events_considered == ["No major news in last 6 hours. Economic calendar clear for AUD/USD."]


def test_submit_fundamental_brief_checklist_resilience():
    from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    base_payload = {
        "macro_narrative": "Comprehensive US disinflation narrative with solid labor conditions.",
        "currency_bias": {
            "USD": "bullish",
            "EUR": "bearish",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "bearish",
        },
        "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.9},
        "confidence": 0.85,
        "risk_sentiment": "risk-on",
        "macro_regime": "mixed",
        "key_data_points_used": {"dxy_trend_5d": "strengthening +0.8%", "vix_close": 15.5},
        "priced_in_assessment": {
            "dominant_driver": "Fed cut",
            "priced_in_score": 6,
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": 75.0,
        },
        "strongest_counter_thesis": "Risiko skenario berlawanan: Jika kejutan data ekonomi riil berbalik arah drastis dari konsensus dan memicu repricing agresif ekspektasi kebijakan moneter.",
    }

    # 1. Grok style: checklist omitted entirely
    obj1 = SubmitFundamentalBriefSchema.model_validate(base_payload)
    assert obj1.checklist.bias_vs_narrative_match is True
    assert obj1.checklist.contradiction_existed is False

    # 2. Stringified checklist (JSON string)
    payload_str_chk = dict(base_payload)
    payload_str_chk["checklist"] = '{"bias_vs_narrative_match": true, "contradiction_existed": true}'
    obj2 = SubmitFundamentalBriefSchema.model_validate(payload_str_chk)
    assert obj2.checklist.bias_vs_narrative_match is True
    assert obj2.checklist.contradiction_existed is True

    # 3. String booleans inside checklist dict
    payload_str_bools = dict(base_payload)
    payload_str_bools["checklist"] = {"bias_vs_narrative_match": "true", "contradiction_existed": "false"}
    obj3 = SubmitFundamentalBriefSchema.model_validate(payload_str_bools)
    assert obj3.checklist.bias_vs_narrative_match is True
    assert obj3.checklist.contradiction_existed is False


def test_fundamental_brief_transmission_matrix_and_usdjpy_inversion():
    """Verify that auto-healed per_asset_macro_matrix handles USDJPY without direction inversion."""
    from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    # Case A: USD bullish, JPY bearish -> USDJPY MUST be bullish/strong_bullish
    payload_a = {
        "macro_narrative": "USD bullish due to Fed hawkishness, JPY bearish due to dovish BOJ policy stance.",
        "currency_bias": {
            "USD": "bullish",
            "EUR": "bearish",
            "GBP": "neutral",
            "JPY": "bearish",
            "AUD": "neutral",
            "XAU": "bearish",
        },
        "confidence": 0.80,
        "risk_sentiment": "mixed",
        "macro_regime": "mixed",
        "strongest_counter_thesis": "Counter thesis: If US data softens and BOJ surprises with rate hike above 0.50% then bias inverts.",
    }
    brief_a = SubmitFundamentalBriefSchema.model_validate(payload_a)
    matrix_a = brief_a.per_asset_macro_matrix
    assert "USDJPY" in matrix_a
    assert matrix_a["USDJPY"].directional_bias in ("bullish", "strong_bullish")
    assert "EURUSD" in matrix_a
    assert matrix_a["EURUSD"].directional_bias in ("bearish", "strong_bearish")
    assert brief_a.yield_curve_regime == "neutral"
    assert brief_a.systemic_liquidity_trend == "neutral"

    # Case B: Both USD and JPY bearish -> USDJPY net differential is neutral, NOT bearish
    payload_b = {
        "macro_narrative": "Both USD and JPY softening due to broad risk-on capital rotation into commodities.",
        "currency_bias": {
            "USD": "bearish",
            "EUR": "bullish",
            "GBP": "neutral",
            "JPY": "bearish",
            "AUD": "bullish",
            "XAU": "bullish",
        },
        "confidence": 0.75,
        "risk_sentiment": "risk-on",
        "macro_regime": "risk_on",
        "strongest_counter_thesis": "Counter thesis: If risk sentiment reverses abruptly and safe havens surge then USD and JPY rally.",
    }
    brief_b = SubmitFundamentalBriefSchema.model_validate(payload_b)
    matrix_b = brief_b.per_asset_macro_matrix
    assert matrix_b["USDJPY"].directional_bias == "neutral"
    assert matrix_b["EURUSD"].directional_bias in ("bullish", "strong_bullish")


def test_submit_fundamental_brief_tool_schema_required_fields():
    """Verify that SUBMIT_FUNDAMENTAL_BRIEF tool schema requires per_asset_macro_matrix and transmission fields."""
    from monika.application.analysis.tools.tools_definitions import SUBMIT_FUNDAMENTAL_BRIEF

    schema = SUBMIT_FUNDAMENTAL_BRIEF["input_schema"]
    req = schema.get("required", [])
    for field in (
        "per_asset_macro_matrix",
        "asset_priced_in_scores",
        "yield_curve_regime",
        "systemic_liquidity_trend",
        "strongest_counter_thesis",
        "priced_in_assessment",
    ):
        assert field in req, f"Field '{field}' must be required in SUBMIT_FUNDAMENTAL_BRIEF schema"


def test_fundamental_brief_reverse_auto_healing_and_aliases():
    """Verify reverse auto-healing from per_asset_macro_matrix and pair/commodity alias resolution."""
    from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    # 1. Reverse auto-healing when currency_bias is empty but matrix is provided
    payload_matrix = {
        "macro_narrative": "Global macro cross-currents with strong US growth exceptionalism and commodity strength.",
        "per_asset_macro_matrix": {
            "EURUSD": {
                "directional_bias": "bearish",
                "structural_driver": "ECB cut",
                "tactical_catalyst": "PMI",
                "invalidation_level": "1.1000",
            },
            "GBPUSD": {
                "directional_bias": "bearish",
                "structural_driver": "BOE dovish",
                "tactical_catalyst": "CPI",
                "invalidation_level": "1.3000",
            },
            "USDJPY": {
                "directional_bias": "bullish",
                "structural_driver": "Yield gap",
                "tactical_catalyst": "BOJ",
                "invalidation_level": "150.00",
            },
            "AUDUSD": {
                "directional_bias": "neutral",
                "structural_driver": "RBA pause",
                "tactical_catalyst": "China",
                "invalidation_level": "0.6500",
            },
            "XAUUSD": {
                "directional_bias": "bullish",
                "structural_driver": "Safe haven",
                "tactical_catalyst": "Geopolitics",
                "invalidation_level": "2400.00",
            },
            "BTCUSD": {
                "directional_bias": "bullish",
                "structural_driver": "ETF inflow",
                "tactical_catalyst": "Halving",
                "invalidation_level": "60000.00",
            },
            "XTIUSD": {
                "directional_bias": "bearish",
                "structural_driver": "OPEC quota",
                "tactical_catalyst": "EIA",
                "invalidation_level": "70.00",
            },
        },
        "asset_priced_in_scores": {"XTIUSD": 8},
        "confidence": 0.80,
        "strongest_counter_thesis": "Counter thesis: If US growth abruptly stalls and Fed slashes rates by 100 bps immediately.",
    }
    brief = SubmitFundamentalBriefSchema.model_validate(payload_matrix)
    cb = brief.currency_bias
    assert cb["EUR"] == "bearish"
    assert cb["GBP"] == "bearish"
    assert cb["USD"] == "bullish"
    assert cb["JPY"] == "bearish"  # Inverted from USDJPY bullish
    assert cb["AUD"] == "neutral"
    assert cb["XAU"] == "bullish"
    assert cb["BTC"] == "bullish"
    assert cb["OIL"] == "bearish"
    assert "XBRUSD" in brief.per_asset_macro_matrix
    assert brief.asset_priced_in_scores["XBRUSD"] == 8  # Copied from XTIUSD

    # 2. Pair and commodity aliases in currency_bias
    payload_aliases = {
        "macro_narrative": "Macro overview using commodity and FX pair aliases instead of single currency codes.",
        "currency_bias": {
            "DXY": "bullish",
            "EURUSD": "bearish",
            "GBPUSD": "bearish",
            "USDJPY": "bullish",
            "GOLD": "bullish",
            "WTI": "bearish",
            "BITCOIN": "bullish",
            "AUDUSD": "neutral",
        },
        "confidence": 0.75,
        "strongest_counter_thesis": "Counter thesis: If geopolitical tensions collapse and global disinflation accelerates rapidly.",
    }
    brief_alias = SubmitFundamentalBriefSchema.model_validate(payload_aliases)
    cb_alias = brief_alias.currency_bias
    assert cb_alias["USD"] == "bullish"
    assert cb_alias["EUR"] == "bearish"
    assert cb_alias["GBP"] == "bearish"
    assert cb_alias["JPY"] == "bearish"
    assert cb_alias["XAU"] == "bullish"
    assert cb_alias["OIL"] == "bearish"
    assert cb_alias["BTC"] == "bullish"
    assert cb_alias["AUD"] == "neutral"


def test_fundamental_brief_validate_confidence_scales():
    """Verify that validate_confidence correctly normalizes both 1-10 and 10-100 scales."""
    from monika.application.analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema

    # 1-10 scale: confidence=5 -> 0.5, confidence=7.5 -> 0.75
    payload_scale_10 = {
        "macro_narrative": "Fundamental outlook test with 1-10 confidence scale inputs.",
        "currency_bias": {
            "USD": "neutral",
            "EUR": "neutral",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "neutral",
        },
        "confidence": 5.0,
        "currency_confidence": {"USD": 7.0, "EUR": 8.5},
        "strongest_counter_thesis": "Counter thesis: If unanticipated macro shocks hit sovereign debt markets with high volatility.",
    }
    b10 = SubmitFundamentalBriefSchema.model_validate(payload_scale_10)
    assert b10.confidence == 0.5
    assert b10.currency_confidence["USD"] == 0.7
    assert b10.currency_confidence["EUR"] == 0.85

    # 10-100 scale: confidence=85 -> 0.85
    payload_scale_100 = {
        "macro_narrative": "Fundamental outlook test with percentage 10-100 confidence scale inputs.",
        "currency_bias": {
            "USD": "neutral",
            "EUR": "neutral",
            "GBP": "neutral",
            "JPY": "neutral",
            "AUD": "neutral",
            "XAU": "neutral",
        },
        "confidence": 85.0,
        "currency_confidence": {"USD": 90.0, "EUR": 65.0},
        "strongest_counter_thesis": "Counter thesis: If unanticipated macro shocks hit sovereign debt markets with high volatility.",
    }
    b100 = SubmitFundamentalBriefSchema.model_validate(payload_scale_100)
    assert b100.confidence == 0.85
    assert b100.currency_confidence["USD"] == 0.90
    assert b100.currency_confidence["EUR"] == 0.65


def test_phase11_pydantic_hardening_invariants():
    import math
    import pytest
    from pydantic import ValidationError
    from monika.application.analysis.schemas import (
        coerce_float,
        coerce_int,
        coerce_string_list,
        SubmitAssetAnalysisSchema,
    )

    # 1. NaN and Inf rejection
    assert coerce_int(float("nan")) is None
    assert coerce_int(float("inf")) is None
    assert coerce_int(float("-inf")) is None
    assert coerce_float(float("nan")) is None
    assert coerce_float(float("inf")) is None
    assert coerce_float(float("-inf")) is None

    # 2. String list prefix stripping doesn't corrupt prices
    assert coerce_string_list("1.0850 target level") == ["1.0850 target level"]
    assert coerce_string_list("1. Validated level\n2. Another level") == ["Validated level", "Another level"]
    assert coerce_string_list("- Bullet point") == ["Bullet point"]

    # 3. Confluence score bounds [0, 14]
    with pytest.raises(ValidationError):
        SubmitAssetAnalysisSchema(
            symbol="EURUSD", decision="wait", confidence=0.7, rationale="Test", invalidation="Test", confluence_score=15
        )
    with pytest.raises(ValidationError):
        SubmitAssetAnalysisSchema(
            symbol="EURUSD", decision="wait", confidence=0.7, rationale="Test", invalidation="Test", confluence_score=-1
        )


def test_priced_in_override_and_specialist_adjudication_resilience():
    """Verify robust handling of priced_in_override_justification and specialist_adjudication."""
    import pytest
    from pydantic import ValidationError
    from monika.application.analysis.schemas import (
        PricedInOverrideJustification,
        SpecialistAdjudication,
        SubmitAssetAnalysisSchema,
    )

    # 1. SpecialistAdjudication non-conflict strings coerce cleanly without detecting conflict
    for s in ["no conflict", "none", "n/a", "not applicable", "none needed", "no disagreement"]:
        sa = SpecialistAdjudication.model_validate(s)
        assert sa.conflict_detected is False
        assert SubmitAssetAnalysisSchema.validate_specialist_adjudication_field(s) is None

    # Substantive conflict string creates conflict detection
    conflict_s = "Strong divergence between technical H4 structure and daily macro trend"
    sa_conflict = SpecialistAdjudication.model_validate(conflict_s)
    assert sa_conflict.conflict_detected is True
    assert sa_conflict.resolution_path == "cancel_setup"

    # 2. PricedInOverrideJustification non-applicable indicators normalize to None
    for s in ["not applicable", "no override", "none needed", "not needed", "none", "n/a", "null"]:
        assert SubmitAssetAnalysisSchema.validate_override_justification_field(s) is None

    # Substantive string expands into structured model
    substantive_str = "Fresh institutional order flow absorbed the sell side liquidity completely"
    p_obj = PricedInOverrideJustification.model_validate(substantive_str)
    assert p_obj.override_reason == substantive_str
    assert "superseded" in p_obj.why_stage1_wrong

    # Short/trivial string raises ValueError in direct model instantiation
    with pytest.raises(ValueError, match="too short"):
        PricedInOverrideJustification.model_validate("short string")

    # 3. Aliasing for substantive override keys
    d_alias = {
        "justification": "Market repriced on unexpected GDP growth numbers",
        "detail": "Prior news completely faded",
        "post_event_evidence": "Breakout confirmed on high volume",
    }
    p_alias = PricedInOverrideJustification.model_validate(d_alias)
    assert p_alias.override_reason == "Market repriced on unexpected GDP growth numbers"

    # 4. Fail-closed safety invariant: score >= 8 without override MUST raise ValidationError for buy/sell
    with pytest.raises(ValidationError):
        SubmitAssetAnalysisSchema(
            symbol="EURUSD",
            decision="buy",
            direction="buy",
            confidence=0.8,
            confluence_score=10,
            confluence_factors=["h4_trend_aligned"],
            timeframe="H1",
            entry_condition={"type": "market", "detail": "buy now"},
            stop_loss=1.0500,
            take_profit=1.0700,
            rationale="Strong trend",
            invalidation="Break 1.0500",
            macro_narrative="Bullish euro",
            risk_sentiment="risk-on",
            macro_regime="risk_on",
            checklist={"bias_vs_narrative_match": True, "contradiction_existed": False},
            reevaluation_trigger={"type": "time", "detail": "tomorrow"},
            strongest_counter_thesis="Counter thesis detail",
            priced_in_score=9,
            priced_in_override_justification={"override_reason": None},
        )

    # 5. Exact warning log reproduction: wait decision with empty override fields normalizes to None and succeeds!
    payload_exact = {
        "symbol": "BTCUSD",
        "decision": "wait",
        "confidence": 0.7,
        "confluence_score": 6,
        "confluence_factors": ["h4_trend_aligned"],
        "timeframe": "H1",
        "entry_condition": {"type": "market", "detail": "wait for pullback"},
        "stop_loss": 60000.0,
        "take_profit": 70000.0,
        "rationale": "Consolidating near resistance",
        "invalidation": "Break 60000",
        "macro_narrative": "Crypto consolidating",
        "risk_sentiment": "mixed",
        "macro_regime": "mixed",
        "checklist": {"bias_vs_narrative_match": True, "contradiction_existed": False},
        "reevaluation_trigger": {"type": "time", "detail": "next 4h bar"},
        "strongest_counter_thesis": "Could break resistance earlier",
        "priced_in_score": 2,
        "priced_in_override_justification": {
            "override_reason": None,
            "why_stage1_wrong": None,
            "post_event_evidence": None,
        },
    }
    res_s = SubmitAssetAnalysisSchema.model_validate(payload_exact)
    assert res_s.priced_in_override_justification is None
