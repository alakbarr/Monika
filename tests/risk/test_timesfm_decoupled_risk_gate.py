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


@pytest.mark.asyncio
async def test_timesfm_expectancy_adaptive_horizon_intraday_passes():
    """Verify that an intraday setup evaluates against the early horizon step rather than 24h widened cone."""
    settings = {
        "timesfm": {
            "enabled": True,
            "expectancy_gate": {"enabled": True, "default_horizon_steps": 6, "noise_cone_buffer_ratio": 0.2},
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()

    # Entry = 100.0, SL = 95.0 (distance 5.0)
    # At step 6 (index 5): Q10 = 85.0, Q30 = 93.0
    #   sl (95.0) > q30 (93.0), BUT (entry - sl) = 5.0, (entry - q10) * 0.2 = (100 - 85) * 0.2 = 3.0.
    #   Since 5.0 is NOT < 3.0, it is outside the 6h noise cone -> PASSES.
    # At step 24 (index 23): Q10 = 70.0, Q30 = 85.0
    #   If evaluated at 24h: (entry - q10) * 0.2 = (100 - 70) * 0.2 = 6.0.
    #   5.0 < 6.0 and 95 > 85 -> would REJECT if not adaptive!
    q10_profile = [95.0, 93.0, 91.0, 89.0, 87.0, 85.0] + [80.0] * 17 + [70.0]
    q30_profile = [97.0, 96.0, 95.0, 94.0, 93.5, 93.0] + [90.0] * 17 + [85.0]
    q90_profile = [105.0] * 23 + [110.0]

    sizing = _create_sizing(entry_price=100.0, stop_loss=95.0, take_profit=108.0)
    proposal = MagicMock()
    proposal.holding_period = "intraday"
    proposal.metadata = {
        "timesfm_quantiles": {
            "q10": q10_profile,
            "q30": q30_profile,
            "q90": q90_profile,
        }
    }

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing, proposal=proposal)
    assert passed is True
    assert "TimesFM expectancy passed" in reason


@pytest.mark.asyncio
async def test_timesfm_expectancy_adaptive_horizon_explicit_swing_rejects():
    """Verify that a swing setup evaluates against the full 24h widened cone and rejects when SL is inside."""
    settings = {
        "timesfm": {
            "enabled": True,
            "expectancy_gate": {"enabled": True, "default_horizon_steps": 6, "noise_cone_buffer_ratio": 0.2},
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()

    q10_profile = [95.0, 93.0, 91.0, 89.0, 87.0, 85.0] + [80.0] * 17 + [70.0]
    q30_profile = [97.0, 96.0, 95.0, 94.0, 93.5, 93.0] + [90.0] * 17 + [85.0]
    q90_profile = [105.0] * 23 + [110.0]

    sizing = _create_sizing(entry_price=100.0, stop_loss=95.0, take_profit=108.0)
    proposal = MagicMock()
    proposal.holding_period = "swing"
    proposal.metadata = {
        "timesfm_quantiles": {
            "q10": q10_profile,
            "q30": q30_profile,
            "q90": q90_profile,
        }
    }

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing, proposal=proposal)
    assert passed is False
    assert "inside high-probability noise cone" in reason


@pytest.mark.asyncio
async def test_timesfm_expectancy_tight_noise_sl_rejected():
    """Verify that an excessively tight noise SL is rejected even within a short 6h horizon."""
    settings = {
        "timesfm": {
            "enabled": True,
            "expectancy_gate": {"enabled": True, "default_horizon_steps": 6, "noise_cone_buffer_ratio": 0.2},
        }
    }
    gate = RiskGate(settings)
    session = AsyncMock()

    # SL = 99.5 (distance 0.5), while 6h Q10 = 85.0 (20% of 15.0 = 3.0). Distance 0.5 < 3.0 -> noise!
    q10_profile = [95.0, 93.0, 91.0, 89.0, 87.0, 85.0] + [80.0] * 17 + [70.0]
    q30_profile = [97.0, 96.0, 95.0, 94.0, 93.5, 93.0] + [90.0] * 17 + [85.0]
    q90_profile = [105.0] * 23 + [110.0]

    sizing = _create_sizing(entry_price=100.0, stop_loss=99.5, take_profit=108.0)
    proposal = MagicMock()
    proposal.holding_period = "intraday"
    proposal.metadata = {
        "timesfm_quantiles": {
            "q10": q10_profile,
            "q30": q30_profile,
            "q90": q90_profile,
        }
    }

    passed, reason = await gate._check_timesfm_expectancy(session, "EURUSD", "BUY", sizing, proposal=proposal)
    assert passed is False
    assert "inside high-probability noise cone" in reason
