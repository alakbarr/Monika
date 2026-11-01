"""Unit tests for Stage 2 Data Bundler & Quantitative Calculators fixes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context
from monika.application.analysis.calculators.intraday_level_optimizer import compute_optimal_levels
from monika.application.analysis.calculators.macro_bias_filter import (
    compute_currency_macro_score,
    evaluate_macro_alignment,
)
from monika.application.analysis.prefetch.stage2_prefetcher import (
    STANDARD_FETCH_TASKS,
    Stage2DataBundler,
)
from monika.application.analysis.tools.handlers.market_data_handlers.technicals import (
    handle_get_daily_range_context,
)
from monika.infrastructure.database.models import (
    DXYData,
    InterestRate,
    PriceOHLCV,
    TechnicalIndicator,
    TreasuryYield,
)


@pytest.mark.asyncio
async def test_compute_daily_range_context_auto_fetches_atr_h4_and_harmonizes(db_session):
    """Verify compute_daily_range_context auto-fetches H4 ATR when atr_h4=None and harmonizes SL/TP ceilings."""
    as_of = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    # 6 D1 bars with tight range = 0.0060 (so 0.35 * ADR = 0.0021)
    for i in range(6):
        bar_dt = as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i + 1)
        db_session.add(
            PriceOHLCV(
                symbol="EURUSD",
                timeframe="D1",
                timestamp=bar_dt,
                open=1.0800,
                high=1.0860,
                low=1.0800,
                close=1.0830,
                volume=1000.0,
            )
        )
    # H4 ATR_14 = 0.0032 (> 0.0021 raw SL max!)
    db_session.add(
        TechnicalIndicator(
            symbol="EURUSD",
            timeframe="H4",
            timestamp=as_of - timedelta(hours=1),
            indicator_name="ATR_14",
            value_json='{"atr": 0.0032}',
        )
    )
    await db_session.commit()

    with patch(
        "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
        new_callable=AsyncMock,
        return_value=None,
    ):
        res = await compute_daily_range_context(db_session, "EURUSD", settings={}, as_of=as_of, atr_h4=None)

    assert "error" not in res
    assert res["atr_harmonized"] is True
    assert res["atr_h4"] == pytest.approx(0.0032)
    assert res["target_sl_max_distance"] >= round(1.25 * 0.0032, 6)
    assert res["target_tp_min_distance"] >= round(1.50 * 0.0032, 6)
    assert res["target_tp_max_distance"] >= round(1.65 * res["target_sl_max_distance"], 6)


@pytest.mark.asyncio
async def test_compute_daily_range_context_h4_ohlcv_fallback_and_tool_handler(db_session):
    """Verify H4 PriceOHLCV fallback when TechnicalIndicator is absent and clock.now() wiring in handler."""
    as_of = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    for i in range(6):
        bar_dt = as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i + 1)
        db_session.add(
            PriceOHLCV(
                symbol="USDJPY",
                timeframe="D1",
                timestamp=bar_dt,
                open=157.00,
                high=157.70,
                low=157.00,
                close=157.40,
                volume=1000.0,
            )
        )
    # Add 10 H4 bars with true range = 0.40 (> 0.35 * 0.70 = 0.245)
    for j in range(10):
        h4_dt = as_of - timedelta(hours=4 * (j + 1))
        db_session.add(
            PriceOHLCV(
                symbol="USDJPY",
                timeframe="H4",
                timestamp=h4_dt,
                open=157.00,
                high=157.40,
                low=157.00,
                close=157.20,
                volume=500.0,
            )
        )
    await db_session.commit()

    with (
        patch("monika.core.primitives.clock.now", return_value=as_of),
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        res = await handle_get_daily_range_context({"symbol": "USDJPY"}, session=db_session, settings={})

    assert "error" not in res
    assert res["atr_harmonized"] is True
    assert res["atr_h4"] == pytest.approx(0.40)
    assert res["target_sl_max_distance"] >= round(1.25 * 0.40, 6)
    assert res["target_tp_max_distance"] >= round(1.65 * res["target_sl_max_distance"], 6)


@pytest.mark.asyncio
async def test_compute_optimal_levels_min_rr_1_5_and_tp_max_harmonization(db_session):
    """Verify compute_optimal_levels defaults to min_rr=1.5 and harmonizes tp_max_limit when ADR is tight vs ATR."""
    # Tight 5-day ADR (0.779 on USDJPY -> unharmonized tp_max = 0.6232, sl_max = 0.27265)
    # while H4 ATR = 0.35 (so SL is ~0.40, requiring TP >= 0.60, or if SL=0.45 requiring TP=0.675 > 0.6232!)
    unharmonized_adr_ctx = {
        "adr": 0.779,
        "target_tp_min_distance": 0.3895,
        "target_tp_max_distance": 0.6232,
        "target_sl_max_distance": 0.27265,
        "room_remaining_pct": 0.75,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value=unharmonized_adr_ctx,
        ) as mock_drc,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr",
            new_callable=AsyncMock,
            return_value=0.35,
        ),
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones",
            new_callable=AsyncMock,
            return_value=[
                {"type": "order_block", "direction": "bullish", "low": 157.45, "high": 157.55, "weight": 3.0},
            ],
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"sweep_detected": False},
        ),
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        res = await compute_optimal_levels(
            db_session, "USDJPY", "buy", entry_price=157.85, settings={"trading": {"risk": {"min_rr_ratio": 1.5}}}
        )

    assert "error" not in res
    assert res["min_rr_ratio"] == pytest.approx(1.5)
    assert res["entry_allowed"] is True
    assert "rejection_reason" not in res
    assert res["selected_rr"] >= 1.5
    mock_drc.assert_awaited_once()
    assert mock_drc.call_args.kwargs.get("atr_h4") == pytest.approx(0.35)


@pytest.mark.asyncio
async def test_evaluate_macro_alignment_direction_none_and_usdjpy_carry_score(db_session):
    """Verify evaluate_macro_alignment handles direction=None on BTCUSD/XAUUSD and positive USDJPY carry."""
    as_of = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    db_session.add(DXYData(date=as_of, close=101.80))
    db_session.add(TreasuryYield(tenor="10Y_REAL", date=as_of, yield_percent=2.10))
    db_session.add(InterestRate(bank="FED", rate_percent=3.88, effective_date=as_of - timedelta(days=5)))
    db_session.add(InterestRate(bank="BOJ", rate_percent=1.25, effective_date=as_of - timedelta(days=5)))
    db_session.add(InterestRate(bank="RBA", rate_percent=4.60, effective_date=as_of - timedelta(days=5)))
    await db_session.commit()

    settings = {"trading": {"edge_strategy": {"macro_bias": {"enabled": True}}}}

    # 1. BTCUSD with direction=None under DXY=101.80 must NOT emit false strong_conflict=True
    btc_none = await evaluate_macro_alignment(db_session, "BTCUSD", None, settings, as_of=as_of)
    assert btc_none["aligned"] is True
    assert btc_none["strong_conflict"] is False
    assert btc_none["implied_direction"] == "sell"
    assert btc_none["pair_macro_score"] == pytest.approx(-0.5)

    # 2. XAUUSD with direction=None under DXY=101.80 must NOT emit false strong_conflict=True
    xau_none = await evaluate_macro_alignment(db_session, "XAUUSD", None, settings, as_of=as_of)
    assert xau_none["aligned"] is True
    assert xau_none["strong_conflict"] is False
    assert xau_none["implied_direction"] == "sell"
    assert xau_none["pair_macro_score"] == pytest.approx(-0.5)

    # 3. BTCUSD with explicit direction="sell" returns negative pair_macro_score (-0.5)
    btc_sell = await evaluate_macro_alignment(db_session, "BTCUSD", "sell", settings, as_of=as_of)
    assert btc_sell["aligned"] is True
    assert btc_sell["strong_conflict"] is False
    assert btc_sell["pair_macro_score"] == pytest.approx(-0.5)

    # 4. USDJPY with USD=3.88% vs JPY=1.25% (+263 bps carry) produces positive pair_macro_score ("buy")
    with patch(
        "monika.domain.market.usd_strength_proxy.compute_usd_strength_proxy",
        new_callable=AsyncMock,
        return_value={"weighted_usd_change_pct": 0.0},
    ):
        usdjpy_res = await evaluate_macro_alignment(db_session, "USDJPY", None, settings, as_of=as_of)
        aud_score = await compute_currency_macro_score(db_session, "AUD", settings, as_of=as_of)
        usd_score = await compute_currency_macro_score(db_session, "USD", settings, as_of=as_of)

    assert usdjpy_res["pair_macro_score"] > 0.0
    assert usdjpy_res["implied_direction"] == "buy"
    assert usd_score["score"] > usdjpy_res["quote_score"]["score"]
    assert aud_score["score"] > usd_score["score"]


@pytest.mark.asyncio
async def test_stage2_bundler_populates_dealing_range_pos_and_macro_rate_tools(mock_async_session):
    """Verify Stage2DataBundler includes macro rate tools in STANDARD_FETCH_TASKS, aliases them, and computes dealing_range_pos."""
    task_names = [t[0] for t in STANDARD_FETCH_TASKS]
    assert "get_interest_rates" in task_names
    assert "get_fedwatch_probabilities" in task_names
    assert "get_bond_yield_spreads" in task_names

    bundler = Stage2DataBundler(mock_async_session)

    async def mock_execute(tool_name, inp):
        if tool_name == "get_price_history" and inp.get("timeframe") == "H4":
            return {
                "symbol": inp.get("symbol"),
                "timeframe": "H4",
                "bars": [
                    {"time": "2026-10-19T00:00:00Z", "open": 1.0800, "high": 1.0900, "low": 1.0800, "close": 1.0850},
                    {"time": "2026-10-19T04:00:00Z", "open": 1.0850, "high": 1.1000, "low": 1.0820, "close": 1.0825},
                ],
            }
        if tool_name == "get_atr":
            return {"atr": 0.0035}
        if tool_name == "get_interest_rates":
            return {"rates": {"FED": 3.88, "ECB": 3.25}}
        if tool_name == "get_fedwatch_probabilities":
            return {"probabilities": {"hold": 80.0}}
        if tool_name == "get_bond_yield_spreads":
            return {"yield_spreads_10y": {"DE_10Y": {"current_spread": 1.85}}}
        return {"data": "ok"}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    with (
        patch(
            "monika.application.analysis.validators.core_data_validator.CoreDataValidator.validate_and_fetch_core_data",
            new_callable=AsyncMock,
            return_value=(True, {}, []),
        ),
        patch(
            "monika.core.validation.data_validator.validate_data_freshness",
            new_callable=AsyncMock,
            return_value={"ready": True, "errors": [], "warnings": []},
        ),
        patch(
            "monika.core.validation.data_validator.check_data_coherence",
            new_callable=AsyncMock,
            return_value={"coherent": True, "issues": []},
        ),
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value={
                "lookback_days": 5,
                "adr": 0.0060,
                "today_range_so_far": 0.0020,
                "today_range_pct_of_adr": 0.3333,
                "room_remaining_pct": 0.6667,
                "session_recommendation": "full_target",
                "target_tp_min_distance": 0.00525,
                "target_tp_max_distance": 0.00722,
                "target_sl_max_distance": 0.00438,
                "atr_harmonized": True,
            },
        ),
    ):
        bundle_txt, data = await bundler.fetch_bundle("EURUSD")

    assert "interest_rates" in data
    assert "fedwatch_probabilities" in data
    assert "bond_yield_spreads" in data
    assert "dealing_range_pos" in data
    dr = data["dealing_range_pos"]
    # Range: [1.0800, 1.1000], close=1.0825 -> pos = (1.0825 - 1.0800) / 0.0200 = 0.125
    assert dr["position"] == pytest.approx(0.125)
    assert dr["zone"] == "DISCOUNT_ACCUMULATION_ZONE"
    assert "(Harmonized w/ H4 ATR floor)" in bundle_txt
