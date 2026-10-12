# ==============================================================================
# File: tests/analysis/test_multi_timeframe_tool.py
# ==============================================================================

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from database.models import TreasuryYield, BondYieldData
from analysis.tools.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_tool_get_bond_yield_spreads(db_session):
    """Test get_bond_yield_spreads handler in ToolExecutor."""
    now = datetime.now(timezone.utc)
    
    # Insert US 10Y
    db_session.add(TreasuryYield(tenor="10Y", yield_percent=4.25, date=now))
    db_session.add(TreasuryYield(tenor="10Y", yield_percent=4.20, date=now - timedelta(days=4)))
    
    # Insert German Bund
    db_session.add(BondYieldData(country_tenor="DE_10Y", yield_percent=2.25, date=now))
    db_session.add(BondYieldData(country_tenor="DE_10Y", yield_percent=2.22, date=now - timedelta(days=4)))
    
    # Insert UK Gilt
    db_session.add(BondYieldData(country_tenor="UK_10Y", yield_percent=3.85, date=now))
    
    await db_session.commit()

    executor = ToolExecutor(db_session, settings={})
    res = await executor.execute("get_bond_yield_spreads", {"days_back": 10})

    assert "yield_spreads" in res
    assert "DE_10Y" in res["yield_spreads"]
    assert res["yield_spreads"]["DE_10Y"]["current_spread"] == 2.0  # 4.25 - 2.25
    assert res["yield_spreads"]["DE_10Y"]["target_pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_tool_get_multi_timeframe_summary(db_session):
    """Test get_multi_timeframe_summary handler in ToolExecutor."""
    executor = ToolExecutor(db_session, settings={}, symbol="EURUSD")
    res = await executor.execute("get_multi_timeframe_summary", {"symbol": "EURUSD"})

    assert "multi_timeframe" in res
    assert "H1" in res["multi_timeframe"]
    assert "H4" in res["multi_timeframe"]
    assert "D1" in res["multi_timeframe"]
    assert "regimes_summary" in res
