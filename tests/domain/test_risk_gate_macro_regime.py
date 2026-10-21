"""Unit and integration tests for RiskGate and macro_bias_filter Macro Regime enforcement."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.domain.risk.risk_gate import RiskGate
from monika.application.analysis.calculators.macro_bias_filter import evaluate_macro_alignment


@pytest.mark.asyncio
async def test_risk_gate_macro_regime_blocks_commodity_and_crypto_buys_under_strong_dollar():
    gate = RiskGate(settings={"trading": {"risk": {}}})

    # Mock DB session returning DXY 101.50 and 10Y_REAL yield 2.50
    mock_session = AsyncMock()

    mock_dxy = MagicMock()
    mock_dxy.close = 101.50

    mock_yield = MagicMock()
    mock_yield.yield_percent = 2.50

    # execute returns mock scalar_one_or_none
    def side_effect(stmt):
        mock_result = MagicMock()
        # Distinguish DXY vs Yield by string of stmt or by mock return
        stmt_str = str(stmt)
        if "dxy_data" in stmt_str or "close" in stmt_str:
            mock_result.scalar_one_or_none.return_value = mock_dxy
        else:
            mock_result.scalar_one_or_none.return_value = mock_yield
        return mock_result

    mock_session.execute = AsyncMock(side_effect=side_effect)

    # 1. Gold BUY -> Blocked
    ok_gold, reason_gold = await gate._check_macro_regime(mock_session, "XAUUSD", "buy")
    assert ok_gold is False
    assert "Macro Filter Blocked" in reason_gold

    # 2. Oil BUY -> Blocked
    ok_oil, reason_oil = await gate._check_macro_regime(mock_session, "XTIUSD", "buy")
    assert ok_oil is False
    assert "Macro Filter Blocked" in reason_oil

    # 3. BTC BUY -> Blocked
    ok_btc, reason_btc = await gate._check_macro_regime(mock_session, "BTCUSD", "buy")
    assert ok_btc is False
    assert "Macro Filter Blocked" in reason_btc

    # 4. Gold SELL -> Allowed
    ok_gold_sell, _ = await gate._check_macro_regime(mock_session, "XAUUSD", "sell")
    assert ok_gold_sell is True

    # 5. Forex SELL -> Allowed
    ok_eur_sell, _ = await gate._check_macro_regime(mock_session, "EURUSD", "sell")
    assert ok_eur_sell is True


@pytest.mark.asyncio
async def test_risk_gate_macro_regime_allows_buys_under_risk_on_expansion():
    gate = RiskGate(settings={"trading": {"risk": {}}})

    mock_session = AsyncMock()

    mock_dxy = MagicMock()
    mock_dxy.close = 98.20

    mock_yield = MagicMock()
    mock_yield.yield_percent = 1.20

    def side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "dxy_data" in stmt_str or "close" in stmt_str:
            mock_result.scalar_one_or_none.return_value = mock_dxy
        else:
            mock_result.scalar_one_or_none.return_value = mock_yield
        return mock_result

    mock_session.execute = AsyncMock(side_effect=side_effect)

    # Gold BUY -> Allowed
    ok_gold, _ = await gate._check_macro_regime(mock_session, "XAUUSD", "buy")
    assert ok_gold is True

    # BTC BUY -> Allowed
    ok_btc, _ = await gate._check_macro_regime(mock_session, "BTCUSD", "buy")
    assert ok_btc is True


@pytest.mark.asyncio
async def test_evaluate_macro_alignment_blocks_commodity_crypto_buys_under_strong_dollar():
    settings = {"trading": {"edge_strategy": {"macro_bias": {"enabled": True}}}}

    mock_session = AsyncMock()

    mock_dxy = MagicMock()
    mock_dxy.close = 101.80

    mock_yield = MagicMock()
    mock_yield.yield_percent = 2.80

    def side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "dxy_data" in stmt_str or "close" in stmt_str:
            mock_result.scalar_one_or_none.return_value = mock_dxy
        else:
            mock_result.scalar_one_or_none.return_value = mock_yield
        return mock_result

    mock_session.execute = AsyncMock(side_effect=side_effect)

    # XTIUSD BUY -> strong conflict
    res_xti = await evaluate_macro_alignment(mock_session, "XTIUSD", "buy", settings)
    assert res_xti["aligned"] is False
    assert res_xti["strong_conflict"] is True
    assert any("RegimeClassifier" in r for r in res_xti["reasons"])

    # BTCUSD BUY -> strong conflict
    res_btc = await evaluate_macro_alignment(mock_session, "BTCUSD", "buy", settings)
    assert res_btc["aligned"] is False
    assert res_btc["strong_conflict"] is True

    # XTIUSD SELL -> allowed
    res_xti_sell = await evaluate_macro_alignment(mock_session, "XTIUSD", "sell", settings)
    assert res_xti_sell["aligned"] is True
    assert res_xti_sell["strong_conflict"] is False
