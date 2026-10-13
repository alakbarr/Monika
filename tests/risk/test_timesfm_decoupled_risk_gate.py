"""
Unit tests for decoupled TimesFM Expectancy validation in RiskGate.
Verifies pure mathematical evaluation against quantiles without ML engine instantiation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from monika.domain.risk.risk_gate import RiskGate, SizingResult


def _create_sizing(
    symbol: str = "EURUSD",
    direction: str = "buy",
    entry_price: float = 1.1000,
    stop_loss: float = 1.0950,
    take_profit: float = 1.1080,
) -> SizingResult:
    return SizingResult(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=abs(entry_price - stop_loss),
        sl_distance_pips=50.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
    )


@pytest.mark.asyncio
async def test_timesfm_expectancy_precomputed_quantiles_buy_valid():
    settings = {
        "timesfm": {
            "enabled": True,
            "expectancy_gate": {"enabled": True},
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()

    sizing = _create_sizing(take_profit=1.1080)
    proposal = MagicMock()
    proposal.metadata = {
        "timesfm_quantiles": {
            "q10": [1.0900],
            "q30": [1.0940],
            "q70": [1.1050],
            "q90": [1.1100],
        }
    }

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing, proposal=proposal)
    assert passed is True
    assert "TimesFM expectancy passed" in reason


@pytest.mark.asyncio
async def test_timesfm_expectancy_precomputed_quantiles_tp_exceeds_ceiling():
    settings = {
        "timesfm": {
            "enabled": True,
            "expectancy_gate": {"enabled": True},
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()

    # TP 1.1500 exceeds Q90 (1.1000 * 1.02 = 1.1220)
    sizing = _create_sizing(take_profit=1.1500)
    proposal = MagicMock()
    proposal.metadata = {
        "timesfm_quantiles": {
            "q10": [1.0900],
            "q90": [1.1000],
        }
    }

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing, proposal=proposal)
    assert passed is False
    assert "exceeds TimesFM Q90 ceiling" in reason


@pytest.mark.asyncio
async def test_timesfm_expectancy_disabled_gate():
    settings = {
        "timesfm": {
            "enabled": False,
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()
    sizing = _create_sizing(take_profit=1.2000)

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing)
    assert passed is True
    assert "TimesFM expectancy gate disabled" in reason
