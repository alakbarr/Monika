import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import create_mock_async_session
from analysis.validators.precommit_gate import TradePreCommitGate


@pytest.mark.asyncio
async def test_precommit_gate_wait_avoid_passthrough():
    gate = TradePreCommitGate()
    session = create_mock_async_session()
    passed, fails = await gate.verify_precommit(session, {"decision": "wait"}, "BTCUSD")
    assert passed is True
    assert fails == []

    passed, fails = await gate.verify_precommit(session, {"decision": "avoid"}, "BTCUSD")
    assert passed is True
    assert fails == []


@pytest.mark.asyncio
async def test_precommit_gate_geometry_validation():
    gate = TradePreCommitGate()
    session = create_mock_async_session()

    # 1. Missing / zero SL/TP -> FAIL
    passed, fails = await gate.verify_precommit(
        session,
        {"decision": "sell", "entry_price": 83000.0, "stop_loss": 0.0, "take_profit": 78000.0},
        "BTCUSD"
    )
    assert passed is False
    assert any("strictly positive numeric values" in f for f in fails)

    # 2. Invalid SELL geometry (SL <= entry) -> FAIL
    passed, fails = await gate.verify_precommit(
        session,
        {"decision": "sell", "entry_price": 83000.0, "stop_loss": 82000.0, "take_profit": 78000.0},
        "BTCUSD"
    )
    assert passed is False
    assert any("Sell SL" in f for f in fails)

    # 3. Valid SELL geometry -> PASS
    with patch("analysis.validators.market_snapshot.VerifiedMarketSnapshot.compute", new=AsyncMock(return_value={"latest_close": 83000.0})), \
         patch("analysis.validators.market_snapshot.VerifiedMarketSnapshot.validate_plan_against_snapshot", return_value=(True, [])):
        passed, fails = await gate.verify_precommit(
            session,
            {"decision": "sell", "entry_price": 83000.0, "stop_loss": 85000.0, "take_profit": 78000.0},
            "BTCUSD"
        )
        assert passed is True
        assert fails == []

    # 4. Valid BUY geometry -> PASS
    with patch("analysis.validators.market_snapshot.VerifiedMarketSnapshot.compute", new=AsyncMock(return_value={"latest_close": 83000.0})), \
         patch("analysis.validators.market_snapshot.VerifiedMarketSnapshot.validate_plan_against_snapshot", return_value=(True, [])):
        passed, fails = await gate.verify_precommit(
            session,
            {"decision": "buy", "entry_price": 83000.0, "stop_loss": 81000.0, "take_profit": 87000.0},
            "BTCUSD"
        )
        assert passed is True
        assert fails == []
