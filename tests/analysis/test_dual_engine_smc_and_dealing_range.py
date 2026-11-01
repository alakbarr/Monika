# ==============================================================================
# File: tests/analysis/test_dual_engine_smc_and_dealing_range.py
# ==============================================================================

"""
Unit and integration tests for Dual-Engine Institutional SMC,
3-Zone Dealing Range spatial pre-computation, and Dialectical Debate routing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.stages.per_asset.context_builder import ContextBuilder
from monika.application.analysis.tools.executor import ToolExecutor
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_investment_judge_contains_dual_engine_and_3zone_rules():
    """Verify that the Investment Judge prompt incorporates the 3-zone dealing range and dual-engine rules."""
    mock_client = MagicMock(spec=["generate_content"])
    mock_client.generate_content = AsyncMock(
        return_value=json.dumps(
            {
                "reason": "Deep discount with confirmed liquidity sweep validates long.",
                "regime_weights_used": {},
                "risk_multiplier": 0.75,
                "adjusted_entry": None,
                "adjusted_sl": None,
                "adjusted_tp": None,
                "final_decision": "buy",
            }
        )
    )

    verdict = await evaluate_debate(
        client=mock_client,
        symbol="BTCUSD",
        original_context={"symbol": "BTCUSD", "decision": "WAIT"},
        bull_claim={"strength_score": 8, "evidence": ["Deep discount 0.18", "Sweep of low"]},
        bear_dissent={"risk_severity": 6, "counter_arguments": ["Macro headwind"]},
    )

    assert verdict["final_decision"] == "buy"
    assert verdict["risk_multiplier"] == 0.75

    # Verify the prompt sent to the LLM contains the 3-zone and dual-engine rules
    prompt_sent = mock_client.generate_content.call_args.kwargs.get("user_message", "")
    assert "DEEP DISCOUNT (dealing range pos <= 0.35)" in prompt_sent
    assert "DEEP PREMIUM (dealing range pos >= 0.65)" in prompt_sent
    assert "EQUILIBRIUM REGIME (0.35 < pos < 0.65)" in prompt_sent
    assert "Engine 1 (Macro-Aligned/Neutral)" in prompt_sent
    assert "Engine 2 (Contra-Macro)" in prompt_sent
    assert "R:R >= 1.75" in prompt_sent
    assert "R:R >= 2.00" in prompt_sent


@pytest.mark.asyncio
async def test_context_builder_spatial_anchor_deep_discount():
    """Verify that ContextBuilder pre-computes Deep Discount spatial coordinates."""
    mock_session = create_mock_async_session()

    from monika.infrastructure.database.models import FundamentalBrief, PriceOHLCV

    # Mock 20 daily bars: Low=100.0, High=200.0, Close=110.0 -> pos = (110 - 100) / 100 = 0.10 (DEEP DISCOUNT)
    bars = []
    base_ts = datetime(2026, 10, 30, tzinfo=timezone.utc)
    for i in range(20):
        bars.append(
            PriceOHLCV(
                symbol="EURUSD",
                timeframe="D1",
                timestamp=base_ts,
                open=115.0,
                high=200.0 if i == 5 else 130.0,
                low=100.0 if i == 10 else 105.0,
                close=110.0 if i == 0 else 115.0,
                volume=1000.0,
            )
        )

    mock_brief = FundamentalBrief(
        id=1,
        generated_at=base_ts,
        confidence=0.80,
        structured_json=json.dumps(
            {
                "per_asset_macro_matrix": {
                    "EURUSD": {
                        "directional_bias": "bullish",
                        "confidence": 0.80,
                        "time_horizon": "swing",
                        "structural_driver": "ECB policy divergence",
                        "tactical_catalyst": "PMI surprise",
                        "invalidation_level": "1.0700",
                    }
                },
                "asset_priced_in_scores": {"EURUSD": 4},
            }
        ),
    )

    row_mock = MagicMock()
    row_mock.total_trades = 0
    row_mock.winning_trades = 0

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        res.first.return_value = row_mock
        if "fundamental_brief" in query:
            res.scalar_one_or_none.return_value = mock_brief
            res.scalars.return_value.all.return_value = [mock_brief]
        elif "price_ohlcv" in query:
            res.scalar_one_or_none.return_value = bars[0]
            res.scalars.return_value.all.return_value = bars
        elif "order_block" in query:
            res.scalars.return_value.all.return_value = []
        elif "vix_data" in query:
            res.scalar_one_or_none.return_value = None
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    builder = ContextBuilder(settings={"trading": {"risk": {}}})
    with patch(
        "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
        new=AsyncMock(return_value={"sweep_detected": False}),
    ):
        blocks = await builder._build_stage2_context_blocks(
            session=mock_session,
            symbol="EURUSD",
            brief_check=mock_brief,
            start_time=base_ts,
            extra_context=None,
            stage1_confidence=0.80,
            coherence_injection="",
        )

    anchor_block = next((b[1] for b in blocks if b[0] == "TARGET ASSET MACRO ANCHOR"), None)
    assert anchor_block is not None
    assert "Range Position Ratio: 0.10 (DEEP DISCOUNT)" in anchor_block
    assert "Spatial Status: ACCUMULATION ZONE (BUY eligible)" in anchor_block


@pytest.mark.asyncio
async def test_context_builder_spatial_anchor_equilibrium_dead_zone():
    """Verify that ContextBuilder labels middle-range chop as EQUILIBRIUM DEAD ZONE."""
    mock_session = create_mock_async_session()

    from monika.infrastructure.database.models import FundamentalBrief, PriceOHLCV

    # Mock 20 daily bars: Low=100.0, High=200.0, Close=150.0 -> pos = (150 - 100) / 100 = 0.50 (EQUILIBRIUM CHOP)
    bars = []
    base_ts = datetime(2026, 10, 30, tzinfo=timezone.utc)
    for i in range(20):
        bars.append(
            PriceOHLCV(
                symbol="GBPUSD",
                timeframe="D1",
                timestamp=base_ts,
                open=150.0,
                high=200.0 if i == 5 else 160.0,
                low=100.0 if i == 10 else 140.0,
                close=150.0,
                volume=1000.0,
            )
        )

    row_mock = MagicMock()
    row_mock.total_trades = 0
    row_mock.winning_trades = 0

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        res.first.return_value = row_mock
        if "fundamental_brief" in query:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        elif "price_ohlcv" in query:
            res.scalar_one_or_none.return_value = bars[0]
            res.scalars.return_value.all.return_value = bars
        elif "order_block" in query:
            res.scalars.return_value.all.return_value = []
        elif "vix_data" in query:
            res.scalar_one_or_none.return_value = None
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)

    builder = ContextBuilder(settings={"trading": {"risk": {}}})
    with patch(
        "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
        new=AsyncMock(return_value={"sweep_detected": False}),
    ):
        blocks = await builder._build_stage2_context_blocks(
            session=mock_session,
            symbol="GBPUSD",
            brief_check=None,
            start_time=base_ts,
            extra_context=None,
            stage1_confidence=0.50,
            coherence_injection="",
        )

    anchor_block = next((b[1] for b in blocks if b[0] == "TARGET ASSET MACRO ANCHOR"), None)
    assert anchor_block is not None
    assert "Range Position Ratio: 0.50 (EQUILIBRIUM REGIME)" in anchor_block
    assert "Spatial Status: EQUILIBRIUM REGIME" in anchor_block


@pytest.mark.asyncio
async def test_priced_in_gap_two_with_structural_justification():
    """Verify that a 2-point priced-in gap is acknowledged and accepted when structural context is provided."""
    mock_session = create_mock_async_session()

    from monika.infrastructure.database.models import FundamentalBrief

    mock_brief = FundamentalBrief(
        id=2,
        generated_at=datetime.now(timezone.utc),
        confidence=0.70,
        structured_json=json.dumps(
            {
                "currency_bias": {"EUR": "bullish", "USD": "neutral"},
                "currency_confidence": {"EUR": 0.70, "USD": 0.50},
                "asset_priced_in_scores": {"EURUSD": 6},
                "priced_in_assessment": {"priced_in_score": 6},
            }
        ),
    )

    def execute_side_effect(*args, **kwargs):
        query = str(args[0]).lower()
        res = MagicMock()
        if "fundamental_brief" in query:
            res.scalar_one_or_none.return_value = mock_brief
            res.scalars.return_value.all.return_value = [mock_brief]
        elif "price_ohlcv" in query or "technical_indicators" in query:
            res.scalar_one_or_none.return_value = datetime.now(timezone.utc)
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    mock_session.execute = AsyncMock(side_effect=execute_side_effect)
    executor = ToolExecutor(mock_session)

    errors: list[str] = []
    rationale, _ = await executor._cross_validate_priced_in(
        symbol="EURUSD",
        decision="buy",
        rationale="Entering on H4 deep discount order block retest with strong structural confirmation.",
        inp={"priced_in_score": 4},
        errors=errors,
        brief_row=mock_brief,
    )

    # Gap is 2 (6 vs 4), and rationale includes "discount" and "order block"
    assert len(errors) == 0
    assert "[SYSTEM: Priced-in gap (2) acknowledged and accepted based on rationale context.]" in rationale
