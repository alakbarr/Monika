import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import create_mock_async_session
from monika.application.analysis.calculators.intraday_level_optimizer import compute_optimal_levels
from monika.application.analysis.strategies.liquidity_sweep_edge import LiquiditySweepStructuralShift


@pytest.mark.asyncio
async def test_compute_optimal_levels_rr_pairing():
    """Verify that compute_optimal_levels pairs TP and SL to satisfy min_rr >= 1.3."""
    session = create_mock_async_session()
    settings = {"trading": {"risk": {"min_rr_ratio": 1.3}}}

    # Mock daily range context
    mock_adr_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 20.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": 50.0,
        "room_remaining_pct": 0.60,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as m_adr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock
        ) as m_zones,
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as m_sweep,
    ):
        m_adr.return_value = mock_adr_ctx
        m_atr.return_value = 10.0
        m_sweep.return_value = {"sweep_detected": False}

        # Zones that would create:
        # TP 1: dist 30 (low=2030 for buy at 2000)
        # TP 2: dist 55 (low=2055 for buy at 2000)
        # SL 1: dist 35 (high=1965 for buy at 2000) -> TP1/SL1 RR = 30/35 = 0.85 (invalid)
        # However TP2/SL1 RR = 55/35 = 1.57 (valid!)
        m_zones.return_value = [
            {"type": "order_block", "direction": "bullish", "low": 2030.0, "high": 2035.0, "weight": 3.0},
            {"type": "fvg", "direction": "bullish", "low": 2055.0, "high": 2060.0, "weight": 2.5},
            {"type": "order_block", "direction": "bullish", "low": 1960.0, "high": 1965.0, "weight": 3.0},
        ]

        res = await compute_optimal_levels(session, "XAUUSD", "buy", entry_price=2000.0, settings=settings)

        assert "error" not in res
        assert res["entry_allowed"] is True
        assert res["selected_rr"] >= 1.3
        # Ensure best TP chosen is the one with compliant R:R (dist 55.0, low=2055.0)
        assert res["top_tp_candidates"][0]["price"] == 2055.0


@pytest.mark.asyncio
async def test_compute_optimal_levels_synthetic_tp():
    """Verify that when structural TPs cannot fulfill min_rr, a synthetic TP is generated within ADR room."""
    session = create_mock_async_session()
    settings = {"trading": {"risk": {"min_rr_ratio": 1.5}}}

    mock_adr_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 15.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": 40.0,
        "room_remaining_pct": 0.70,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as m_adr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock
        ) as m_zones,
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as m_sweep,
    ):
        m_adr.return_value = mock_adr_ctx
        m_atr.return_value = 10.0
        m_sweep.return_value = {"sweep_detected": False}

        # Structural TP at low=2020 (dist=20.0), SL at high=1980 (dist=20.0).
        # RR = 20.0 / 20.0 = 1.0 < 1.5. No structural pair meets min_rr!
        m_zones.return_value = [
            {"type": "order_block", "direction": "bullish", "low": 2020.0, "high": 2025.0, "weight": 3.0},
            {"type": "order_block", "direction": "bullish", "low": 1975.0, "high": 1980.0, "weight": 3.0},
        ]

        res = await compute_optimal_levels(session, "XAUUSD", "buy", entry_price=2000.0, settings=settings)

        assert "error" not in res
        assert res["entry_allowed"] is True
        assert res["selected_rr"] >= 1.5
        # Top TP candidate should be synthetic min_rr target
        top_tp = res["top_tp_candidates"][0]
        assert top_tp["basis"] == "synthetic_min_rr_adr_target"
        # Synthetic TP: 2000 + 26.5 * 1.5 = 2039.75
        assert top_tp["price"] == 2039.75


