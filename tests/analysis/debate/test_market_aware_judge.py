import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from monika.application.analysis.debate.investment_judge import (
    REGIME_WEIGHT_MATRIX,
    evaluate_debate,
    resolve_regime_weights,
)


def test_resolve_regime_weights_trending():
    assert "trending" in REGIME_WEIGHT_MATRIX
    weights = resolve_regime_weights({"market_regime": "trending_bull", "vix": 16.5})
    assert weights["detected_regime"] == "trending"
    assert weights["trend_thesis_weight"] == 0.65
    assert weights["counter_thesis_weight"] == 0.35
    assert weights["volatility_penalty"] == 0.0


def test_resolve_regime_weights_ranging():
    weights = resolve_regime_weights({"regime": "ranging_chop", "vix": 18.0})
    assert weights["detected_regime"] == "ranging"
    assert weights["trend_thesis_weight"] == 0.50
    assert weights["counter_thesis_weight"] == 0.50
    assert weights["volatility_penalty"] == 0.10


def test_resolve_regime_weights_volatile_via_vix():
    weights = resolve_regime_weights({"market_regime": "trending", "vix": 28.5})
    # VIX >= 25 elevates to volatile
    assert weights["detected_regime"] == "volatile"
    assert weights["trend_thesis_weight"] == 0.30
    assert weights["counter_thesis_weight"] == 0.70
    assert weights["volatility_penalty"] == 0.20


@pytest.mark.asyncio
async def test_evaluate_debate_in_volatile_regime_rejects_on_moderate_bear_severity():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(
        return_value={
            "final_decision": "buy",
            "reason": "Technical breakout has momentum",
            "risk_multiplier": 0.60,
            "adjusted_entry": None,
            "adjusted_sl": None,
            "adjusted_tp": None,
        }
    )

    # In volatile regime, bear_severity 7 triggers avoid veto
    verdict = await evaluate_debate(
        mock_client,
        symbol="XAUUSD",
        original_context={"decision": "buy", "market_regime": "volatile_shock", "vix": 31.0},
        bull_claim={"strength_score": 7},
        bear_dissent={"risk_severity": 7, "evidence_cited": ["VIX spike above 30"]},
        bull_rebuttal=None,
    )

    assert verdict["final_decision"] == "avoid"
    assert verdict["risk_multiplier"] == 0.0
    assert verdict["regime_weights_used"]["detected_regime"] == "volatile"


@pytest.mark.asyncio
async def test_evaluate_debate_in_volatile_regime_applies_volatility_penalty():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(
        return_value={
            "final_decision": "buy",
            "reason": "Strong low-volatility counter trend or safe setup",
            "risk_multiplier": 0.80,
            "adjusted_entry": None,
            "adjusted_sl": None,
            "adjusted_tp": None,
        }
    )

    # Bear severity 4 (low) does not trigger veto, but volatility penalty (0.20) is deducted
    verdict = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "buy", "volatility_regime": "volatile", "vix": 26.0},
        bull_claim={"strength_score": 8},
        bear_dissent={"risk_severity": 4},
        bull_rebuttal=None,
    )

    assert verdict["final_decision"] == "buy"
    # 0.80 - 0.20 = 0.60
    assert abs(verdict["risk_multiplier"] - 0.60) < 1e-4
    assert verdict["regime_weights_used"]["detected_regime"] == "volatile"


@pytest.mark.asyncio
async def test_evaluate_debate_fallback_preserves_regime_weights():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(side_effect=RuntimeError("LLM API timeout"))

    verdict = await evaluate_debate(
        mock_client,
        symbol="GBPUSD",
        original_context={"decision": "sell", "market_regime": "trending"},
        bull_claim={"strength_score": 6},
        bear_dissent={"risk_severity": 5},
    )

    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert verdict["regime_weights_used"]["detected_regime"] == "trending"


@pytest.mark.asyncio
async def test_evaluate_debate_generate_content_empty_response_fallback():
    mock_client = MagicMock(spec=["generate_content"])
    mock_client.generate_content = AsyncMock(return_value="")

    verdict = await evaluate_debate(
        mock_client,
        symbol="XAUUSD",
        original_context={"decision": "buy", "market_regime": "ranging"},
        bull_claim={"strength_score": 5},
        bear_dissent={"risk_severity": 5},
    )

    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert "Empty or invalid response" in verdict["reason"]


