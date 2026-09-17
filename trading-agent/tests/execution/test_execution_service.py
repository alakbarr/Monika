import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from execution.execution_service import ExecutionService, ExecutionResult
from database.models import AssetAnalysis, Position

class TestExecutionResult:
    def test_summary_blocked(self):
        res = ExecutionResult("XAUUSD", 1, "buy", None, False, [], ["check_1"], ["Too risky"], False, None, None, None, None, None, datetime.now(timezone.utc), 1.0)
        assert "BLOCKED [XAUUSD] BUY" in res.summary()
        assert "Too risky" in res.summary()

    def test_summary_executed(self):
        res = ExecutionResult("XAUUSD", 1, "buy", None, True, [], [], [], True, 100, 2000.0, 1.0, None, 1, datetime.now(timezone.utc), 1.0)
        assert "EXECUTED [XAUUSD] BUY" in res.summary()
        assert "100" in res.summary()

    def test_summary_failed(self):
        res = ExecutionResult("XAUUSD", 1, "buy", None, True, [], [], [], False, None, None, None, "MT5 down", None, datetime.now(timezone.utc), 1.0)
        assert "FAILED [XAUUSD] BUY" in res.summary()
        assert "MT5 down" in res.summary()

class TestExecutionService:

    @pytest.fixture
    def svc(self):
        return ExecutionService({}, mt5_client=AsyncMock(), dry_run=False)

    @pytest.mark.asyncio
    @patch('execution.execution_service.PositionSizer')
    @patch('execution.execution_service.RiskGate')
    async def test_execute_analysis_skip_wait(self, mock_risk_cls, mock_sizer_cls, svc):
        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        analysis = AssetAnalysis(id=1, symbol="XAUUSD", decision="wait", stop_loss=10, take_profit=20)
        
        res = await svc.execute_analysis(session, analysis)
        assert res.risk_approved is False
        assert "not_tradeable" in res.risk_checks_failed
        assert res.executed is False

    @pytest.mark.asyncio
    async def test_execute_analysis_success(self):
        from execution.execution_service import _EXECUTED_ANALYSIS_IDS
        _EXECUTED_ANALYSIS_IDS.clear()
        
        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info.return_value = {"equity": 10000}
        mock_mt5.get_current_price.return_value = {"ask": 2000.0, "bid": 1999.0}
        mock_mt5.place_order.return_value = {"success": True, "ticket": 12345, "price": 2000.0, "error": None}
    
        settings = {"trading": {"min_paper_trades_before_live": 0, "risk": {"confluence_verifier_enabled": False, "min_verifiable_confluence": 0}}}
        svc = ExecutionService(settings, mt5_client=mock_mt5)
    
        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(return_value=MagicMock(recommended_lots=0.1, entry_price=2000.0))
        svc.sizer = mock_sizer
    
        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate
    
        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
    
        analysis = AssetAnalysis(id=999, symbol="XAUUSD", decision="buy", stop_loss=1980, take_profit=2020, invalidation_price=1980, invalidation_direction="below", rationale="Test rationale")
        
        with patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv:
            mock_adv.return_value = {'approve': True, 'hard_block': False}
            res = await svc.execute_analysis(session, analysis)
    
        assert res.risk_approved is True
        assert res.executed is True
        assert res.mt5_ticket == 12345
        assert res.executed_price == 2000.0
        mock_mt5.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_limit_order_execution_and_drift_validation(self):
        from execution.execution_service import _EXECUTED_ANALYSIS_IDS
        _EXECUTED_ANALYSIS_IDS.clear()

        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info.return_value = {"equity": 10000}
        # Current price: 2000.0
        mock_mt5.get_current_price.return_value = {"ask": 2000.0, "bid": 1999.0}
        mock_mt5.place_order.return_value = {"success": True, "ticket": 67890, "price": 1980.0, "error": None}

        settings = {"trading": {"min_paper_trades_before_live": 0, "risk": {"confluence_verifier_enabled": False, "min_verifiable_confluence": 0}}}
        svc = ExecutionService(settings, mt5_client=mock_mt5)

        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(return_value=MagicMock(recommended_lots=0.1, entry_price=1980.0))
        svc.sizer = mock_sizer

        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate

        session = AsyncMock()
        session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.first.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        # Case 1: Limit order with specified_price (1980.0) 1% away from current market (2000.0).
        # price_at_analysis is 2000.0 (drift is 0%).
        # Old bug would reject because (2000 - 1980)/2000 = 1.0% > 0.5% * 2.
        # Fixed logic checks drift against price_at_analysis (0% <= 1.0%), so it succeeds.
        analysis = AssetAnalysis(
            id=1001, symbol="XAUUSD", decision="buy",
            stop_loss=1970, take_profit=2020,
            invalidation_price=1970, invalidation_direction="below",
            price_at_analysis=2000.0,
            entry_zone='{"price": 1980.0, "order_type": "limit"}',
            rationale="Limit order pullback entry"
        )

        with patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv:
            mock_adv.return_value = {'approve': True, 'hard_block': False}
            res = await svc.execute_analysis(session, analysis)

        assert res.risk_approved is True
        assert res.executed is True
        assert res.mt5_ticket == 67890

        # Case 2: Market has drifted 3% since analysis was made (price_at_analysis=1940.0 vs current=2000.0).
        # Drift = abs(2000 - 1940) / 1940 * 100 = 3.09% > 1.0% threshold.
        # Should be rejected with stale_entry_price.
        analysis_stale = AssetAnalysis(
            id=1002, symbol="XAUUSD", decision="buy",
            stop_loss=1970, take_profit=2020,
            invalidation_price=1970, invalidation_direction="below",
            price_at_analysis=1940.0,
            entry_zone='{"price": 1980.0, "order_type": "limit"}',
            rationale="Stale analysis"
        )
        res_stale = await svc.execute_analysis(session, analysis_stale)
        assert res_stale.risk_approved is False
        assert "stale_entry_price" in res_stale.risk_checks_failed

        # Case 3: Missing price_at_analysis (None) falls back to current_price without crashing or ZeroDivisionError
        analysis_fallback = AssetAnalysis(
            id=1003, symbol="XAUUSD", decision="buy",
            stop_loss=1970, take_profit=2020,
            invalidation_price=1970, invalidation_direction="below",
            price_at_analysis=None,
            entry_zone='{"price": 1980.0, "order_type": "limit"}',
            rationale="Fallback analysis"
        )
        res_fallback = await svc.execute_analysis(session, analysis_fallback)
        assert res_fallback.risk_approved is True
        assert res_fallback.executed is True



    @pytest.mark.asyncio
    async def test_close_position_by_ticket(self):
        mock_mt5 = AsyncMock()
        mock_mt5.close_position.return_value = {"success": True, "profit": 50.0}
        svc = ExecutionService({}, mt5_client=mock_mt5)
        svc.gate = AsyncMock()
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_pos = Position(mt5_ticket=123, entry_price=2000, volume=0.1)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pos
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        with patch('execution.execution_service.get_session') as mock_get_session:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_session
            mock_get_session.return_value = mock_ctx
            
            res = await svc.close_position_by_ticket(123)
            
            assert res["success"] is True
            assert mock_pos.status == "closed"
            assert mock_pos.pnl == 50.0

    @pytest.mark.asyncio
    async def test_kill_switch(self):
        mock_mt5 = AsyncMock()
        mock_mt5.close_all_positions.return_value = {"closed": 5, "failed": 0, "total": 5}
        mock_mt5.sync_positions_from_mt5 = AsyncMock()
        svc = ExecutionService({}, mt5_client=mock_mt5)
        svc.gate = AsyncMock()
        
        with patch('execution.execution_service.get_session') as mock_get_session:
            mock_ctx = AsyncMock()
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result
            mock_ctx.__aenter__.return_value = mock_session
            mock_get_session.return_value = mock_ctx
            
            res = await svc.kill_switch()
            
            assert res["closed"] == 5
            mock_mt5.close_all_positions.assert_awaited_once()
            svc.gate.pause_trading.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execution_service_paper_trading_flag(self):
        settings = {"trading": {"auto_execute": True}}
        mt5_client = AsyncMock()
        svc = ExecutionService(settings, mt5_client=mt5_client, dry_run=True)
        assert svc.dry_run is True

    @pytest.mark.asyncio
    async def test_execution_service_live_trading_flag(self):
        settings = {"trading": {"auto_execute": True}}
        mt5_client = AsyncMock()
        svc = ExecutionService(settings, mt5_client=mt5_client, dry_run=False)
        assert svc.dry_run is False

    @pytest.mark.asyncio
    async def test_count_open_positions(self):
        svc = ExecutionService({}, mt5_client=AsyncMock())
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 3
        mock_session.execute.return_value = mock_result
        count = await svc._count_open_positions(mock_session)
        assert count == 3
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_news_blackout_circuit_breaker_triggered_for_matching_currency(self):
        from database.models import EconomicCalendar
        svc = ExecutionService({"trading": {"risk": {"news_window_minutes": 30}}}, mt5_client=AsyncMock(), dry_run=True)
        session = AsyncMock()
        session.add = MagicMock()
        
        # Mock MT5 & DB checks before news blackout
        mock_dup = MagicMock()
        mock_dup.scalar_one_or_none.return_value = None
        
        # Mock high impact USD news in blackout window
        high_news = EconomicCalendar(event_name="Initial Jobless Claims", currency="USD", impact="high", event_time=datetime.now(timezone.utc))
        mock_news_res = MagicMock()
        mock_news_res.scalars.return_value.all.return_value = [high_news]
        
        session.execute.side_effect = [mock_dup, mock_news_res]
        
        analysis = AssetAnalysis(id=888, symbol="GBPUSD", decision="buy", stop_loss=1.25, take_profit=1.27)
        res = await svc.execute_analysis(session, analysis)
        
        assert res.risk_approved is False
        assert res.executed is False
        assert "news_blackout" in res.risk_checks_failed
        assert "Initial Jobless Claims" in res.risk_rejection_reasons[0]

    @pytest.mark.asyncio
    async def test_news_blackout_circuit_breaker_ignored_for_unrelated_currency(self):
        from execution.execution_service import _EXECUTED_ANALYSIS_IDS
        _EXECUTED_ANALYSIS_IDS.clear()
        
        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info.return_value = {"equity": 10000}
        mock_mt5.get_current_price.return_value = {"ask": 1.2600, "bid": 1.2598}
        mock_mt5.place_order.return_value = {"success": True, "ticket": 55555, "price": 1.2600, "error": None}
        
        svc = ExecutionService({"trading": {"risk": {"news_window_minutes": 30, "min_verifiable_confluence": 0}}}, mt5_client=mock_mt5, dry_run=True)
        
        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(return_value=MagicMock(recommended_lots=0.1, entry_price=1.2600))
        svc.sizer = mock_sizer
        
        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate
        
        session = AsyncMock()
        session.add = MagicMock()
        
        def mock_execute(*args, **kwargs):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            return m
        session.execute = AsyncMock(side_effect=mock_execute)
        
        analysis = AssetAnalysis(id=777, symbol="GBPUSD", decision="buy", stop_loss=1.25, take_profit=1.27)
        with patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv:
            mock_adv.return_value = {'approve': True, 'hard_block': False}
            res = await svc.execute_analysis(session, analysis)
        
        assert res.risk_approved is True
        assert res.executed is True
        assert "news_blackout" not in res.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execute_analysis_with_6h_old_brief_accepted(self):
        from database.models import AssetAnalysis, FundamentalBrief
        from datetime import datetime, timezone, timedelta
        import time
        from execution.execution_service import _EXECUTED_ANALYSIS_IDS
        _EXECUTED_ANALYSIS_IDS.clear()
        
        settings = {"paper_trading": {"enabled": True}}
        svc = ExecutionService(settings=settings)
        svc.dry_run = True
        
        mock_mt5 = AsyncMock()
        mock_mt5.get_account_info = AsyncMock(return_value={"equity": 10000})
        mock_mt5.get_current_price = AsyncMock(return_value={"ask": 1.2605, "bid": 1.2600, "fetched_at": time.time()})
        mock_mt5.get_symbol_info = AsyncMock(return_value={"ask": 1.2605, "bid": 1.2600, "spread": 0.0005})
        mock_mt5.open_order = AsyncMock(return_value=12345)
        svc.mt5 = mock_mt5
        
        mock_sizer = MagicMock()
        mock_sizer.calculate_with_session = AsyncMock(return_value=MagicMock(recommended_lots=0.1, entry_price=1.2600))
        svc.sizer = mock_sizer
        
        mock_gate = AsyncMock()
        mock_gate.check.return_value = MagicMock(approved=True, checks_passed=[], checks_failed=[], rejection_reasons=[])
        svc.gate = mock_gate
        
        session = AsyncMock()
        session.add = MagicMock()
        def mock_execute(*args, **kwargs):
            m = MagicMock()
            m.scalar_one_or_none.return_value = None
            m.scalars.return_value.all.return_value = []
            return m
        session.execute = AsyncMock(side_effect=mock_execute)
        
        # 6 hours old brief (less than 12h threshold)
        brief_gen_at = datetime.now(timezone.utc) - timedelta(hours=6)
        mock_brief = FundamentalBrief(id=10, generated_at=brief_gen_at, structured_json="{}")
        
        brief_ctx = AsyncMock()
        brief_ctx.__aenter__.return_value.get = AsyncMock(return_value=mock_brief)
        
        analysis = AssetAnalysis(id=888, symbol="GBPUSD", decision="buy", brief_id=10, stop_loss=1.25, take_profit=1.27, confluence_score=6, confidence=0.8)
        with patch('execution.execution_service.get_session', return_value=brief_ctx), \
             patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv, \
             patch('analysis.validators.confluence_verifier.verify_confluence', new_callable=AsyncMock) as mock_conf:
            mock_adv.return_value = {'approve': True, 'hard_block': False}
            mock_conf.return_value = {'verified': True, 'blocking_issues': []}
            res = await svc.execute_analysis(session, analysis)
        
        assert res.risk_approved is True
        assert res.executed is True
        assert "stale_fundamental_brief" not in res.risk_checks_failed

    @pytest.mark.asyncio
    async def test_execute_analysis_with_13h_old_brief_rejected(self):
        from database.models import AssetAnalysis, FundamentalBrief
        from datetime import datetime, timezone, timedelta
        
        settings = {"paper_trading": {"enabled": True}}
        svc = ExecutionService(settings=settings)
        svc.dry_run = True
        
        mock_mt5 = AsyncMock()
        mock_mt5.get_symbol_info = AsyncMock(return_value={"ask": 1.2605, "bid": 1.2600, "spread": 0.0005})
        svc.mt5 = mock_mt5
        
        session = AsyncMock()
        session.add = MagicMock()
        
        # 13 hours old brief (exceeds 12h threshold)
        brief_gen_at = datetime.now(timezone.utc) - timedelta(hours=13)
        mock_brief = FundamentalBrief(id=11, generated_at=brief_gen_at, structured_json="{}")
        
        brief_ctx = AsyncMock()
        brief_ctx.__aenter__.return_value.get = AsyncMock(return_value=mock_brief)
        
        analysis = AssetAnalysis(id=889, symbol="GBPUSD", decision="buy", brief_id=11, stop_loss=1.25, take_profit=1.27)
        with patch('execution.execution_service.get_session', return_value=brief_ctx):
            res = await svc.execute_analysis(session, analysis)
        
        assert res.risk_approved is False
        assert res.executed is False
        assert "stale_fundamental_brief" in res.risk_checks_failed

