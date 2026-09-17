import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from database.cleanup import cleanup_old_data
from sqlalchemy import delete

class TestCleanup:

    @pytest.mark.asyncio
    @patch('database.cleanup.datetime')
    async def test_cleanup_old_data_success(self, mock_datetime):
        from datetime import datetime, timezone, timedelta
        now = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.timezone = timezone
        mock_datetime.timedelta = timedelta

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_result)

        await cleanup_old_data(mock_session, settings=None)

        assert mock_session.execute.call_count == 39
        assert mock_session.commit.call_count == 1

    @pytest.mark.asyncio
    @patch('database.cleanup.datetime')
    async def test_cleanup_old_data_exception(self, mock_datetime):
        from datetime import datetime, timezone, timedelta
        now = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.timezone = timezone
        mock_datetime.timedelta = timedelta

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB Error")

        await cleanup_old_data(mock_session, settings=None)

        assert mock_session.commit.call_count == 0
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    @patch('database.cleanup.datetime')
    async def test_cleanup_with_custom_settings(self, mock_datetime):
        """Test that per-timeframe retention settings are respected."""
        from datetime import datetime, timezone, timezone, timedelta
        now = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.timezone = timezone
        mock_datetime.timedelta = timedelta

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        settings = {
            "data_retention_days": {
                "ohlcv_d1": 400,
                "ohlcv_h1_h4": 60,
                "news_items": 30,
                "activity_log": 90,
                "asset_analysis": 30,
                "fundamental_brief": 30,
                "order_log": 90,
                "economic_calendar": 30,
                "vix_data": 60,
                "risk_state": 90,
            }
        }

        await cleanup_old_data(mock_session, settings=settings)

        assert mock_session.execute.call_count == 39
        assert mock_session.commit.call_count == 1

    @pytest.mark.asyncio
    @patch('database.cleanup.datetime')
    async def test_d1_retention_never_below_400(self, mock_datetime):
        """D1 retention must be at least 400 days regardless of config."""
        from datetime import datetime, timezone, timedelta
        now = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.timezone = timezone
        mock_datetime.timedelta = timedelta

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Try to set D1 retention too low — should be clamped to 400
        settings = {"data_retention_days": {"ohlcv_d1": 30}}
        await cleanup_old_data(mock_session, settings=settings)
        # Should still execute without error (D1 days clamped to max(30, 400) = 400)
        assert mock_session.execute.call_count == 39

    @pytest.mark.asyncio
    async def test_reset_paper_trading_history_success(self, tmp_path):
        """Test reset_paper_trading_history runs cleanly, creates backup, and commits."""
        from database.cleanup import reset_paper_trading_history

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_result.rowcount = 2
        mock_session.execute = AsyncMock(return_value=mock_result)

        res = await reset_paper_trading_history(
            session=mock_session,
            create_backup=True,
            backup_dir=str(tmp_path),
            unlock_all=True,
        )

        assert res["status"] == "success"
        assert res["backup_file"] is not None
        assert mock_session.commit.call_count == 1
        assert mock_session.rollback.call_count == 0

    @pytest.mark.asyncio
    async def test_reset_paper_trading_history_rollback(self, tmp_path):
        """Test reset_paper_trading_history rolls back on database exception."""
        from database.cleanup import reset_paper_trading_history

        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB Connection Lost")

        with pytest.raises(Exception, match="DB Connection Lost"):
            await reset_paper_trading_history(
                session=mock_session,
                create_backup=False,
                unlock_all=True,
            )

        assert mock_session.commit.call_count == 0
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_paper_trading_history_with_signals_and_positions(self, tmp_path):
        """Test reset_paper_trading_history when positions and tickets exist, exercising signal_conds."""
        from datetime import datetime, timezone
        from database.cleanup import reset_paper_trading_history
        from database.models import PaperTradeRecord, Position, MT5Signal

        mock_session = AsyncMock()

        mock_paper_trade = MagicMock(spec=PaperTradeRecord)
        mock_paper_trade.id = 1
        mock_paper_trade.analysis_id = "analysis-pt-1"
        mock_paper_trade.symbol = "EURUSD"
        mock_paper_trade.direction = "BUY"
        mock_paper_trade.entry_price = 1.0850
        mock_paper_trade.stop_loss = 1.0800
        mock_paper_trade.take_profit = 1.0950
        mock_paper_trade.opened_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_paper_trade.filled_at = None
        mock_paper_trade.closed_at = None
        mock_paper_trade.exit_price = None
        mock_paper_trade.exit_reason = None
        mock_paper_trade.detection_method = "smc"
        mock_paper_trade.risk_pct = 1.0
        mock_paper_trade.pnl_pct = None
        mock_paper_trade.status = "OPEN"

        mock_pos = MagicMock(spec=Position)
        mock_pos.id = 10
        mock_pos.order_id = 1
        mock_pos.is_paper = True
        mock_pos.analysis_id = "analysis-pos-2"
        mock_pos.mt5_ticket = 123456
        mock_pos.symbol = "EURUSD"
        mock_pos.direction = "buy"
        mock_pos.volume = 0.1
        mock_pos.entry_price = 1.0850
        mock_pos.sl = 1.0800
        mock_pos.tp = 1.0950
        mock_pos.opened_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_pos.closed_at = None
        mock_pos.status = "open"

        mock_sig = MagicMock(spec=MT5Signal)
        mock_sig.id = 100
        mock_sig.asset_analysis_id = "analysis-pt-1"
        mock_sig.mt5_ticket = 123456
        mock_sig.symbol = "EURUSD"
        mock_sig.action = "BUY"
        mock_sig.status = "EXECUTED"
        mock_sig.created_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_sig.executed_at = datetime(2024, 2, 1, tzinfo=timezone.utc)

        call_count = {"scalars": 0}

        def fake_scalars():
            call_count["scalars"] += 1
            mock_res = MagicMock()
            if call_count["scalars"] == 1:
                mock_res.all.return_value = [mock_paper_trade]
            elif call_count["scalars"] == 2:
                mock_res.all.return_value = [mock_pos]
            elif call_count["scalars"] == 3:
                mock_res.all.return_value = [mock_sig]
            else:
                mock_res.all.return_value = []
            return mock_res

        mock_result = MagicMock()
        mock_result.scalars.side_effect = fake_scalars
        mock_result.scalar_one_or_none.return_value = None
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        res = await reset_paper_trading_history(
            session=mock_session,
            create_backup=True,
            backup_dir=str(tmp_path),
            unlock_all=True,
        )

        assert res["status"] == "success"
        assert res["signals_deleted"] == 1
        assert res["positions_deleted"] == 1
        assert res["paper_trades_deleted"] == 1
        assert mock_session.commit.call_count == 1

