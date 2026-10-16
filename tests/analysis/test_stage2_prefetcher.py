import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler

ASSET_UNIVERSE = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XTIUSD", "BTCUSD", "XBRUSD"]


def test_compress_history_includes_tick_volume(mock_async_session):
    bundler = Stage2DataBundler(mock_async_session)
    sample_history = {
        "symbol": "EURUSD",
        "bars": [
            {
                "time": "2026-09-04T12:00:00Z",
                "open": 1.08500,
                "high": 1.08600,
                "low": 1.08450,
                "close": 1.08550,
                "tick_volume": 1250,
            },
            {
                "time": "2026-09-04T13:00:00Z",
                "open": 1.08550,
                "high": 1.08700,
                "low": 1.08500,
                "close": 1.08650,
                "volume": 980,
            },
        ],
    }
    csv_text = bundler._compress_history(sample_history, symbol="EURUSD")
    lines = csv_text.splitlines()
    assert lines[0] == "time,O,H,L,C,V"
    assert "1250" in lines[1]
    assert "980" in lines[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ASSET_UNIVERSE)
async def test_prefetch_asset_fetches_d1_history_for_all_symbols(symbol, mock_async_session):
    bundler = Stage2DataBundler(mock_async_session, settings={"trading": {"asset_universe": ASSET_UNIVERSE}})

    executed_tools = []

    async def mock_execute(tool_name, inp):
        executed_tools.append((tool_name, inp.get("timeframe"), inp.get("symbol")))
        if tool_name == "get_price_history" and inp.get("timeframe") == "D1":
            return {
                "symbol": symbol,
                "timeframe": "D1",
                "bars": [
                    {
                        "time": "2026-09-01T00:00:00Z",
                        "open": 100,
                        "high": 105,
                        "low": 95,
                        "close": 102,
                        "tick_volume": 5000,
                    }
                ],
            }
        return {"data": "mock_val"}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    with (
        patch(
            "monika.application.analysis.validators.core_data_validator.CoreDataValidator.validate_and_fetch_core_data",
            new_callable=AsyncMock,
        ) as mock_val,
        patch("monika.core.validation.data_validator.validate_data_freshness", new_callable=AsyncMock) as mock_fresh,
        patch("monika.core.validation.data_validator.check_data_coherence", new_callable=AsyncMock) as mock_coh,
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
        ) as mock_tfm,
    ):
        mock_val.return_value = (True, {}, [])
        mock_fresh.return_value = {"ready": True, "errors": [], "warnings": []}
        mock_coh.return_value = {"coherent": True, "issues": []}
        mock_tfm.return_value = None
        bundle, res = await bundler.fetch_bundle(symbol)

    assert "price_history_D1_recent" in res, f"D1 history not fetched for {symbol}"
    assert res["price_history_D1_recent"]["timeframe"] == "D1"
    assert any(t[0] == "get_price_history" and t[1] == "D1" and t[2] == symbol for t in executed_tools)


@pytest.mark.asyncio
async def test_prefetch_sentiment_tools_and_core_warnings(mock_async_session):
    bundler = Stage2DataBundler(mock_async_session)

    executed_calls = []

    async def mock_execute(tool_name, inp):
        executed_calls.append((tool_name, dict(inp)))
        return {"data": "mock_val"}

    bundler.executor.execute = AsyncMock(side_effect=mock_execute)

    mock_issues = ["CORE DATA CONTRADICTION: DXY=strengthening but brief says USD='bearish'."]

    with (
        patch(
            "monika.application.analysis.validators.core_data_validator.CoreDataValidator.validate_and_fetch_core_data",
            new_callable=AsyncMock,
        ) as mock_val,
        patch("monika.core.validation.data_validator.validate_data_freshness", new_callable=AsyncMock) as mock_fresh,
        patch("monika.core.validation.data_validator.check_data_coherence", new_callable=AsyncMock) as mock_coh,
        patch(
            "monika.infrastructure.ml.timesfm_engine.TimesFMEngine.get_latest_forecast", new_callable=AsyncMock
        ) as mock_tfm,
    ):
        mock_val.return_value = (True, {}, mock_issues)
        mock_fresh.return_value = {"ready": True, "errors": [], "warnings": []}
        mock_coh.return_value = {"coherent": True, "issues": []}
        mock_tfm.return_value = None

        # 1. Test EURUSD: get_retail_sentiment receives {"symbol": "EURUSD"} and core_data_warnings is populated
        bundle_eur, res_eur = await bundler.fetch_bundle("EURUSD")
        assert "core_data_warnings" in res_eur
        assert res_eur["core_data_warnings"] == mock_issues
        assert any(call[0] == "get_retail_sentiment" and call[1] == {"symbol": "EURUSD"} for call in executed_calls)

        # 2. Test XBRUSD: skips get_retail_sentiment, calls get_fxssi_sentiment with {"symbol": "XBRUSD"}
        executed_calls.clear()
        bundle_xbr, res_xbr = await bundler.fetch_bundle("XBRUSD")
        assert not any(call[0] == "get_retail_sentiment" for call in executed_calls)
        assert any(call[0] == "get_fxssi_sentiment" and call[1] == {"symbol": "XBRUSD"} for call in executed_calls)
