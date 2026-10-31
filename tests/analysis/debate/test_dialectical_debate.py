import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.application.analysis.debate.adjustment_validator import validate_and_apply_judge_adjustments
from monika.application.analysis.debate.bear_analyst import generate_bear_dissent
from monika.application.analysis.debate.bull_analyst import generate_bull_advocacy
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.infrastructure.database.models import AssetAnalysis


@pytest.mark.asyncio
async def test_bull_advocacy_handles_conflict_adjudication():
    """Bull Advocate should formulate valid Long proposal when decision is conflicted (WAIT)."""
    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value=MagicMock(
            text=json.dumps(
                {
                    "thesis": "H1 Bullish Order Block in Deep Discount",
                    "strength_score": 8,
                    "proposed_entry": 1.0850,
                    "proposed_sl": 1.0800,
                    "proposed_tp": 1.0950,
                    "rr_ratio": 2.0,
                    "macro_rebuttal": "USD rate cuts imminent, technical breaker invalidates dollar strength.",
                    "evidence_cited": ["Discount dealing range (0.35)", "Unmitigated FVG"],
                }
            )
        )
    )

    original_context = {
        "decision": "WAIT",
        "rationale": "Bullish technical structure diverges from bearish macro brief.",
        "confluence_score": 7,
    }

    claim = await generate_bull_advocacy(
        mock_client,
        symbol="EURUSD",
        original_context=original_context,
        fact_sheet={"price": 1.0850, "atr": 0.0040},
    )

    assert claim["strength_score"] == 8
    assert claim["proposed_entry"] == 1.0850
    assert claim["proposed_sl"] == 1.0800
    assert claim["proposed_tp"] == 1.0950
    assert claim["rr_ratio"] == 2.0


@pytest.mark.asyncio
async def test_bear_dissent_handles_conflict_adjudication():
    """Bear Dissenter should formulate valid Short proposal when technicals are overbought/premium."""
    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value=MagicMock(
            text=json.dumps(
                {
                    "bear_dissent": "Liquidity sweep above Asian session high into H4 Premium Bearish OB.",
                    "risk_severity": 7,
                    "proposed_entry": 2650.0,
                    "proposed_sl": 2675.0,
                    "proposed_tp": 2600.0,
                    "rr_ratio": 2.0,
                    "structural_thesis": "Bearish breaker block confirmed on H1.",
                    "evidence_cited": ["Premium location (0.75)", "H4 rejection wick"],
                }
            )
        )
    )

    original_context = {
        "decision": "WAIT",
        "rationale": "Bearish technical structure diverges from bullish macro brief.",
        "confluence_score": 7,
    }

    dissent = await generate_bear_dissent(
        mock_client,
        symbol="XAUUSD",
        original_context=original_context,
        bull_claim={"thesis": "Macro safe haven", "strength_score": 6},
        fact_sheet="Price: 2650.0, ATR: 20.0",
    )

    assert dissent["risk_severity"] == 7
    assert dissent["proposed_entry"] == 2650.0
    assert dissent["proposed_sl"] == 2675.0
    assert dissent["proposed_tp"] == 2600.0
    assert dissent["rr_ratio"] == 2.0


@pytest.mark.asyncio
async def test_investment_judge_conflict_resolution():
    """Investment Judge resolves conflicted setup to BUY when Bull thesis is grounded in discount."""
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(
        return_value={
            "final_decision": "buy",
            "confidence": 0.75,
            "risk_multiplier": 0.65,
            "reason": "Technical discount breaker confirmed; macro USD strength is lagging.",
            "adjusted_entry": 1.0850,
            "adjusted_sl": 1.0800,
            "adjusted_tp": 1.0950,
        }
    )

    verdict = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "WAIT", "market_regime": "trending_bull", "vix": 16.0},
        bull_claim={
            "strength_score": 8,
            "proposed_entry": 1.0850,
            "proposed_sl": 1.0800,
            "proposed_tp": 1.0950,
            "rr_ratio": 2.0,
        },
        bear_dissent={"risk_severity": 5, "evidence_cited": ["Macro rate differential"]},
    )

    assert verdict["final_decision"] == "buy"
    assert verdict["confidence"] == 0.75
    assert verdict["risk_multiplier"] == 0.65
    assert verdict["adjusted_entry"] == 1.0850


@pytest.mark.asyncio
async def test_validate_and_apply_judge_adjustments_uses_verdict_direction():
    """Adjustment validator should use verdict['final_decision'] to validate geometry correctly."""
    mock_session = AsyncMock()
    # Mock ATR query
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    ana = AssetAnalysis(
        symbol="EURUSD",
        decision="wait",  # Original decision was WAIT
        stop_loss=1.0800,
        take_profit=1.0950,
    )

    verdict = {
        "final_decision": "buy",
        "adjusted_entry": 1.0850,
        "adjusted_sl": 1.0800,
        "adjusted_tp": 1.0950,
    }

    # Should succeed because for BUY: SL (1.0800) < Entry (1.0850) < TP (1.0950), R:R = 2.0
    is_valid, err = await validate_and_apply_judge_adjustments(
        session=mock_session,
        ana=ana,
        verdict=verdict,
        settings={"trading": {"risk": {"min_rr_ratio": 1.5}}},
        entry_zone_data={"price": 1.0850},
    )

    assert is_valid is True
    assert err == ""
