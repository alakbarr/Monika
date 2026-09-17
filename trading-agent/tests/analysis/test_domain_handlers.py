"""Unit tests for modular domain tool handlers and new utilities."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import pandas as pd

from analysis.tools.domain.execution_handlers import ExecutionToolHandlers
from analysis.tools.domain.position_handlers import PositionToolHandlers
from analysis.tools.domain.macro_handlers import MacroToolHandlers
from analysis.tools.domain.sentiment_handlers import SentimentToolHandlers
from analysis.tools.domain.technical_handlers import TechnicalToolHandlers
from utils.market.session_info import get_current_market_session
from risk.position_sizing import calculate_lot_size
from risk.risk_gate import get_current_risk_state
from backtest.decision_memory import DecisionMemoryManager
from backtest.offline_signal_engine import OfflineSignalEngine


@pytest.mark.asyncio
async def test_execution_handlers():
    handlers = ExecutionToolHandlers()
    with patch("risk.position_sizing.calculate_lot_size", new_callable=AsyncMock) as mock_calc:
        mock_calc.return_value = {"recommended_lots": 0.5, "is_valid": True}
        res = await handlers.calculate_position_size("EURUSD", 1.1000, 1.0950, risk_pct=1.0)
        assert res["recommended_lots"] == 0.5

    with patch("execution.mt5_client.get_mt5_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_spread = AsyncMock(return_value={"symbol": "EURUSD", "spread_points": 12})
        mock_get_client.return_value = mock_client
        spread = await handlers.get_spread_snapshot("EURUSD")
        assert spread["spread_points"] == 12


@pytest.mark.asyncio
async def test_position_handlers():
    handlers = PositionToolHandlers()
    with patch("execution.mt5_client.get_mt5_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_open_positions = AsyncMock(return_value=[{"ticket": 12345}])
        mock_client.get_account_info = AsyncMock(return_value={"equity": 10500.0})
        mock_get_client.return_value = mock_client

        pos = await handlers.get_open_positions()
        assert len(pos) == 1
        assert pos[0]["ticket"] == 12345

        acc = await handlers.get_account_info()
        assert acc["equity"] == 10500.0

    with patch("risk.risk_gate.get_current_risk_state", new_callable=AsyncMock) as mock_risk:
        mock_risk.return_value = {"current_drawdown_pct": 0.5, "is_trading_paused": False}
        r_state = await handlers.get_risk_state()
        assert r_state["is_trading_paused"] is False


@pytest.mark.asyncio
async def test_macro_handlers_and_session_info():
    handlers = MacroToolHandlers()

    # Test session info
    dt_overlap = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
    sess_overlap = get_current_market_session(dt_overlap)
    assert sess_overlap["is_london_ny_overlap"] is True
    assert sess_overlap["session_modifier"] == 1
    assert "London" in sess_overlap["active_sessions"]
    assert "New York" in sess_overlap["active_sessions"]

    dt_offpeak = datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc)
    sess_offpeak = get_current_market_session(dt_offpeak)
    assert sess_offpeak["is_off_peak"] is True
    assert sess_offpeak["session_modifier"] == -2

    # Test macro handlers
    sess = await handlers.get_market_session()
    assert "active_sessions" in sess

    with patch("data_sources.cftc_cot.CFTCCOTFetcher.fetch_all", new_callable=AsyncMock) as mock_cot:
        mock_cot.return_value = 5
        mock_session = AsyncMock()
        cot_res = await handlers.get_cot_report(session=mock_session)
        assert cot_res["status"] == "success"
        assert cot_res["new_records"] == 5

    with patch("data_sources.vix_yfinance.VIXFetcher.fetch", new_callable=AsyncMock) as mock_vix:
        mock_vix.return_value = 3
        mock_session = AsyncMock()
        vix_res = await handlers.get_vix(session=mock_session)
        assert vix_res["new_records"] == 3


@pytest.mark.asyncio
async def test_sentiment_handlers():
    handlers = SentimentToolHandlers()
    mock_session = AsyncMock()

    # get_fear_greed
    with patch("data_sources.fear_greed.FearGreedFetcher.fetch", new_callable=AsyncMock) as mock_fg:
        mock_fg.return_value = {"current_value": 45, "classification": "Neutral"}
        res = await handlers.get_fear_greed(session=mock_session)
        assert res["current_value"] == 45

    # get_retail_sentiment
    with patch("scrapers.sentiment.myfxbook_sentiment.MyFxBookSentimentFetcher.fetch", new_callable=AsyncMock) as mock_myfx:
        mock_myfx.return_value = {"symbol": "EURUSD", "long_pct": 40.0, "short_pct": 60.0}
        ret_res = await handlers.get_retail_sentiment("EURUSD", session=mock_session)
        assert ret_res["long_pct"] == 40.0

    # get_funding_rate
    with patch("utils.api.http_retry.fetch_with_retry", new_callable=AsyncMock) as mock_retry:
        mock_retry.return_value = [{"fundingRate": "0.0001", "fundingTime": 1720000000}]
        fund_res = await handlers.get_funding_rate("BTCUSD")
        assert fund_res["funding_rate"] == 0.0001


@pytest.mark.asyncio
async def test_technical_handlers():
    handlers = TechnicalToolHandlers()
    mock_session = AsyncMock()

    with patch("execution.mt5_client.get_mt5_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rates = AsyncMock(return_value=[{"time": 1, "close": 1.1000}])
        mock_get_client.return_value = mock_client
        rates = await handlers.get_price_history("EURUSD", "H4", 50)
        assert len(rates) == 1

    with patch("indicators.technical.TechnicalIndicatorCalculator.get_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = {"ATR": {"value": 0.0045}, "RSI": {"value": 55.0}}
        tech_res = await handlers.get_technical_indicators("EURUSD", "H4", session=mock_session)
        assert "indicators" in tech_res
        assert tech_res["indicators"]["RSI"]["value"] == 55.0

        atr_res = await handlers.get_atr("EURUSD", "H4", session=mock_session)
        assert atr_res["atr"] == 0.0045


def test_offline_signal_engine_atr():
    engine = OfflineSignalEngine({})
    data = {
        "High": [10.0, 11.0, 12.0, 11.5, 12.5],
        "Low": [9.0, 9.5, 10.5, 10.0, 11.0],
        "Close": [9.5, 10.5, 11.0, 11.2, 12.0]
    }
    df = pd.DataFrame(data)
    atr = engine._calculate_atr(df, period=3)
    assert isinstance(atr, pd.Series)
    assert not atr.empty


def test_decision_memory_init():
    mgr = DecisionMemoryManager(settings=None)
    assert mgr.settings is not None
