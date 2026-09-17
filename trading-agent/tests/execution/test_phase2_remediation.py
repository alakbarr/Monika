
import asyncio
import inspect
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def test_group_a_inspect_iscoroutinefunction():
    async def sample_coro():
        pass
    def sample_func():
        pass
    assert inspect.iscoroutinefunction(sample_coro)
    assert not inspect.iscoroutinefunction(sample_func)

def test_cw4_task_registry_core_tasks():
    from agent.task_registry import CORE_TRADING_TASKS
    required_tasks = {
        'MT5HealthMonitor', 'OrderReconciler', 'FridayCloseGuardian',
        'CycleScheduler', 'PositionGuardian', 'TrailingStop', 'Heartbeat'
    }
    for task in required_tasks:
        assert task in CORE_TRADING_TASKS, f'{task} missing from CORE_TRADING_TASKS'

@pytest.mark.asyncio
async def test_cw1_adhoc_scheduler_proxy_data_node():
    from agent.agent_loop import AdHocSchedulerProxy
    from graph.nodes.data_node import fetch_data_node
    proxy = AdHocSchedulerProxy({'trading': {'symbols': ['XAUUSD']}}, ['XAUUSD'])
    assert proxy.asset_universe == ['XAUUSD']
    assert await proxy._refresh_data_sources() == {'status': 'ad_hoc_refresh_skipped'}
    assert proxy.mt5_timeframes == ['M15', 'H1', 'H4', 'D1']
    assert proxy.settings['trading']['symbols'] == ['XAUUSD']

    # When scheduler is None and is_ad_hoc is False, node immediately pauses
    state = {'summary': {}, 'symbols': ['XAUUSD'], 'actionable_trades': []}
    res_no_adhoc = await fetch_data_node(state, config={'configurable': {'is_ad_hoc': False, 'scheduler': None}})
    assert res_no_adhoc.get('should_pause') is True

    # When is_ad_hoc is True, fallback AdHocSchedulerProxy is created and executed
    with patch('graph.nodes.data_node.get_session') as mock_gs, \
         patch('utils.validation.data_validator.validate_data_freshness', new_callable=AsyncMock) as mock_vdf:
        mock_vdf.return_value = {"ready": True, "stale_assets": [], "warnings": [], "errors": []}
        mock_sess = AsyncMock()
        mock_gs.return_value.__aenter__.return_value = mock_sess
        with patch('analysis.calculators.economic_surprise.compute_surprise_scores', new_callable=AsyncMock) as mock_css:
            mock_css.return_value = 0
            res = await fetch_data_node(
                {'summary': {'is_ad_hoc': True}, 'symbols': ['XAUUSD'], 'actionable_trades': []},
                config={'configurable': {'is_ad_hoc': True, 'scheduler': None}}
            )
            assert res.get('should_pause') is not True
            assert 'summary' in res
            assert res['summary']['data_refresh'] == {'status': 'ad_hoc_refresh_skipped'}

def test_sc5_trigger_checker_properties():
    from scheduler.trigger_checker import TriggerChecker
    settings = {'trading': {'symbols': ['EURUSD', 'GBPUSD'], 'risk': {'max_concurrent_positions': 5}}}
    checker = TriggerChecker(settings)
    assert checker.asset_universe == ['EURUSD', 'GBPUSD']
    assert checker.dry_run is False
    assert checker._mt5 is None

@pytest.mark.asyncio
async def test_ex7_ex8_simulated_broker_adapter_parity_and_pending_sltp():
    from execution.broker_adapter import SimulatedBrokerAdapter
    from database.models import Order
    adapter = SimulatedBrokerAdapter(initial_balance=10000.0)
    adapter.set_tick('EURUSD', bid=1.08000, ask=1.08010)

    # 1. Market order parity check
    order = Order(
        id=991, symbol='EURUSD', direction='buy', order_type='MARKET',
        requested_volume=0.1, requested_price=1.08010, client_order_id='TEST_MKT_1'
    )
    res = await adapter.submit_order(order, sl=1.07500, tp=1.09000)
    assert res['success']
    ticket = res['ticket']
    pos = adapter.positions[ticket]
    assert 'price_open' in pos
    assert 'open_price' in pos
    assert 'id' in pos
    assert pos['sl'] == 1.07500
    assert pos['tp'] == 1.09000

    # 2. Pending order auto-filled on set_tick
    pending_order = Order(
        id=992, symbol='EURUSD', direction='buy', order_type='LIMIT',
        requested_volume=0.1, requested_price=1.07900, client_order_id='TEST_PENDING_1'
    )
    res_pending = await adapter.submit_order(pending_order, sl=1.07400, tp=1.08900)
    assert res_pending['status'] == 'pending'
    pending_ticket = res_pending['ticket']

    adapter.set_tick('EURUSD', bid=1.07890, ask=1.07900)
    assert pending_ticket in adapter.positions
    filled_pos = adapter.positions[pending_ticket]
    assert filled_pos['sl'] == 1.07400
    assert filled_pos['tp'] == 1.08900
    assert 'price_open' in filled_pos

    # 3. Pending order filled via check_pending_orders call
    pending_order2 = Order(
        id=993, symbol='EURUSD', direction='buy', order_type='LIMIT',
        requested_volume=0.1, requested_price=1.07800, client_order_id='TEST_PENDING_2'
    )
    res_pending2 = await adapter.submit_order(pending_order2, sl=1.07300, tp=1.08800)
    assert res_pending2['status'] == 'pending'
    # Direct price update without triggering set_tick
    adapter.current_prices['EURUSD'] = {'symbol': 'EURUSD', 'bid': 1.07790, 'ask': 1.07800, 'last': 1.07800, 'spread': 0.0001}
    fills = adapter.check_pending_orders('EURUSD')
    assert len(fills) == 1
    assert fills[0]['ticket'] == res_pending2['ticket']
    filled_pos2 = adapter.positions[res_pending2['ticket']]
    assert filled_pos2['sl'] == 1.07300
    assert filled_pos2['tp'] == 1.08800

