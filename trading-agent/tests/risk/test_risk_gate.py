import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from risk.risk_gate import RiskGate, RiskVerdict
from risk.position_sizing import SizingResult

class TestRiskGate:
    @pytest.fixture
    def settings(self):
        return {
            "trading": {
                "risk": {
                    "max_daily_drawdown_percent": 3.0,
                    "max_concurrent_positions": 5,
                    "max_lot_size": 1.0,
                    "correlation_limit": 3,
                    "news_window_minutes": 15,
                    "max_portfolio_heat_pct": 4.0
                }
            }
        }

    @pytest.fixture
    def sizing(self):
        return SizingResult(
            symbol="XAUUSD", direction="buy", entry_price=2000.0, stop_loss=1990.0,
            take_profit=2020.0, account_equity=10000.0, risk_percent=1.0,
            risk_amount_usd=100.0, sl_distance_price=10.0, sl_distance_pips=1000.0,
            pip_value_per_lot=1.0, raw_lots=0.1, recommended_lots=0.1, rr_ratio=2.0,
            is_valid=True
        )

    def _setup_mock_session(self, return_value_scalar=None, return_value_scalars=None):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = return_value_scalar
        
        if return_value_scalars is not None:
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = return_value_scalars
            mock_result.scalars.return_value = mock_scalars
            
        mock_session.execute.return_value = mock_result
        return mock_session

    @pytest.mark.asyncio
    async def test_check_not_paused(self, settings):
        gate = RiskGate(settings)
        mock_state = MagicMock()
        mock_state.trading_paused = True
        mock_state.reason = "test reason"
        mock_session = self._setup_mock_session(mock_state)
        
        ok, reason = await gate._check_not_paused(mock_session)
        assert not ok
        assert "test reason" in reason
        
        mock_state.trading_paused = False
        ok, reason = await gate._check_not_paused(mock_session)
        assert ok

    @pytest.mark.asyncio
    async def test_check_sizing_valid(self, settings, sizing):
        gate = RiskGate(settings)
        
        ok, reason = await gate._check_sizing_valid(sizing)
        assert ok
        
        sizing.is_valid = False
        ok, reason = await gate._check_sizing_valid(sizing)
        assert not ok
        
        sizing.is_valid = True
        sizing.recommended_lots = 0
        ok, reason = await gate._check_sizing_valid(sizing)
        assert not ok

    @pytest.mark.asyncio
    async def test_check_daily_drawdown(self, settings):
        gate = RiskGate(settings)
        mock_state = MagicMock()
        mock_state.current_drawdown = -400.0 # -4% of 10000
        mock_state.daily_pnl = -400.0
        mock_session = self._setup_mock_session(mock_state)
        
        ok, reason = await gate._check_daily_drawdown(mock_session, 10000.0)
        assert not ok
        assert ">= limit 3.0" in reason
        
        mock_state.current_drawdown = -100.0 # -1%
        mock_state.daily_pnl = -100.0
        ok, reason = await gate._check_daily_drawdown(mock_session, 10000.0)
        assert ok

    @pytest.mark.asyncio
    async def test_check_max_positions(self, settings):
        gate = RiskGate(settings)
        mock_session = self._setup_mock_session(5)
        
        ok, reason = await gate._check_max_positions(mock_session)
        assert not ok
        
        mock_session.execute.return_value.scalar_one_or_none.return_value = 3
        ok, reason = await gate._check_max_positions(mock_session)
        assert ok

    @pytest.mark.asyncio
    async def test_check_no_duplicate(self, settings):
        gate = RiskGate(settings)
        mock_session = self._setup_mock_session(1)
        
        ok, reason = await gate._check_no_duplicate(mock_session, "XAUUSD")
        assert not ok
        
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        ok, reason = await gate._check_no_duplicate(mock_session, "XAUUSD")
        assert ok

    @pytest.mark.asyncio
    async def test_check_news_window(self, settings):
        gate = RiskGate(settings)
        
        mock_event = MagicMock()
        mock_event.event_time = datetime.now(timezone.utc)
        mock_event.event_name = "NFP"
        mock_event.currency = "USD"
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        # Scenario 1: SystemConfig has fresh timestamp, but high-impact event is active
        mock_cfg = MagicMock()
        mock_cfg.value = datetime.now(timezone.utc).isoformat()
        
        mock_res_cfg = MagicMock()
        mock_res_cfg.scalar_one_or_none.return_value = mock_cfg
        
        mock_res_count = MagicMock()
        mock_res_count.scalar_one_or_none.return_value = 50
        
        mock_res_future = MagicMock()
        mock_res_future.scalar_one_or_none.return_value = 1
        
        mock_res_event = MagicMock()
        mock_res_event.scalar_one_or_none.return_value = mock_event
        
        mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_event]
        
        ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
        assert not ok
        assert "NFP" in reason
        
        # Scenario 2: SystemConfig fresh, no high-impact events
        mock_res_none = MagicMock()
        mock_res_none.scalar_one_or_none.return_value = None
        
        mock_session.execute.side_effect = [mock_res_cfg, mock_res_count, mock_res_future, mock_res_none]
        ok, reason = await gate._check_news_window(mock_session, "XAUUSD")
        assert ok

    @pytest.mark.asyncio
    async def test_check_correlation(self, settings):
        gate = RiskGate(settings)
    
        pos1 = MagicMock()
        pos1.symbol = "EURUSD"
        pos1.direction = "buy"
        pos1.volume = 1.0
    
        pos2 = MagicMock()
        pos2.symbol = "GBPUSD" # Highly correlated to EURUSD (0.85)
        pos2.direction = "buy"
        pos2.volume = 1.0
        
        # Test adding EURUSD buy when GBPUSD buy is open
        mock_session = self._setup_mock_session(return_value_scalars=[pos2, pos2, pos2, pos2])
        
        # exposure will be 1.0 (base) + 4 * 0.85 = 4.4 > 3
        ok, reason = await gate._check_correlation(mock_session, "EURUSD", "buy")
        assert not ok
        assert "Correlated exposure limit exceeded" in reason



    @pytest.mark.asyncio
    async def test_main_check(self, settings, sizing):
        gate = RiskGate(settings)
        gate._check_not_paused = AsyncMock(return_value=(True, ""))
        gate._check_sizing_valid = AsyncMock(return_value=(True, ""))
        gate._check_daily_drawdown = AsyncMock(return_value=(True, ""))
        gate._check_max_positions = AsyncMock(return_value=(True, ""))
        gate._check_no_duplicate = AsyncMock(return_value=(True, ""))
        gate._check_news_window = AsyncMock(return_value=(True, ""))
        gate._check_correlation = AsyncMock(return_value=(True, ""))
        gate._check_data_freshness = AsyncMock(return_value=(True, ""))
        gate.assess_weekend_gap_risk = AsyncMock(return_value=(True, ""))
        gate._check_rollover_window = AsyncMock(return_value=(True, ""))
        gate._log_verdict = AsyncMock()
    
        mock_session = self._setup_mock_session(return_value_scalars=[])
        mock_session.add = MagicMock()
        verdict = await gate.check(mock_session, "XAUUSD", "buy", sizing, 10000.0)
        
        assert verdict.approved
        assert len(verdict.checks_failed) == 0
        gate._log_verdict.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_risk_state(self, settings):
        gate = RiskGate(settings)
        
        # Scenario 1: New risk state
        mock_session = self._setup_mock_session(None)
        mock_session.add = MagicMock()
        
        await gate.update_risk_state(mock_session, -100.0, 10000.0)
        
        added_state = mock_session.add.call_args[0][0]
        assert added_state.daily_pnl == -100.0
        assert added_state.current_drawdown == -100.0
        assert not added_state.trading_paused
        
        # Scenario 2: Existing risk state exceeding max limit
        existing_state = MagicMock()
        existing_state.daily_pnl = -250.0
        existing_state.current_drawdown = -250.0
        existing_state.trading_paused = False
        mock_session.execute.return_value.scalar_one_or_none.return_value = existing_state
        
        with patch("utils.infra.notifier.AgentNotifier") as mock_notifier:
            mock_notifier.return_value.send_critical = AsyncMock()
            # -100 pnl -> total drawdown = -350 -> 3.5% >= 3.0%
            await gate.update_risk_state(mock_session, -100.0, 10000.0)
            
            assert existing_state.daily_pnl == -350.0
            assert existing_state.current_drawdown == -350.0
            assert existing_state.trading_paused
            assert "Auto-paused" in existing_state.reason
            mock_notifier.return_value.send_critical.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pause_resume(self, settings):
        gate = RiskGate(settings)
        
        mock_state = MagicMock()
        mock_state.trading_paused = False
        mock_session = self._setup_mock_session(mock_state)
        
        await gate.pause_trading(mock_session, "manual test")
        assert mock_state.trading_paused
        assert mock_state.reason == "manual test"
        mock_session.commit.assert_awaited()
        
        await gate.resume_trading(mock_session)
        assert not mock_state.trading_paused
        assert mock_state.reason is None

    @pytest.mark.asyncio
    async def test_assess_weekend_gap_risk_saturday_blocked(self, settings):
        gate = RiskGate(settings)
        mock_session = AsyncMock()
        
        # Saturday at 10:00 UTC (weekday == 5, hour == 10)
        saturday_dt = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
        with patch("utils.clock.now", return_value=saturday_dt):
            # Non-exempt symbol (EURUSD) must be blocked on Saturday
            ok, reason = await gate.assess_weekend_gap_risk(mock_session, "EURUSD")
            assert not ok
            assert "Saturday" in reason
            
            # Exempt symbol (BTCUSD) must pass
            ok, reason = await gate.assess_weekend_gap_risk(mock_session, "BTCUSD")
            assert ok
            assert "exempted" in reason

    @pytest.mark.asyncio
    async def test_check_vix_threshold_monday_preserves_real_vix(self, settings):
        """Verify Monday morning with Friday VIX (3.0-4.5d old) uses real VIX, not defensive default."""
        gate = RiskGate(settings)
        mock_vix = MagicMock()
        mock_vix.close = 14.5
        mock_vix.date = datetime(2026, 8, 28, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_session = self._setup_mock_session(mock_vix)
        monday_dt = datetime(2026, 8, 31, 7, 3, 52, tzinfo=timezone.utc) # 3.29 days old
        
        with patch("utils.clock.now", return_value=monday_dt):
            ok, reason = await gate._check_vix_threshold(mock_session, as_of=monday_dt)
            assert ok is True
            assert "VIX=14.5" in reason
            assert "weekend/Monday expected delay" in reason
            assert "defaulting to" not in reason

    @pytest.mark.asyncio
    async def test_check_vix_threshold_stale_falls_back_to_defensive(self, settings):
        """Verify truly stale VIX (> 4.5d old) falls back to defensive threshold."""
        gate = RiskGate(settings)
        mock_vix = MagicMock()
        mock_vix.close = 14.5
        mock_vix.date = datetime(2026, 8, 28, 0, 0, 0, tzinfo=timezone.utc)
        
        mock_session = self._setup_mock_session(mock_vix)
        wednesday_dt = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc) # 5.5 days old
        
        with patch("utils.clock.now", return_value=wednesday_dt):
            ok, reason = await gate._check_vix_threshold(mock_session, as_of=wednesday_dt)
            assert ok is True
            assert "defaulting to 25.0" in reason

    @pytest.mark.asyncio
    async def test_get_daily_risk_cutoff_and_state(self, settings):
        """Verify get_daily_risk_cutoff and get_current_risk_state work seamlessly."""
        from risk.risk_gate import get_daily_risk_cutoff, get_current_risk_state
        now_dt = datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone.utc)
        cutoff = get_daily_risk_cutoff(now_dt, {"daily_rollover_utc_hour": 21})
        assert cutoff.hour == 21

        # No session test
        state_no_sess = await get_current_risk_state(None)
        assert state_no_sess["status"] == "unavailable"

        # Mock session test with risk_row
        mock_risk_state = MagicMock()
        mock_risk_state.date = now_dt
        mock_risk_state.daily_pnl = 150.0
        mock_risk_state.current_drawdown = 0.8
        mock_risk_state.trading_paused = False
        mock_risk_state.reason = None

        mock_session = AsyncMock()
        mock_exec = AsyncMock()
        mock_exec.scalar_one_or_none.return_value = mock_risk_state
        mock_exec.scalar.return_value = 2
        mock_session.execute.return_value = mock_exec

        state = await get_current_risk_state(mock_session, settings)
        assert state["current_drawdown_pct"] == 0.8
        assert state["is_trading_paused"] is False
        assert state["open_positions_count"] == 2
        assert state["status"] == "normal"

    @pytest.mark.asyncio
    async def test_check_daily_drawdown_first_trade_unrealized_loss(self, settings):
        """Verify that first trade of the day (state is None) does NOT bypass floating loss checks."""
        gate = RiskGate(settings)
        # state is None (no trades yet today)
        mock_session = self._setup_mock_session(None)
        
        # Mock MT5 open positions with a big floating loss of -$500 (-5% on $10,000 equity)
        mock_mt5 = AsyncMock()
        mock_mt5.get_open_positions.return_value = [{"ticket": 123, "profit": -500.0}]
        gate._mt5 = mock_mt5
        gate.dry_run = False

        ok, reason = await gate._check_daily_drawdown(mock_session, 10000.0)
        assert not ok
        assert "Unrealized drawdown" in reason or "Daily PnL loss" in reason

    @pytest.mark.asyncio
    async def test_check_daily_drawdown_first_trade_paper_unrealized_loss(self, settings):
        """Verify that first trade of the day in dry-run mode computes paper trade unrealized loss."""
        gate = RiskGate(settings)
        gate.dry_run = True

        mock_paper = MagicMock()
        mock_paper.symbol = "EURUSD"
        mock_paper.status = "open"
        mock_paper.direction = "buy"
        mock_paper.entry_price = 1.1000
        mock_paper.stop_loss = 1.0900  # sl_dist = 0.0100
        mock_paper.risk_pct = 5.0

        mock_session = AsyncMock()
        
        # 1st execute: select(RiskState) -> None
        exec_state = MagicMock()
        exec_state.scalar_one_or_none.return_value = None

        # 2nd execute: select(PaperTradeRecord) -> [mock_paper]
        exec_paper = MagicMock()
        exec_paper.scalars.return_value.all.return_value = [mock_paper]

        # 3rd execute: select(PriceOHLCV.close) -> 1.0920 (diff = -0.0080 -> -4% of equity)
        exec_price = MagicMock()
        exec_price.scalar_one_or_none.return_value = 1.0920

        mock_session.execute.side_effect = [exec_state, exec_paper, exec_price]

        ok, reason = await gate._check_daily_drawdown(mock_session, 10000.0)
        assert not ok
        assert "Unrealized drawdown" in reason or "Daily PnL loss" in reason





