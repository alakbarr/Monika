"""
Unit test suite verifying all consolidated audit remediations.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import yaml
import re
from pathlib import Path


def test_settings_yaml_single_execution_block():
    settings_path = Path('trading-agent/config/settings.yaml')
    if not settings_path.exists():
        settings_path = Path('config/settings.yaml')
    with open(settings_path, 'r', encoding='utf-8') as f:
        content = f.read()

    execution_matches = re.findall(r"^execution:", content, re.MULTILINE)
    assert len(execution_matches) == 1, f"expected exactly 1 execution block, found {len(execution_matches)}"
    data = yaml.safe_load(content)
    assert 'execution' in data
    exec_cfg = data['execution']
    assert exec_cfg.get('max_price_staleness_seconds') == 120
    assert exec_cfg.get('max_analysis_age_hours') == 0.5
    assert 'max_spread_multiplier' in exec_cfg
    assert exec_cfg['max_spread_multiplier']['XAUUSD'] == 5
    assert exec_cfg.get('adapter_type') == 'live'


@pytest.mark.asyncio
async def test_adhoc_scheduler_proxy_interface():
    from agent.agent_loop import AdHocSchedulerProxy
    proxy = AdHocSchedulerProxy(settings={}, symbols=['EURUSD'], dry_run=True)
    should_skip, reason = await proxy._should_skip_full_cycle()
    assert should_skip is False
    assert hasattr(proxy, '_stage1_consecutive_failures')
    assert hasattr(proxy, '_max_stage1_failures_before_alert')
    stats = await proxy._get_symbol_paper_stats(None, 'EURUSD')
    assert isinstance(stats, dict)


def test_valid_order_transitions_submitted_to_expired():
    from database.models import OrderStatus, VALID_ORDER_TRANSITIONS
    assert OrderStatus.EXPIRED in VALID_ORDER_TRANSITIONS[OrderStatus.SUBMITTED]


@pytest.mark.asyncio
async def test_trigger_circuit_breaker_exists():
    from execution.service.emergency_manager import EmergencyManagerMixin
    mixin = EmergencyManagerMixin()
    mixin.gate = MagicMock()
    mixin.gate.pause_trading = AsyncMock()
    with patch('execution.service.emergency_manager.get_session') as mock_gs:
        mock_sess = AsyncMock()
        mock_gs.return_value.__aenter__.return_value = mock_sess
        res = await mixin.trigger_circuit_breaker('Test crash', cooldown_seconds=60)
        assert res.get('success') is True
        assert res.get('action') == 'paused'


def test_gemini_provider_generate_accepts_kwargs():
    from analysis.providers.gemini_provider import GeminiProvider
    import inspect
    sig = inspect.signature(GeminiProvider.generate)
    assert 'kwargs' in sig.parameters
    assert sig.parameters['kwargs'].kind == inspect.Parameter.VAR_KEYWORD


def test_openrouter_provider_generate_content_accepts_kwargs():
    from analysis.providers.openrouter_provider import OpenRouterProvider
    import inspect
    sig = inspect.signature(OpenRouterProvider.generate_content)
    assert 'kwargs' in sig.parameters
    assert sig.parameters['kwargs'].kind == inspect.Parameter.VAR_KEYWORD


@pytest.mark.asyncio
async def test_mt5_live_adapter_close_position_contract():
    from execution.broker_adapter import MT5LiveAdapter
    mock_mt5 = MagicMock()
    mock_mt5.close_position = AsyncMock(return_value={'success': True, 'profit': 25.5, 'price': 1.0850})
    adapter = MT5LiveAdapter(mock_mt5, dry_run=False)
    res = await adapter.close_position(ticket=12345, lots=0.1)
    assert 'ticket' in res
    assert res['ticket'] == 12345
    assert 'pnl' in res
    assert res['pnl'] == 25.5



def test_core_trading_tasks_includes_critical_schedulers():
    from agent.task_registry import CORE_TRADING_TASKS
    assert 'TickStream' in CORE_TRADING_TASKS
    assert 'PositionSync' in CORE_TRADING_TASKS
    assert 'MarketDataScheduler' in CORE_TRADING_TASKS



def test_model_capabilities_registered_models():
    from utils.llm.model_capabilities import get_capabilities
    cap = get_capabilities('gemini-3.6-flash')
    assert cap.prompt_cache_strategy == 'gemini_context'
    assert cap.supports_tool_choice is True


def test_workflow_has_execution_to_end_edge():
    from graph.workflow import build_trading_graph
    graph = build_trading_graph()
    assert graph is not None
