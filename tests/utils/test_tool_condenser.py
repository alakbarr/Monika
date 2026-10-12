import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from utils.llm.tool_condenser import ToolObservationCondenser


@pytest.mark.asyncio
async def test_tool_condenser_under_threshold():
    condenser = ToolObservationCondenser()
    small_data = {"symbol": "EURUSD", "price": 1.0850}
    res = await condenser.condense_observation("get_market_quote", small_data)
    parsed = json.loads(res)
    assert parsed["symbol"] == "EURUSD"
    assert parsed["price"] == 1.0850


@pytest.mark.asyncio
async def test_tool_condenser_protected_tools_immutable():
    condenser = ToolObservationCondenser()
    protected_payload = {
        "decision": "buy",
        "symbol": "EURUSD",
        "lots": 0.5,
        "huge_filler": "x" * 10000
    }
    res = await condenser.condense_observation("submit_asset_analysis", protected_payload)
    parsed = json.loads(res)
    assert parsed["decision"] == "buy"
    assert len(parsed["huge_filler"]) == 10000


@pytest.mark.asyncio
async def test_tool_condenser_ohlcv_lfsp():
    condenser = ToolObservationCondenser()
    # Generate 50 mock bars
    mock_bars = []
    for i in range(50):
        mock_bars.append({
            "time": f"2026-09-01T{i:02d}:00:00Z",
            "open": 1.0800 + i * 0.0001,
            "high": 1.0850 + i * 0.0001,
            "low": 1.0790 + i * 0.0001,
            "close": 1.0820 + i * 0.0001,
            "volume": 1000 + i
        })
    raw_payload = {"symbol": "EURUSD", "bars": mock_bars, "extra_text": "x" * 6000}
    res = await condenser.condense_observation("get_price_history", raw_payload, symbol="EURUSD")
    parsed = json.loads(res)

    assert "period_extrema" in parsed
    assert parsed["symbol"] == "EURUSD"
    assert len(parsed["recent_bars"]) == 10
    assert "period_open" in parsed["period_extrema"]
    assert "period_high" in parsed["period_extrema"]
    assert "period_low" in parsed["period_extrema"]
    assert "period_close" in parsed["period_extrema"]
    assert "total_bars_span" in parsed
    assert parsed["total_bars_span"] == 50


@pytest.mark.asyncio
async def test_tool_condenser_smc_zones_unmitigated_preservation():
    condenser = ToolObservationCondenser()
    zones = [
        {"type": "OB", "price_low": 1.0800, "price_high": 1.0820, "is_mitigated": False},
        {"type": "FVG", "price_low": 1.0850, "price_high": 1.0870, "is_mitigated": False},
        {"type": "OB", "price_low": 1.0700, "price_high": 1.0720, "is_mitigated": True},
    ]
    # Add filler to push past 1200 tokens
    raw_payload = {"zones": zones, "padding": "x" * 8000}
    res = await condenser.condense_observation("get_smc_zones", raw_payload)
    parsed = json.loads(res)

    assert "zones" in parsed
    assert len(parsed["zones"]) == 2  # Only 2 unmitigated zones preserved
    assert parsed["zones_mitigated_count"] == 1
    assert parsed["zones"][0]["price_low"] == 1.0800
    assert parsed["zones"][1]["price_high"] == 1.0870
