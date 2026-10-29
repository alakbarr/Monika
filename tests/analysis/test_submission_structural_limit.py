"""Unit tests verifying structural limit orders during squeeze and multi-key price parsing in analysis_submission.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import create_mock_async_session
from monika.application.analysis.tools.executor import ToolExecutor
from monika.infrastructure.database.models import PriceOHLCV


@pytest.mark.asyncio
async def test_submission_allows_structural_limit_during_chop_squeeze():
    """Verify that during a Bollinger squeeze/chop block, structural limit orders are allowed without GATE error."""
    session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "macro_bias": {"enabled": False},
                "volatility_regime": {"enabled": True},
            },
            "risk": {
                "min_rr_ratio": 1.3,
                "intraday_range_strategy_enabled": False,
            },
        }
    }

    tool = ToolExecutor(session=session, settings=settings, symbol="EURUSD")
    # Satisfy monotonic read-before-act & mandatory calculation guards
    tool.called_tools.add("get_price_history")
    tool.called_tools.add("calculate_position_size")

    # Mock compute_bollinger_donchian_chop returning chop_block = True
    mock_chop = {
        "chop_block": True,
        "reason": "Bollinger squeeze 18th percentile (compression)",
    }

    mock_bar = MagicMock(spec=PriceOHLCV)
    mock_bar.close = 1.0855

    # Mock session execute scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_bar
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    inp = {
        "symbol": "EURUSD",
        "decision": "buy",
        "confluence_score": 7,
        "confluence_factors": ["fundamental_bias", "dxy_confirms", "d1_trend", "near_fvg"],
        "confidence": 0.75,
        "priced_in_score": 2,
        "invalidation_price": 1.0800,
        "invalidation_direction": "below",
        "entry_condition": {
            "type": "limit_order",
            "price_low": 1.0850,
            "description": "Pending limit at unmitigated FVG",
        },
        "entry_price": 1.0850,
        "stop_loss": 1.0800,
        "take_profit": 1.0950,
        "invalidation": "H4 candle closes below 1.0800",
        "rationale": "High-confluence structural limit setup at unmitigated FVG with DXY alignment.",
    }

    with (
        patch(
            "monika.application.analysis.calculators.regime_classifier.compute_bollinger_donchian_chop",
            AsyncMock(return_value=mock_chop),
        ),
        patch(
            "monika.application.analysis.calculators.unified_threshold_calculator.compute_unified_confluence_threshold",
            AsyncMock(return_value=(6, "Normal session")),
        ),
        patch(
            "monika.application.analysis.calculators.confluence_calculator.calculate_confluence",
            AsyncMock(return_value={"computed_score": 7}),
        ),
        patch.object(tool, "_get_dynamic_atr_fallback", AsyncMock(return_value=0.0020)),
        patch.object(tool, "_cross_validate_priced_in", AsyncMock(return_value=(inp["rationale"], None))),
        patch.object(tool, "_cross_validate_directional_coherence", AsyncMock(return_value=inp["rationale"])),
        patch.object(tool, "_validate_ssvp_and_context_drift", AsyncMock(return_value=("snap_1", 0.85))),
    ):
        res = await tool.execute("submit_asset_analysis", inp)

    assert res.get("decision") == "buy"
    assert res.get("status") == "saved"
    assert res.get("symbol") == "EURUSD"


@pytest.mark.asyncio
async def test_submission_allows_wait_decision_during_chop_squeeze():
    """Verify that during a Bollinger squeeze/chop block, submitting decision='wait' succeeds without GATE error."""
    session = create_mock_async_session()
    settings = {
        "trading": {
            "edge_strategy": {
                "macro_bias": {"enabled": False},
                "volatility_regime": {"enabled": True},
            },
            "risk": {
                "min_rr_ratio": 1.3,
                "intraday_range_strategy_enabled": False,
            },
        }
    }

    tool = ToolExecutor(session=session, settings=settings, symbol="EURUSD")
    # Satisfy monotonic read-before-act guard (reading price/volatility data)
    tool.called_tools.add("get_price_history")

    # Mock compute_bollinger_donchian_chop returning chop_block = True
    mock_chop = {
        "chop_block": True,
        "reason": "Bollinger squeeze 15th percentile (compression)",
    }

    mock_bar = MagicMock(spec=PriceOHLCV)
    mock_bar.close = 1.0855

    # Mock session execute scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_bar
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    inp = {
        "symbol": "EURUSD",
        "decision": "wait",
        "confidence": 0.40,
        "rationale": "Market is consolidating in tight Bollinger squeeze. Waiting for breakout or expansion.",
        "invalidation": "H4 candle closes above 1.0900 or below 1.0800",
        "reevaluation_trigger": {
            "type": "time",
            "hours": 4,
            "detail": "Re-evaluate when volatility expands",
        },
    }

    mock_chop_fn = AsyncMock(return_value=mock_chop)
    with (
        patch(
            "monika.application.analysis.calculators.regime_classifier.compute_bollinger_donchian_chop",
            mock_chop_fn,
        ),
        patch.object(tool, "_cross_validate_priced_in", AsyncMock(return_value=(inp["rationale"], None))),
        patch.object(tool, "_cross_validate_directional_coherence", AsyncMock(return_value=inp["rationale"])),
        patch.object(tool, "_validate_ssvp_and_context_drift", AsyncMock(return_value=("snap_1", 0.85))),
    ):
        res = await tool.execute("submit_asset_analysis", inp)

    assert res.get("status") == "saved"
    assert res.get("decision") == "wait"
    assert res.get("symbol") == "EURUSD"
    assert "errors" not in res
    assert "Analysis saved successfully." in res.get("message", "")
    # Volatility regime gate should not even invoke chop calculation for wait decision
    mock_chop_fn.assert_not_called()


@pytest.mark.asyncio
async def test_submission_cleans_and_bounds_long_playbook_id():
    """Verify that submit_asset_analysis cleans commentary and bounds long playbook_id/source_strategy_id."""
    session = create_mock_async_session()
    settings = {"trading": {"risk": {}}}

    tool = ToolExecutor(session=session, settings=settings, symbol="USDJPY")
    tool.called_tools.add("get_price_history")

    long_commentary_id = (
        "usdjpy_jpy_tokyo_ema25_bounce_playbook (triggered but REJECTED - its SL 157.862 is only 0.43x H4 ATR, "
        "violating the mandatory 1.0x ATR buffer)"
    )

    inp = {
        "symbol": "USDJPY",
        "decision": "wait",
        "confidence": 0.65,
        "priced_in_score": 5,
        "invalidation": "Long-side thesis invalidated by H4 close below 157.698",
        "rationale": "USDJPY waiting for compliant bracket.",
        "playbook_id": long_commentary_id,
    }

    added_objects = []
    session.add = lambda obj: added_objects.append(obj)

    with (
        patch.object(tool, "_cross_validate_priced_in", AsyncMock(return_value=(inp["rationale"], None))),
        patch.object(tool, "_cross_validate_directional_coherence", AsyncMock(return_value=inp["rationale"])),
        patch.object(tool, "_validate_ssvp_and_context_drift", AsyncMock(return_value=("snap_1", 0.85))),
    ):
        res = await tool.execute("submit_asset_analysis", inp)

    assert res.get("status") == "saved"
    assert res.get("decision") == "wait"
    assert len(added_objects) > 0
    saved_analysis = added_objects[0]
    assert saved_analysis.source_strategy_id == "usdjpy_jpy_tokyo_ema25_bounce_playbook"
    assert len(saved_analysis.source_strategy_id) <= 50

    # Also test none_executed pattern
    tool2 = ToolExecutor(session=session, settings=settings, symbol="AUDUSD")
    tool2.called_tools.add("get_price_history")
    added_objects.clear()

    inp2 = {
        "symbol": "AUDUSD",
        "decision": "wait",
        "confidence": 0.72,
        "priced_in_score": 2,
        "invalidation": "H4 close < 0.70457",
        "rationale": "AUDUSD waiting.",
        "playbook_id": "none_executed__audusd_sydney_fade_bb15_playbook_rejected",
    }
    with (
        patch.object(tool2, "_cross_validate_priced_in", AsyncMock(return_value=(inp2["rationale"], None))),
        patch.object(tool2, "_cross_validate_directional_coherence", AsyncMock(return_value=inp2["rationale"])),
        patch.object(tool2, "_validate_ssvp_and_context_drift", AsyncMock(return_value=("snap_2", 0.85))),
    ):
        res2 = await tool2.execute("submit_asset_analysis", inp2)

    assert res2.get("status") == "saved"
    saved_analysis2 = added_objects[0]
    assert saved_analysis2.source_strategy_id is None