@pytest.mark.asyncio
async def test_evaluate_debate_generate_content_empty_response_decisive_fallback():
    mock_client = MagicMock(spec=["generate_content"])
    mock_client.generate_content = AsyncMock(return_value="")

    # When pro-strength (6) outweighs counter-threat (4) by >= 2, apply defensive algorithmic fallback
    verdict = await evaluate_debate(
        mock_client,
        symbol="XAUUSD",
        original_context={"decision": "buy", "market_regime": "ranging"},
        bull_claim={"strength_score": 6},
        bear_dissent={"risk_severity": 4},
    )

    assert verdict["final_decision"] == "buy"
    assert verdict["risk_multiplier"] == 0.40
    assert "Algorithmic fallback adjudication" in verdict["reason"]


@pytest.mark.asyncio
async def test_evaluate_debate_generate_content_success():
    mock_client = MagicMock(spec=["generate_content"])
    json_body = json.dumps(
        {
            "final_decision": "buy",
            "reason": "Clear market structure with positive risk-reward",
            "risk_multiplier": 0.85,
        }
    )
    mock_client.generate_content = AsyncMock(return_value=f"```json\n{json_body}\n```")

    verdict = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "buy", "market_regime": "trending"},
        bull_claim={"strength_score": 8},
        bear_dissent={"risk_severity": 3},
    )

    assert verdict.get("parse_error") is not True
    assert verdict["final_decision"] == "buy"
    assert verdict["risk_multiplier"] == 0.85


@pytest.mark.asyncio
async def test_evaluate_debate_client_without_methods_fallback():
    # Client with neither classify_json nor generate_content
    class EmptyClient:
        pass

    verdict = await evaluate_debate(
        EmptyClient(),
        symbol="BTCUSD",
        original_context={"decision": "sell", "market_regime": "ranging"},
        bull_claim={"strength_score": 5},
        bear_dissent={"risk_severity": 6},
    )

    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert "Empty or invalid response" in verdict["reason"]


@pytest.mark.asyncio
async def test_build_fact_sheet_populates_synergy_regime_and_bracket_options():
    from monika.application.analysis.debate.fact_sheet import build_fact_sheet
    from monika.infrastructure.database.models import AssetAnalysis

    ana = AssetAnalysis(
        id=999,
        symbol="EURUSD",
        decision="buy",
        price_at_analysis=1.1020,
        entry_zone=json.dumps({"price": 1.1020}),
        stop_loss=1.0940,
        take_profit=1.1140,
        confluence_score=10,
        confluence_factors_json=json.dumps(["H4_OB", "DISCOUNT"]),
        rationale="Discount accumulation with uncrowded institutional synergy",
        specialist_biases_json=json.dumps(
            {"biases": {"technical": "bullish", "sentiment": "bearish", "macro": "bullish"}}
        ),
    )

    atr_row = MagicMock()
    atr_row.value_json = json.dumps({"atr": 0.0080})

    class DummyCandle:
        def __init__(self, h, l, c):
            self.high = h
            self.low = l
            self.close = c

    # Newest-first (descending timestamp) H4 candles
    h4_candles_desc = [
        DummyCandle(1.1050, 1.1000, 1.1020),
        DummyCandle(1.1080, 1.1010, 1.1040),
        DummyCandle(1.1150, 1.1040, 1.1060),
        DummyCandle(1.1200, 1.1000, 1.1100),
    ]

    call_idx = {"n": 0}

    async def fake_execute(stmt):
        call_idx["n"] += 1
        res = MagicMock()
        if call_idx["n"] == 1:
            res.scalar_one_or_none = lambda: atr_row
            res.scalars = lambda: MagicMock(all=lambda: [])
        elif "price_ohlcv" in str(stmt).lower():
            res.scalars = lambda: MagicMock(all=lambda: list(h4_candles_desc))
            res.scalar_one_or_none = lambda: None
        else:
            res.scalar_one_or_none = lambda: None
            res.scalars = lambda: MagicMock(all=lambda: [])
        return res

    session = MagicMock()
    session.execute = AsyncMock(side_effect=fake_execute)

    fs = await build_fact_sheet(session, ana)

    assert fs["atr"] == pytest.approx(0.0080)
    assert fs["atr_14_h4"] == pytest.approx(0.0080)
    assert "dealing_range_pos" in fs
    assert fs["dealing_range_pos"] == pytest.approx(0.10, abs=1e-3)
    assert "h4_impulse_atr" in fs
    assert fs["specialist_consensus"]["synergy_state"] == "uncrowded_institutional_synergy"
    assert fs["specialist_consensus"]["biases"]["technical"] == "bullish"
    assert fs["regime_classification"] == "DISCOUNT_ACCUMULATION_ZONE"
    assert "daily_range_context" in fs
    assert "bracket_options" in fs
    assert "long_option_a" in fs["bracket_options"]
    assert "short_option_b" in fs["bracket_options"]