@pytest.mark.asyncio
async def test_ex9_order_emulator_sell_breakeven_guard():
    from execution.order_emulator import ClientOrderEmulator
    emulator = ClientOrderEmulator()
    pos = await emulator.register_position(
        ticket=12345, symbol='EURUSD', direction='sell',
        entry_price=1.08500, current_sl=0.0, atr=0.0010
    )
    assert pos.breakeven_activated is False

    pos2 = await emulator.register_position(
        ticket=12346, symbol='EURUSD', direction='sell',
        entry_price=1.08500, current_sl=1.08400, atr=0.0010
    )
    assert pos2.breakeven_activated is True

@pytest.mark.asyncio
async def test_db10_risk_gate_flush_not_commit():
    from risk.risk_gate import RiskGate
    from risk.position_sizing import SizingResult
    from risk.risk_gate import RiskVerdict
    gate = RiskGate({})
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    sizing = SizingResult(
        symbol='EURUSD',
        direction='buy',
        entry_price=1.0820,
        stop_loss=1.0800,
        take_profit=1.0900,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0020,
        sl_distance_pips=20.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True
    )
    verdict = RiskVerdict(approved=True, symbol='EURUSD', proposed_lots=0.1,
                          checks_passed=['test'], checks_failed=[], rejection_reasons=[])

    await gate._log_verdict(mock_session, 'EURUSD', 'buy', sizing, verdict)
    assert mock_session.flush.called
    assert not mock_session.commit.called

@pytest.mark.asyncio
async def test_db9_portfolio_correlation_gate_negative_correlation():
    from risk.portfolio_correlation_gate import filter_correlated_proposals
    mock_session = AsyncMock()
    with patch('risk.portfolio_correlation_gate.get_rolling_correlation', new_callable=AsyncMock) as mock_corr:
        mock_corr.return_value = (-0.85, 'dynamic_rolling')
        actionable = [
            ('EURUSD', {'decision': 'buy', 'confidence': 0.8, 'analysis_id': 1}),
            ('USDCHF', {'decision': 'sell', 'confidence': 0.8, 'analysis_id': 2}),
        ]
        kept, rejected = await filter_correlated_proposals(mock_session, actionable, threshold=0.65)
        assert len(kept) == 1
        assert len(rejected) == 1
        assert rejected[0][0] == 'USDCHF'
        assert 'effective_corr=0.85' in rejected[0][2]

@pytest.mark.asyncio
async def test_an3_adversarial_check_prompt_initialization():
    from analysis.validators.adversarial_check import run_adversarial_check
    mock_session = AsyncMock()
    analysis = MagicMock()
    analysis.symbol = 'XAUUSD'
    analysis.decision = 'buy'
    analysis.stop_loss = 2300.0
    analysis.take_profit = 2400.0
    analysis.price_at_analysis = 2320.0
    analysis.confluence_score = 8
    analysis.priced_in_score = 3
    analysis.invalidation_price = 2290.0
    analysis.invalidation_direction = 'below'
    analysis.rationale = 'Gold setup'
    analysis.entry_zone = 'market'
    analysis.invalidation = 'below 2290'
    analysis.id = 101

    with patch('analysis.validators.adversarial_check.get_client_for_task', side_effect=RuntimeError('LLM down')):
        res = await run_adversarial_check(mock_session, analysis, {})
        assert res['approve'] is True
        assert 'Adversarial check unavailable' in res['strongest_counter_argument']

def test_an8_fundamental_brief_schema_harmonization():
    from analysis.schemas.pydantic_schemas import FundamentalBriefSchema
    payload = {
        'macro_narrative': 'US economy expanding moderately.',
        'currency_bias': {'USD': 'bullish', 'EUR': 'bearish'},
        'risk_sentiment': 'risk-on',
        'confidence': 0.8,
        'key_data_points_used': {'DXY': '104.2', 'CPI': '3.1%'},
    }
    brief = FundamentalBriefSchema.model_validate(payload)
    assert brief.macro_bias == 'risk-on'
    assert brief.macro_narrative == 'US economy expanding moderately.'
    assert len(brief.key_drivers) == 2

def test_lu3_credential_pool_groq_multikey():
    from utils.api.credential_pool import CredentialPool
    with patch.dict(os.environ, {'GROQ_API_KEYS': 'gsk_1, gsk_2, gsk_3'}):
        pool = CredentialPool()
        groq_keys = [k.key for k in pool._pools.get('groq', [])]
        assert len(groq_keys) == 3
        assert 'gsk_1' in groq_keys
        assert 'gsk_2' in groq_keys
        assert 'gsk_3' in groq_keys