@pytest.mark.asyncio
async def test_compute_optimal_levels_insufficient_adr_room():
    """Verify that when required TP for min_rr exceeds ADR limits, entry is disallowed."""
    session = create_mock_async_session()
    settings = {"trading": {"risk": {"min_rr_ratio": 2.0}}}

    mock_adr_ctx = {
        "adr": 50.0,
        "target_tp_min_distance": 10.0,
        "target_tp_max_distance": 30.0,
        "target_sl_max_distance": 30.0,
        "room_remaining_pct": 0.10,  # Very exhausted room
        "entry_allowed": False,
        "volatility_regime": "contracting",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as m_adr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock
        ) as m_zones,
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as m_sweep,
    ):
        m_adr.return_value = mock_adr_ctx
        m_atr.return_value = 10.0
        m_sweep.return_value = {"sweep_detected": False}

        # SL dist = 25.0 -> required TP for 2.0 RR = 50.0 > max allowed 30.0 * 1.15
        m_zones.return_value = [
            {"type": "order_block", "direction": "bullish", "low": 1975.0, "high": 1980.0, "weight": 3.0},
        ]

        res = await compute_optimal_levels(session, "XAUUSD", "buy", entry_price=2000.0, settings=settings)

        assert res["entry_allowed"] is False
        assert "insufficient_rr_within_adr" in res.get("rejection_reason", "")


@pytest.mark.asyncio
async def test_compute_optimal_levels_with_existing_sl():
    """Verify that caller-provided existing_sl is prioritized and respected."""
    session = create_mock_async_session()
    settings = {"trading": {"risk": {"min_rr_ratio": 1.3}}}

    mock_adr_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 15.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": 50.0,
        "room_remaining_pct": 0.80,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as m_adr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock
        ) as m_zones,
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as m_sweep,
    ):
        m_adr.return_value = mock_adr_ctx
        m_atr.return_value = 10.0
        m_sweep.return_value = {"sweep_detected": False}
        # Structural TP at 2025.0 (dist 25.0)
        m_zones.return_value = [
            {"type": "order_block", "direction": "bullish", "low": 2025.0, "high": 2030.0, "weight": 3.0},
        ]

        # Prescribed SL at 1990.0 (dist = 10.0)
        res = await compute_optimal_levels(
            session, "XAUUSD", "buy", entry_price=2000.0, settings=settings, existing_sl=1990.0
        )

        assert "error" not in res
        assert res["entry_allowed"] is True
        assert res["top_sl_candidates"][0]["price"] == 1990.0
        assert res["top_sl_candidates"][0]["basis"] == "signal_prescribed_sl"
        assert res["selected_rr"] >= 1.3


@pytest.mark.asyncio
async def test_liquidity_sweep_computes_invalidation_stop_loss():
    """Verify that LiquiditySweepStructuralShift calculates SL from sweep_price +/- buffer."""
    settings = {"trading": {"edge_strategy": {"liquidity_sweep": {"enabled": True}}}}
    strategy = LiquiditySweepStructuralShift(settings)
    session = create_mock_async_session()

    with (
        patch(
            "monika.application.analysis.strategies.liquidity_sweep_edge.detect_liquidity_sweep", new_callable=AsyncMock
        ) as m_detect,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
    ):
        m_atr.return_value = 10.0

        # Bullish sweep: swept low at 2600.0
        m_detect.return_value = {
            "structure_confirmed": True,
            "volume_confirmed": True,
            "valid_for_direction": "buy",
            "sweep_price": 2600.0,
            "reasons": ["Sweep at 2600 confirmed"],
        }
        sig_buy = await strategy.evaluate(session, "XAUUSD", settings)
        assert sig_buy.valid is True
        assert sig_buy.direction == "buy"
        # SL should be sweep_price - (atr * 0.1) = 2600 - 1.0 = 2599.0
        assert sig_buy.stop_loss == 2599.0

        # Bearish sweep: swept high at 2700.0
        m_detect.return_value = {
            "structure_confirmed": True,
            "volume_confirmed": True,
            "valid_for_direction": "sell",
            "sweep_price": 2700.0,
            "reasons": ["Sweep at 2700 confirmed"],
        }
        sig_sell = await strategy.evaluate(session, "XAUUSD", settings)
        assert sig_sell.valid is True
        assert sig_sell.direction == "sell"
        # SL should be sweep_price + (atr * 0.1) = 2700 + 1.0 = 2701.0
        assert sig_sell.stop_loss == 2701.0


