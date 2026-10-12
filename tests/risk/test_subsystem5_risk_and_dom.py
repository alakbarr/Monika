import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from risk.risk_gate import RiskGate, SizingResult
from execution.mt5_client import _calculate_dom_vwap


def test_dom_ladder_walk_vwap():
    # Mock book items: BookItem(type, price, volume, volume_dbl)
    # Type 2 = SELL (Asks), Type 1 = BUY (Bids)
    mock_item1 = MagicMock(type=2, price=1.1000, volume_dbl=2.0)
    mock_item2 = MagicMock(type=2, price=1.1005, volume_dbl=3.0)
    mock_item3 = MagicMock(type=2, price=1.1010, volume_dbl=5.0)

    mock_info = MagicMock(point=0.0001, digits=4)

    with patch("MetaTrader5.market_book_get", return_value=[mock_item1, mock_item2, mock_item3]), \
         patch("MetaTrader5.symbol_info", return_value=mock_info):

        # Test 1: Order for 4.0 lots BUY
        # Takes 2.0 @ 1.1000 and 2.0 @ 1.1005
        # VWAP = (2*1.1000 + 2*1.1005) / 4 = 1.10025
        res = _calculate_dom_vwap("EURUSD", "buy", 4.0)

        assert res["has_dom"] is True
        assert res["bbo_price"] == 1.1000
        assert res["filled_pct"] == 1.0
        # Expected VWAP ~ 1.1003 (rounded to 4 digits)
        assert abs(res["vwap"] - 1.10025) < 1e-4
        # Slippage: |1.10025 - 1.1000| / 0.0001 = 2.5 pts
        assert abs(res["slippage_pts"] - 2.5) < 0.2


@pytest.mark.asyncio
async def test_risk_gate_adv_liquidity_floor():
    settings = {"trading": {"risk": {}}}
    rg = RiskGate(settings)

    session = MagicMock()
    # Mock ADV query returning 20 days with 500 volume -> ADV = 500
    mock_execute = AsyncMock()
    mock_scalar_result = MagicMock()
    mock_scalar_result.scalars.return_value.all.return_value = [500.0] * 20
    mock_execute.return_value = mock_scalar_result
    session.execute = mock_execute

    # 1. Order of 10 lots > 1% of 500 (5.0 lots) -> Must be rejected
    sizing_excessive = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=10.0,
        recommended_lots=10.0,
        rr_ratio=2.0,
        is_valid=True,
    )
    ok, reason = await rg._check_adv_liquidity(session, "EURUSD", sizing_excessive, as_of=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc))
    assert ok is False
    assert "exceeds 1.0% of 20-day ADV" in reason

    # 2. Order of 1.0 lots <= 1% of 500 (5.0 lots) -> Approved
    sizing_ok = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0050,
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=1.0,
        recommended_lots=1.0,
        rr_ratio=2.0,
        is_valid=True,
    )
    ok_pass, msg = await rg._check_adv_liquidity(session, "EURUSD", sizing_ok, as_of=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc))
    assert ok_pass is True


@pytest.mark.asyncio
async def test_risk_gate_evidence_gate():
    settings = {"trading": {"risk": {}}}
    rg = RiskGate(settings)
    session = MagicMock()

    # Mock AssetAnalysis with strategy_id and regime
    mock_analysis = MagicMock()
    mock_analysis.strategy_id = "failing_alpha"
    mock_analysis.market_regime = "ranging"

    with patch("analysis.strategies.evidence_store.EvidenceStore.validate_strategy_for_trade", return_value=(False, "Negative expectancy -0.22")):
        ok, reason = await rg._check_evidence_gate(session, "EURUSD", analysis=mock_analysis)
        assert ok is False
        assert "Negative expectancy" in reason

    with patch("analysis.strategies.evidence_store.EvidenceStore.validate_strategy_for_trade", return_value=(True, "Approved")):
        ok, reason = await rg._check_evidence_gate(session, "EURUSD", analysis=mock_analysis)
        assert ok is True
