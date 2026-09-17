import pytest
from unittest.mock import AsyncMock, patch
from analysis.tools.tool_executor import ToolExecutor
from analysis.tools.tools_definitions import (
    GET_TIMESFM_FORECAST,
    STAGE2_TOOLS,
    TELEGRAM_TOOLS,
    ALL_TOOLS,
)


@pytest.fixture
def fake_forecast():
    return {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "current_price": 2700.0,
        "quantiles": {
            "q10": [2690.0, 2695.0],
            "q50": [2700.0, 2710.0],
            "q90": [2715.0, 2725.0],
        },
        "expected_range": 30.0,
        "quantile_skew": 0.12,
        "volatility_expansion_ratio": 1.1,
    }


@pytest.mark.asyncio
async def test_tool_get_timesfm_forecast_success(fake_forecast):
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    with patch("indicators.timesfm_engine.TimesFMEngine.get_or_generate_forecast", new_callable=AsyncMock) as mock_get_fc:
        mock_get_fc.return_value = fake_forecast

        result = await executor.execute("get_timesfm_forecast", {"symbol": "XAUUSD", "timeframe": "H1", "horizon_steps": 24})

        assert result["status"] == "success"
        assert result["symbol"] == "XAUUSD"
        assert result["q10_lower_bound"] == 2695.0
        assert result["q50_median"] == 2710.0
        assert result["q90_upper_bound"] == 2725.0
        assert result["trend"] == "BULLISH"
        assert result["confidence"] > 0.5


@pytest.mark.asyncio
async def test_tool_get_timesfm_forecast_positional_and_kwargs(fake_forecast):
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    with patch("indicators.timesfm_engine.TimesFMEngine.get_or_generate_forecast", new_callable=AsyncMock) as mock_get_fc:
        mock_get_fc.return_value = fake_forecast

        # Positional call
        res_pos = await executor._tool_get_timesfm_forecast("XAUUSD", "H1", 24)
        assert res_pos["status"] == "success"
        assert res_pos["symbol"] == "XAUUSD"
        assert res_pos["timeframe"] == "H1"
        assert res_pos["horizon_steps"] == 24

        # Kwargs call
        res_kw = await executor._tool_get_timesfm_forecast(symbol="XAUUSD", timeframe="H4", horizon_steps=12)
        assert res_kw["status"] == "success"
        assert res_kw["symbol"] == "XAUUSD"


@pytest.mark.asyncio
async def test_tool_get_timesfm_forecast_missing_symbol():
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    result = await executor.execute("get_timesfm_forecast", {})
    assert result["status"] == "error"


def test_tool_definition_registration():
    assert GET_TIMESFM_FORECAST["name"] == "get_timesfm_forecast"
    assert any(t["name"] == "get_timesfm_forecast" for t in STAGE2_TOOLS)
    assert any(t["name"] == "get_timesfm_forecast" for t in TELEGRAM_TOOLS)
    assert any(t["name"] == "get_timesfm_forecast" for t in ALL_TOOLS)