@pytest.mark.asyncio
async def test_compute_optimal_levels_default_min_rr_1_8_and_limit_entry():
    """Verify that compute_optimal_levels defaults to min_rr 1.8 and provides recommended limit pullback entry."""
    session = create_mock_async_session()
    # Empty risk settings to test system defaults
    settings = {"trading": {"risk": {}}}

    mock_adr_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 20.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": 40.0,
        "room_remaining_pct": 0.80,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }

    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
        ) as m_adr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr", new_callable=AsyncMock
        ) as m_atr,
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones", new_callable=AsyncMock
        ) as m_zones,
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
        ) as m_sweep,
    ):
        m_adr.return_value = mock_adr_ctx
        m_atr.return_value = 10.0
        m_sweep.return_value = {"sweep_detected": False}
        m_zones.return_value = []

        res = await compute_optimal_levels(session, "EURUSD", "buy", entry_price=1.1000, settings=settings)

        assert "error" not in res
        assert res["min_rr_ratio"] == 1.8
        assert res["selected_rr"] >= 1.8
        assert res["recommended_entry_type"] == "LIMIT"
        assert "pullback_entry_price" in res
        # Pullback entry for BUY should be below market entry price
        assert res["pullback_entry_price"] < 1.1000


@pytest.mark.asyncio
async def test_collect_zones_point_in_time_filters_future_and_mitigated_zones(db_session):
    """Verify _collect_zones respects Point-in-Time as_of filtering for OrderBlock and FVGZone."""
    from datetime import datetime, timedelta, timezone
    import monika.core.primitives.clock as clock
    from monika.application.analysis.calculators.intraday_level_optimizer import _collect_zones
    from monika.infrastructure.database.models import FVGZone, OrderBlock

    as_of = datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc)
    past_ob = OrderBlock(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        price_low=1.0950,
        price_high=1.0965,
        formed_at=as_of - timedelta(hours=8),
        mitigated_at=as_of + timedelta(hours=12),  # Not yet mitigated as of 13:00 UTC!
    )
    future_ob = OrderBlock(
        symbol="EURUSD",
        timeframe="H4",
        direction="bearish",
        price_low=1.1080,
        price_high=1.1095,
        formed_at=as_of + timedelta(hours=4),  # Formed in the future -> must be excluded!
        mitigated_at=None,
    )
    past_fvg = FVGZone(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        gap_low=1.0970,
        gap_high=1.0985,
        formed_at=as_of - timedelta(hours=4),
        filled_at=None,
    )
    db_session.add_all([past_ob, future_ob, past_fvg])
    await db_session.commit()

    with clock.frozen_time(as_of):
        zones = await _collect_zones(db_session, "EURUSD")

    lows = [z["low"] for z in zones]
    assert 1.0950 in lows
    assert 1.0970 in lows
    assert 1.1080 not in lows


