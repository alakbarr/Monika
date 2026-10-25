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
