import asyncio
import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from execution.mt5_client import MT5Client

class TestMT5Client:

    @pytest.fixture
    def client(self):
        c = MT5Client()
        c._run = AsyncMock()
        c.ensure_connected = AsyncMock(return_value=True)
        return c

    @pytest.mark.asyncio
    async def test_connect(self, client):
        client._run.return_value = True
        res = await client.connect()
        assert res is True
        client._run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_account_info(self, client):
        mock_info = MagicMock(login=123, balance=1000.0, equity=1000.0, margin=0, margin_free=1000.0,
                              margin_level=0, currency="USD", leverage=100, server="Test")
        client._run.return_value = mock_info
        
        res = await client.get_account_info()
        assert res["balance"] == 1000.0
        assert res["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_get_symbol_info(self, client):
        mock_info = MagicMock(digits=2, point=0.01, trade_tick_size=0.01, trade_tick_value=1.0,
                              trade_contract_size=100.0, volume_min=0.01, volume_max=100.0, volume_step=0.01,
                              bid=2000.0, ask=2001.0, spread=100)
        mock_info.name = "XAUUSD"
        client._run.return_value = mock_info
        
        res = await client.get_symbol_info("XAUUSD")
        assert res["symbol"] == "XAUUSD"
        assert res["bid"] == 2000.0

    @pytest.mark.asyncio
    async def test_get_ohlcv(self, client):
        client._resolve_timeframe = MagicMock(return_value=1)
        mock_rates = [
            {"time": 1704067200, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "tick_volume": 100}
        ]
        client._run.return_value = mock_rates
        
        df = await client.get_ohlcv("EURUSD", "H1", 1)
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["close"] == 1.15
        assert "volume" in df.columns

    @pytest.mark.asyncio
    async def test_save_ohlcv(self, client):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        df = pd.DataFrame({
            "time": [pd.Timestamp('2024-01-01', tz='UTC')],
            "open": [1.1], "high": [1.2], "low": [1.0], "close": [1.15], "volume": [100]
        })
        
        saved = await client.save_ohlcv(mock_session, "EURUSD", "H1", df)
        
        assert saved == 1
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_current_price(self, client):
        mock_tick = MagicMock(bid=1999.0, ask=2000.0, last=1999.5, time=1704067200)
        client._run.return_value = mock_tick
        
        res = await client.get_current_price("XAUUSD")
        
        assert res["bid"] == 1999.0
        assert res["ask"] == 2000.0

    @pytest.mark.asyncio
    async def test_place_order(self, client):
        client._run.return_value = {"success": True, "ticket": 12345, "price": 2000.0, "error": None, "retcode": 10009}
        
        res = await client.place_order("XAUUSD", "buy", 0.1)
        
        assert res["success"] is True
        assert res["ticket"] == 12345

    @pytest.mark.asyncio
    async def test_modify_position(self, client):
        client._run.return_value = {"success": True, "error": None, "retcode": 10009}
        
        res = await client.modify_position(12345, sl=1980.0)
        
        assert res["success"] is True

    @pytest.mark.asyncio
    async def test_close_position(self, client):
        client._run.return_value = {"success": True, "price": 2010.0, "profit": 100.0, "error": None, "retcode": 10009}
        
        res = await client.close_position(12345)
        
        assert res["success"] is True
        assert res["profit"] == 100.0

    @pytest.mark.asyncio
    async def test_get_open_positions(self, client):
        client._run.return_value = [
            {"ticket": 123, "symbol": "XAUUSD", "type": 0, "volume": 0.1, "price_open": 2000.0, "time": datetime.now(timezone.utc)}
        ]
        
        res = await client.get_open_positions()
        
        assert len(res) == 1
        assert res[0]["ticket"] == 123

    @pytest.mark.asyncio
    async def test_sync_positions_from_mt5(self, client):
        client.get_open_positions = AsyncMock(return_value=[
            {"ticket": 123, "symbol": "XAUUSD", "type": 0, "volume": 0.1, "price_open": 2000.0, "time": datetime.now(timezone.utc)}
        ])
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = None  # Position not in DB
        
        mock_result2 = MagicMock()
        mock_result2.scalars().all.return_value = [] # No DB-open positions to close
        
        mock_session.execute = AsyncMock(side_effect=[mock_result1, mock_result2])
        
        res = await client.sync_positions_from_mt5(mock_session)
        
        assert res["synced"] == 1
        assert res["closed_in_db"] == 0
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_spread(self, client):
        client.get_symbol_info = AsyncMock(return_value={"symbol": "EURUSD", "spread": 15, "bid": 1.1000, "ask": 1.1015})
        spread_res = await client.get_spread("EURUSD")
        assert spread_res["spread_points"] == 15
        assert spread_res["spread"] == 15
        assert spread_res["bid"] == 1.1000

        client.get_symbol_info = AsyncMock(return_value=None)
        fail_res = await client.get_spread("INVALID")
        assert "error" in fail_res

    @pytest.mark.asyncio
    async def test_get_rates(self, client):
        df_mock = pd.DataFrame([{"time": 1704067200, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 100}])
        client.get_ohlcv = AsyncMock(return_value=df_mock)
        rates = await client.get_rates("EURUSD", "H4", 10)
        assert len(rates) == 1
        assert rates[0]["close"] == 1.15

        client.get_ohlcv = AsyncMock(return_value=None)
        empty_rates = await client.get_rates("EURUSD", "H4", 10)
        assert empty_rates == []

    @pytest.mark.asyncio
    async def test_get_latest_tick(self, client):
        mock_tick = MagicMock(bid=2000.5, ask=2001.0, last=2000.75, spread=50, time=1704067200)
        with patch("execution.mt5_client._get_last_tick", return_value=mock_tick):
            res = await client.get_latest_tick("XAUUSD")
            assert res.bid == 2000.5
            assert res.spread == 50

    @pytest.mark.asyncio
    async def test_run_without_timeout_returns_coro_result(self):
        """Regression test: verify real _run() returns the executed function result when timeout=None."""
        real_client = MT5Client()
        def dummy_worker(x, y):
            return x + y

        result = await real_client._run(dummy_worker, 10, 20, timeout=None)
        assert result == 30, "_run without timeout must await and return result, not None"

    @pytest.mark.asyncio
    async def test_run_with_timeout_returns_coro_result(self):
        """Verify real _run() returns result when timeout is provided."""
        real_client = MT5Client()
        def dummy_worker():
            return "ok"

        result = await real_client._run(dummy_worker, timeout=2.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_market_book_methods(self):
        """Verify market_book_add, market_book_get, and market_book_release."""
        real_client = MT5Client()
        real_client.ensure_connected = AsyncMock(return_value=True)
        real_client._connected = True

        with patch("execution.mt5_client._market_book_add", return_value=True):
            assert await real_client.market_book_add("EURUSD") is True

        mock_book = [{"type": 2, "price": 1.1000, "volume": 100}]
        with patch("execution.mt5_client._market_book_get", return_value=mock_book):
            assert await real_client.market_book_get("EURUSD") == mock_book

        with patch("execution.mt5_client._market_book_release", return_value=True):
            assert await real_client.market_book_release("EURUSD") is True

    @pytest.mark.asyncio
    async def test_priority_resolution_defaults(self):
        """Verify automatic mapping of MT5 functions to priority levels."""
        from execution.mt5_client import (
            PRIORITY_CRITICAL, PRIORITY_STANDARD, PRIORITY_BACKGROUND,
            _place_order, _modify_position, _close_position,
            _copy_rates_from_pos, _copy_rates_range,
            _get_account_info, _get_last_tick
        )
        client = MT5Client()
        # Critical orders
        assert client._resolve_priority(_place_order) == PRIORITY_CRITICAL
        assert client._resolve_priority(_modify_position) == PRIORITY_CRITICAL
        assert client._resolve_priority(_close_position) == PRIORITY_CRITICAL

        # Background bulk rates
        assert client._resolve_priority(_copy_rates_from_pos) == PRIORITY_BACKGROUND
        assert client._resolve_priority(_copy_rates_range) == PRIORITY_BACKGROUND

        # Standard ticks/account
        assert client._resolve_priority(_get_account_info) == PRIORITY_STANDARD
        assert client._resolve_priority(_get_last_tick) == PRIORITY_STANDARD

        # Explicit priority overrides default
        assert client._resolve_priority(_copy_rates_from_pos, explicit_priority=0) == 0

    @pytest.mark.asyncio
    async def test_priority_queue_execution_order(self):
        """Verify that Priority 0 (Critical) tasks preempt Priority 10 (Background) in the queue."""
        import time
        from execution.mt5_client import PRIORITY_CRITICAL, PRIORITY_BACKGROUND
        client = MT5Client()
        execution_order = []

        def slow_initial_task():
            time.sleep(0.08)
            execution_order.append("initial_slow")
            return "initial_done"

        def background_task():
            execution_order.append("background_task")
            return "bg_done"

        def critical_order_task():
            execution_order.append("critical_order")
            return "crit_done"

        # Start initial task to hold the worker thread
        t1 = asyncio.create_task(client._run(slow_initial_task, priority=PRIORITY_BACKGROUND))
        await asyncio.sleep(0.01)  # allow t1 to be picked up by the worker

        # While worker is busy with t1, enqueue background task first, then critical task
        t_bg = asyncio.create_task(client._run(background_task, priority=PRIORITY_BACKGROUND))
        t_crit = asyncio.create_task(client._run(critical_order_task, priority=PRIORITY_CRITICAL))

        await asyncio.gather(t1, t_bg, t_crit)

        # Critical task (Priority 0) must execute before Background task (Priority 10)
        assert execution_order == ["initial_slow", "critical_order", "background_task"]

    @pytest.mark.asyncio
    async def test_copy_rates_range(self, client):
        """Verify copy_rates_range fetches OHLCV dataframe within date range."""
        mock_rates = [
            {"time": 1704067200, "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "tick_volume": 100}
        ]
        client._resolve_timeframe = MagicMock(return_value=1)
        client._run.return_value = mock_rates

        d_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        d_to = datetime(2024, 1, 2, tzinfo=timezone.utc)
        df = await client.copy_rates_range("EURUSD", "H1", d_from, d_to)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["close"] == 1.15
        assert "volume" in df.columns