@pytest.mark.asyncio
async def test_intraday_level_optimizer_full_branch_coverage(db_session):
    """Cover _get_atr, _collect_zones (SR/Liquidity/Swing + non-PiT), _score_candidate, TimesFM sell/overextended, and prescribed TP/SL edges."""
    from datetime import datetime, timedelta, timezone
    from monika.application.analysis.calculators.intraday_level_optimizer import (
        _collect_zones,
        _get_atr,
        _score_candidate,
        compute_optimal_levels,
    )
    from monika.infrastructure.database.models import (
        LiquidityZone,
        SRZone,
        SwingPoint,
        TechnicalIndicator,
    )

    assert _score_candidate(10.0, 10.0, 0.0, 2.0) == 1.0

    as_of = datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc)
    # 1. _get_atr with valid JSON and invalid JSON
    ind_valid = TechnicalIndicator(
        symbol="EURUSD",
        timeframe="H4",
        indicator_name="ATR_14",
        timestamp=as_of - timedelta(hours=1),
        value_json='{"atr": 0.0025}',
    )
    db_session.add(ind_valid)
    await db_session.commit()
    assert await _get_atr(db_session, "EURUSD", as_of=as_of) == pytest.approx(0.0025)

    ind_corrupt = TechnicalIndicator(
        symbol="GBPUSD",
        timeframe="H4",
        indicator_name="ATR_14",
        timestamp=as_of - timedelta(hours=1),
        value_json="{bad_json",
    )
    db_session.add(ind_corrupt)
    await db_session.commit()
    assert await _get_atr(db_session, "GBPUSD", as_of=as_of) == 0.0

    # 2. _collect_zones with SRZone, LiquidityZone, SwingPoint (both with as_of and without as_of)
    sr = SRZone(
        symbol="EURUSD",
        timeframe="H4",
        price_low=1.0900,
        price_high=1.0910,
        strength=3,
        last_touched=as_of - timedelta(hours=2),
    )
    lz = LiquidityZone(
        symbol="EURUSD",
        timeframe="H4",
        type="below_swing_low",
        zone_low=1.0880,
        zone_high=1.0890,
        identified_at=as_of - timedelta(hours=2),
    )
    sw = SwingPoint(
        symbol="EURUSD",
        timeframe="H4",
        type="low",
        price=1.0870,
        timestamp=as_of - timedelta(hours=3),
    )
    db_session.add_all([sr, lz, sw])
    await db_session.commit()

    zones_pit = await _collect_zones(db_session, "EURUSD", as_of=as_of)
    zone_types = {z["type"] for z in zones_pit}
    assert {"sr_zone", "liquidity", "swing"}.issubset(zone_types)

    zones_live = await _collect_zones(db_session, "EURUSD", as_of=None)
    assert len(zones_live) >= 3

    # 3. compute_optimal_levels when compute_daily_range_context returns error
    with patch(
        "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
        new_callable=AsyncMock,
        return_value={"error": "no d1 bars"},
    ):
        err_res = await compute_optimal_levels(db_session, "EURUSD", "buy", 1.1000, {})
        assert err_res == {"error": "no d1 bars"}

    # 4. compute_optimal_levels with sweep detected, TimesFM overextended BUY & SELL, and invalid/valid existing_sl/tp
    mock_adr_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 20.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": 50.0,
        "room_remaining_pct": 0.80,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }
    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value=mock_adr_ctx,
        ),
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr",
            new_callable=AsyncMock,
            return_value=0.0,
        ),
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones",
            new_callable=AsyncMock,
            return_value=[
                {"type": "order_block", "direction": "bullish", "low": 2030.0, "high": 2035.0, "weight": 3.0},
                {"type": "fvg", "direction": "bullish", "low": 2070.0, "high": 2075.0, "weight": 2.5},
                {"type": "order_block", "direction": "bearish", "low": 1965.0, "high": 1970.0, "weight": 3.0},
                {"type": "fvg", "direction": "bearish", "low": 1925.0, "high": 1930.0, "weight": 2.5},
            ],
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            return_value={"sweep_detected": True, "sweep_price": 1980.0, "valid_for_direction": "buy"},
        ),
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            new_callable=AsyncMock,
            return_value={"quantiles": {"q10": [1950.0], "q90": [2050.0]}},
        ),
    ):
        # BUY with invalid existing_sl/tp strings & TimesFM q90 (2030 <= 2050 boosted, 2070 > 2050 penalized)
        bad_val = getattr(str, "nonexistent", "bad_value")
        res_buy = await compute_optimal_levels(
            db_session,
            "XAUUSD",
            "buy",
            entry_price=2000.0,
            settings={},
            existing_sl=bad_val,
            existing_tp=bad_val,
        )
        assert "error" not in res_buy

        # SELL with valid existing_tp & TimesFM q10 (1970 >= 1950 boosted, 1930 < 1950 penalized)
        res_sell = await compute_optimal_levels(
            db_session,
            "XAUUSD",
            "sell",
            entry_price=2000.0,
            settings={},
            existing_tp=1940.0,
        )
        assert "error" not in res_sell
        assert any(c["basis"] == "signal_prescribed_tp" for c in res_sell["top_tp_candidates"])

    # 5. Sweep detector exception, TimesFM exception, and sl["distance"] <= 0 continue guard
    mock_zero_sl_ctx = {
        "adr": 100.0,
        "target_tp_min_distance": 20.0,
        "target_tp_max_distance": 80.0,
        "target_sl_max_distance": -10.0,
        "room_remaining_pct": 0.80,
        "entry_allowed": True,
        "volatility_regime": "normal",
    }
    with (
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer.compute_daily_range_context",
            new_callable=AsyncMock,
            return_value=mock_zero_sl_ctx,
        ),
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._get_atr",
            new_callable=AsyncMock,
            return_value=10.0,
        ),
        patch(
            "monika.application.analysis.calculators.intraday_level_optimizer._collect_zones",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "monika.application.analysis.calculators.liquidity_sweep_detector.detect_liquidity_sweep",
            new_callable=AsyncMock,
            side_effect=RuntimeError("sweep err"),
        ),
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast",
            new_callable=AsyncMock,
            side_effect=RuntimeError("tfm err"),
        ),
    ):
        res_zero = await compute_optimal_levels(db_session, "XAUUSD", "buy", entry_price=2000.0, settings={})
        assert "error" not in res_zero


