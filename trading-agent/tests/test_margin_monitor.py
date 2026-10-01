"""
Unit tests for MarginGuardian (MarginMonitor).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from agent.monitors.margin_monitor import run_margin_monitor


@pytest.mark.asyncio
async def test_margin_monitor_emits_warning_under_threshold():
    shutdown_event = asyncio.Event()
    mock_agent = MagicMock()
    mock_agent.shutdown_event = shutdown_event
    mock_agent._recovery_complete = None

    mock_exec_service = MagicMock()
    mock_adapter = AsyncMock()
    mock_adapter.get_account_info.return_value = {
        "balance": 1000.0,
        "equity": 800.0,
        "margin": 500.0,
        "margin_free": 300.0,
        "margin_level": 160.0,  # Under 200% threshold
    }
    mock_exec_service.broker_adapter = mock_adapter
    mock_exec_service.mt5 = None
    mock_agent.execution_service = mock_exec_service

    with patch("agent.monitors.margin_monitor.AgentNotifier") as MockNotifier:
        mock_notifier_instance = AsyncMock()
        MockNotifier.return_value = mock_notifier_instance

        # Run one iteration and stop
        async def _stop_soon():
            await asyncio.sleep(0.05)
            shutdown_event.set()

        asyncio.create_task(_stop_soon())
        await run_margin_monitor(mock_agent, alert_threshold_pct=200.0, poll_interval=0.01)

        assert mock_notifier_instance.send_warning.called
        call_msg = mock_notifier_instance.send_warning.call_args[0][0]
        assert "MARGIN LEVEL ALERT" in call_msg
        assert "160.0%" in call_msg


@pytest.mark.asyncio
async def test_margin_monitor_healthy_no_alert():
    shutdown_event = asyncio.Event()
    mock_agent = MagicMock()
    mock_agent.shutdown_event = shutdown_event
    mock_agent._recovery_complete = None

    mock_exec_service = MagicMock()
    mock_adapter = AsyncMock()
    mock_adapter.get_account_info.return_value = {
        "balance": 1000.0,
        "equity": 1050.0,
        "margin": 100.0,
        "margin_free": 950.0,
        "margin_level": 1050.0,  # Well above 200% threshold
    }
    mock_exec_service.broker_adapter = mock_adapter
    mock_exec_service.mt5 = None
    mock_agent.execution_service = mock_exec_service

    with patch("agent.monitors.margin_monitor.AgentNotifier") as MockNotifier:
        mock_notifier_instance = AsyncMock()
        MockNotifier.return_value = mock_notifier_instance

        async def _stop_soon():
            await asyncio.sleep(0.05)
            shutdown_event.set()

        asyncio.create_task(_stop_soon())
        await run_margin_monitor(mock_agent, alert_threshold_pct=200.0, poll_interval=0.01)

        assert not mock_notifier_instance.send_warning.called
