import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.tools.composite_tools import (
    execute_market_context,
    execute_technical_analysis,
    execute_price_data,
    execute_institutional_data
)
from analysis.tools.tools_definitions import (
    GET_MARKET_CONTEXT,
    GET_TECHNICAL_ANALYSIS,
    GET_PRICE_DATA,
    GET_INSTITUTIONAL_DATA,
    STAGE2_TOOLS_V2
)

@pytest.mark.asyncio
async def test_composite_tools_execution():
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    ctx = await execute_market_context(mock_executor, symbol="EURUSD")
    assert "market_session" in ctx
    assert "dxy" in ctx
    assert "vix" in ctx
    assert "fundamental_brief" in ctx
    assert "open_positions" in ctx
    assert "risk_state" in ctx

    tech = await execute_technical_analysis(mock_executor, symbol="EURUSD", timeframes=["D1", "H4"])
    assert "D1" in tech
    assert "H4" in tech
    assert "technical_indicators" in tech["D1"]
    assert "smc_zones" in tech["H4"]

    price = await execute_price_data(mock_executor, symbol="EURUSD", direction="buy", entry_price=1.10)
    assert "price_history" in price
    assert "atr" in price
    assert "optimal_levels" in price

    inst = await execute_institutional_data(mock_executor, symbol="BTCUSD", cot_code="099741")
    assert "cot_signals" in inst
    assert "cot_report" in inst
    assert "fear_greed" in inst
    assert "funding_rate" in inst

def test_stage2_tools_v2_definitions():
    assert len(STAGE2_TOOLS_V2) >= 9
    tool_names = [t["name"] for t in STAGE2_TOOLS_V2]
    assert "get_technical_analysis" in tool_names
    assert "get_price_data" in tool_names
    assert "get_institutional_data" in tool_names
    assert "submit_asset_analysis" in tool_names