@pytest.mark.asyncio
async def test_structures_smc_handlers_full_coverage(db_session):
    """Comprehensive tests for all handlers in structures_smc.py to achieve 100% coverage."""
    from datetime import datetime, timedelta, timezone
    import monika.core.primitives.clock as clock
    from monika.application.analysis.tools.handlers.market_data_handlers.structures_smc import (
        handle_detect_candlestick_patterns,
        handle_get_fibonacci_levels,
        handle_get_optimal_intraday_levels,
        handle_get_smc_zones,
        handle_get_sr_zones,
        handle_get_structure_breaks,
        handle_get_swing_points,
        handle_scan_chart_patterns,
    )
    from monika.infrastructure.database.models import (
        FVGZone,
        OrderBlock,
        PriceOHLCV,
        SRZone,
        StructureBreak,
        SwingPoint,
    )

    as_of = datetime(2026, 10, 7, 13, 0, tzinfo=timezone.utc)

    # 1. Missing symbol and no_session guards for swing_points, structure_breaks, sr_zones, smc_zones
    assert "error" in await handle_get_swing_points({})
    assert (await handle_get_swing_points({"symbol": "EURUSD"}))["swing_points"] == []

    assert "error" in await handle_get_structure_breaks({})
    assert (await handle_get_structure_breaks({"symbol": "EURUSD"}))["breaks"] == []

    assert "error" in await handle_get_sr_zones({})
    assert (await handle_get_sr_zones({"symbol": "EURUSD"}))["zones"] == []

    assert "error" in await handle_get_smc_zones({})
    assert (await handle_get_smc_zones({"symbol": "EURUSD"}))["status"] == "no_session"

    # 2. Seed DB rows for swing_points, structure_breaks, sr_zones, smc_zones
    sb = StructureBreak(
        symbol="EURUSD",
        timeframe="H4",
        type="BOS",
        direction="bullish",
        price=1.1000,
        formed_at=as_of - timedelta(hours=2),
    )
    sr_row = SRZone(
        symbol="EURUSD",
        timeframe="H4",
        price_low=1.0900,
        price_high=1.0910,
        strength=4,
        last_touched=as_of - timedelta(hours=1),
    )
    ob_row = OrderBlock(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        price_low=1.0920,
        price_high=1.0930,
        formed_at=as_of - timedelta(hours=3),
        mitigated_at=None,
    )
    fvg_row = FVGZone(
        symbol="EURUSD",
        timeframe="H4",
        direction="bullish",
        gap_low=1.0940,
        gap_high=1.0950,
        formed_at=as_of - timedelta(hours=2),
        filled_at=None,
    )
    sw_low = SwingPoint(
        symbol="EURUSD",
        timeframe="H4",
        type="low",
        price=1.0800,
        timestamp=as_of - timedelta(hours=10),
    )
    sw_high = SwingPoint(
        symbol="EURUSD",
        timeframe="H4",
        type="high",
        price=1.1000,
        timestamp=as_of - timedelta(hours=5),
    )
    bar = PriceOHLCV(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=as_of - timedelta(hours=1),
        open=1.0890,
        high=1.0910,
        low=1.0880,
        close=1.0900,
        volume=100.0,
    )
    db_session.add_all([sb, sr_row, ob_row, fvg_row, sw_low, sw_high, bar])
    await db_session.commit()

    with clock.frozen_time(as_of):
        sp_res = await handle_get_swing_points({"symbol": "EURUSD"}, session=db_session)
        assert len(sp_res["swing_points"]) >= 2

        sb_res = await handle_get_structure_breaks({"symbol": "EURUSD"}, session=db_session)
        assert len(sb_res["breaks"]) == 1

        sr_res = await handle_get_sr_zones({"symbol": "EURUSD"}, session=db_session)
        assert len(sr_res["zones"]) >= 1

        smc_res = await handle_get_smc_zones({"symbol": "EURUSD"}, session=db_session)
        assert smc_res["total_order_blocks"] >= 1
        assert smc_res["total_fvg_zones"] >= 1

    # 3. handle_get_fibonacci_levels: manual inputs (invalid bounds, bullish, bearish, invalid float)
    assert "error" in await handle_get_fibonacci_levels({"high": 1.0, "low": 2.0})
    fib_man_bull = await handle_get_fibonacci_levels({"high": 1.1000, "low": 1.0800, "trend": "bullish"})
    assert fib_man_bull["source"] == "manual_input"
    assert fib_man_bull["trend"] == "bullish"

    fib_man_bear = await handle_get_fibonacci_levels({"high": 1.1000, "low": 1.0800, "trend": "bearish"})
    assert fib_man_bear["trend"] == "bearish"

    assert "error" in await handle_get_fibonacci_levels({"high": "not_a_float", "low": 1.0})
    assert "error" in await handle_get_fibonacci_levels({})
    assert "error" in await handle_get_fibonacci_levels({"symbol": "EURUSD"})

    # 4. handle_get_fibonacci_levels: DB swing points (bullish EQUILIBRIUM, PREMIUM, DISCOUNT, bearish, errors)
    # Bullish with DB latest_bar close == 1.0900 (EQUILIBRIUM) and invalid current_price arg
    fib_db_eq = await handle_get_fibonacci_levels(
        {"symbol": "EURUSD", "current_price": "invalid_float"}, session=db_session
    )
    assert fib_db_eq["trend_context"] == "bullish"
    assert fib_db_eq["current_zone"] == "EQUILIBRIUM"

    # Bullish with explicit current_price in PREMIUM
    fib_db_prem = await handle_get_fibonacci_levels({"symbol": "EURUSD", "current_price": 1.0950}, session=db_session)
    assert fib_db_prem["current_zone"] == "PREMIUM"

    # Bearish trend (add newer low swing) + DISCOUNT zone + OTE zone
    sw_newer_low = SwingPoint(
        symbol="EURUSD",
        timeframe="H4",
        type="low",
        price=1.0800,
        timestamp=as_of - timedelta(hours=1),
    )
    db_session.add(sw_newer_low)
    await db_session.commit()
    fib_db_bear = await handle_get_fibonacci_levels({"symbol": "EURUSD", "current_price": 1.0860}, session=db_session)
    assert fib_db_bear["trend_context"] == "bearish"
    assert fib_db_bear["current_zone"] == "DISCOUNT"
    assert fib_db_bear["in_ote_zone"] is True

    # Insufficient swing points (< 2)
    assert "error" in await handle_get_fibonacci_levels({"symbol": "EMPTY_SYM"}, session=db_session)

    # All swings same type ("Not enough swing points found")
    db_session.add_all(
        [
            SwingPoint(
                symbol="ONLY_HIGH", timeframe="H4", type="high", price=1.10, timestamp=as_of - timedelta(hours=2)
            ),
            SwingPoint(
                symbol="ONLY_HIGH", timeframe="H4", type="high", price=1.12, timestamp=as_of - timedelta(hours=1)
            ),
        ]
    )
    await db_session.commit()
    assert (
        "Not enough swing points found"
        in (await handle_get_fibonacci_levels({"symbol": "ONLY_HIGH"}, session=db_session))["error"]
    )

    # Invalid swing pair: high <= low (fallback path where best_range == 0 and diff <= 0)
    # Also test DB exception on PriceOHLCV lookup
    db_session.add_all(
        [
            SwingPoint(
                symbol="BAD_PAIR", timeframe="H4", type="high", price=1.05, timestamp=as_of - timedelta(hours=2)
            ),
            SwingPoint(symbol="BAD_PAIR", timeframe="H4", type="low", price=1.10, timestamp=as_of - timedelta(hours=1)),
        ]
    )
    await db_session.commit()
    assert (
        "Invalid swing pair" in (await handle_get_fibonacci_levels({"symbol": "BAD_PAIR"}, session=db_session))["error"]
    )

    # Non-coherent valid pair when last 8 swings are all high, but 9th older swing is low, plus PriceOHLCV query error
    mock_sess = create_mock_async_session()
    swings_9 = [
        SwingPoint(symbol="NON_COH", timeframe="H4", type="low", price=1.00, timestamp=as_of - timedelta(hours=20)),
        *[
            SwingPoint(
                symbol="NON_COH",
                timeframe="H4",
                type="high",
                price=1.10,
                timestamp=as_of - timedelta(hours=10 - i),
            )
            for i in range(8)
        ],
    ]
    call_count = {"n": 0}

    def _fib_exec(stmt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            r = MagicMock()
            r.scalars().all.return_value = swings_9
            return r
        raise RuntimeError("db bar query failed")

    mock_sess.execute = AsyncMock(side_effect=_fib_exec)
    fib_non_coh = await handle_get_fibonacci_levels({"symbol": "NON_COH"}, session=mock_sess)
    assert fib_non_coh["coherent_pair"] is False
    assert fib_non_coh["current_zone"] == "UNKNOWN"

    # 5. handle_get_optimal_intraday_levels
    assert "error" in await handle_get_optimal_intraday_levels({})
    assert (await handle_get_optimal_intraday_levels({"symbol": "EURUSD", "entry_price": 0.0}))["levels"] == {}
    with patch(
        "monika.application.analysis.calculators.intraday_level_optimizer.compute_optimal_levels",
        new_callable=AsyncMock,
        return_value={"tp1": 1.11, "sl": 1.09},
    ):
        opt_ok = await handle_get_optimal_intraday_levels({"symbol": "EURUSD", "entry_price": 1.10}, session=db_session)
        assert opt_ok["tp1"] == 1.11

    with patch(
        "monika.application.analysis.calculators.intraday_level_optimizer.compute_optimal_levels",
        new_callable=AsyncMock,
        side_effect=RuntimeError("calc failed"),
    ):
        opt_err = await handle_get_optimal_intraday_levels(
            {"symbol": "EURUSD", "entry_price": 1.10}, session=db_session
        )
        assert opt_err["levels"] == {}

    # 6. handle_detect_candlestick_patterns
    assert "error" in await handle_detect_candlestick_patterns({})
    c_res = await handle_detect_candlestick_patterns({"symbol": "EURUSD", "timeframe": "H1"}, session=db_session)
    assert c_res["symbol"] == "EURUSD"

    # 7. handle_scan_chart_patterns
    with patch(
        "monika.application.services.market_data_service.MarketDataService.ensure_bars",
        new_callable=AsyncMock,
        return_value=[],
    ):
        scan_err = await handle_scan_chart_patterns({}, session=db_session)
        assert "Insufficient bars" in scan_err["error"]

    fake_bars = [
        {
            "open": 1.10 + i * 0.0001,
            "high": 1.11 + i * 0.0001,
            "low": 1.09 + i * 0.0001,
            "close": 1.10 + i * 0.0001,
            "volume": 100.0,
        }
        for i in range(30)
    ]
    with (
        patch(
            "monika.application.services.market_data_service.MarketDataService.ensure_bars",
            new_callable=AsyncMock,
            return_value=fake_bars,
        ),
        patch(
            "monika.domain.indicators.chart_patterns.scan_all_chart_patterns",
            return_value={"patterns": []},
        ),
    ):
        scan_ok = await handle_scan_chart_patterns({"symbol": "EURUSD"}, session=db_session)
        assert scan_ok["symbol"] == "EURUSD"
