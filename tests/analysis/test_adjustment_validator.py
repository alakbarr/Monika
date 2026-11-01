from tests.conftest import create_mock_async_session
# ==============================================================================
# File: tests/analysis/test_adjustment_validator.py
# Monika Adjustment Validator Test Suite
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.application.analysis.debate.adjustment_validator import validate_and_apply_judge_adjustments


class DummyAnalysis:
    def __init__(self, symbol="EURUSD", direction="BUY", price=1.1000, sl=1.0900, tp=1.1200):
        self.symbol = symbol
        self.direction = direction
        self.price_at_analysis = price
        self.stop_loss = sl
        self.take_profit = tp


@pytest.mark.asyncio
async def test_no_adjustments_returns_true():
    session = create_mock_async_session()
    ana = DummyAnalysis()
    ok, reason = await validate_and_apply_judge_adjustments(
        session=session,
        ana=ana,
        verdict={},
        settings={},
        entry_zone_data={},
    )
    assert ok is True
    assert reason == ""


@pytest.mark.asyncio
async def test_buy_geometry_violation():
    session = create_mock_async_session()
    ana = DummyAnalysis(direction="BUY", price=1.1000, sl=1.0900, tp=1.1200)

    # SL >= Entry
    verdict = {"adjusted_sl": 1.1050}
    ok, reason = await validate_and_apply_judge_adjustments(
        session=session, ana=ana, verdict=verdict, settings={}, entry_zone_data={}
    )
    assert ok is False
    assert "BUY geometry violation" in reason


@pytest.mark.asyncio
async def test_sell_geometry_violation():
    session = create_mock_async_session()
    ana = DummyAnalysis(direction="SELL", price=1.1000, sl=1.1100, tp=1.0800)

    # SL <= Entry
    verdict = {"adjusted_sl": 1.0950}
    ok, reason = await validate_and_apply_judge_adjustments(
        session=session, ana=ana, verdict=verdict, settings={}, entry_zone_data={}
    )
    assert ok is False
    assert "SELL geometry violation" in reason


@pytest.mark.asyncio
async def test_min_rr_violation_exact_decimal():
    session = create_mock_async_session()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    ana = DummyAnalysis(direction="BUY", price=100.0, sl=90.0, tp=110.0)  # RR = 1.0

    settings = {"trading": {"risk": {"min_rr_ratio": 1.5}}}
    verdict = {"adjusted_tp": 110.0}  # SL distance = 10, TP distance = 10, RR = 1.0 < 1.5

    ok, reason = await validate_and_apply_judge_adjustments(
        session=session, ana=ana, verdict=verdict, settings=settings, entry_zone_data={}
    )
    assert ok is False
    assert "di bawah minimum" in reason


@pytest.mark.asyncio
async def test_entry_deviation_limit():
    session = create_mock_async_session()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    ana = DummyAnalysis(direction="BUY", price=100.0, sl=90.0, tp=130.0)

    # Adjusted entry 104.0 is 4.0% deviation (> 3%)
    verdict = {"adjusted_entry": 104.0, "adjusted_sl": 90.0, "adjusted_tp": 130.0}
    ok, reason = await validate_and_apply_judge_adjustments(
        session=session, ana=ana, verdict=verdict, settings={}, entry_zone_data={}
    )
    assert ok is False
    assert "deviasi" in reason


@pytest.mark.asyncio
async def test_adjustment_validator_passes_atr_h4_and_harmonizes_high_atr_vs_adr(monkeypatch):
    import json
    import monika.application.analysis.calculators.daily_range_calculator as drc

    session = create_mock_async_session()
    atr_row_mock = MagicMock()
    atr_row_mock.value_json = json.dumps({"atr": 0.0080})
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: atr_row_mock))

    captured_kwargs = {}

    async def fake_compute_daily_range_context(sess, symbol, settings, atr_h4=None):
        captured_kwargs["atr_h4"] = atr_h4
        # Simulate unharmonized raw ADR=0.0150 where 0.35*ADR=0.00525 < H4 ATR (0.0080)
        return {
            "adr": 0.0150,
            "target_sl_max_distance": 0.00525,
            "target_tp_min_distance": 0.00750,
            "target_tp_max_distance": 0.01200,
            "band_tolerance_pct": 0.10,
        }

    monkeypatch.setattr(drc, "compute_daily_range_context", fake_compute_daily_range_context)

    # Entry=1.1000, SL=1.0916 (SL dist = 0.0084 = 1.05x ATR), TP=1.1126 (TP dist = 0.0126, R:R = 1.50)
    ana = DummyAnalysis(symbol="EURUSD", direction="BUY", price=1.1000, sl=1.0916, tp=1.1126)
    verdict = {"adjusted_entry": 1.1000, "adjusted_sl": 1.0916, "adjusted_tp": 1.1126}
    settings = {"trading": {"risk": {"min_rr_ratio": 1.5}}}

    ok, reason = await validate_and_apply_judge_adjustments(
        session=session, ana=ana, verdict=verdict, settings=settings, entry_zone_data={"price": 1.1000}
    )
    assert ok is True, f"Expected valid adjustment, got error: {reason}"
    assert reason == ""
    assert captured_kwargs.get("atr_h4") == pytest.approx(0.0080)
