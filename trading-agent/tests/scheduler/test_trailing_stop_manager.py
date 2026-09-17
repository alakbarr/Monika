import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scheduler.trailing_stop_manager import TrailingStopManager


@pytest.mark.asyncio
async def test_trailing_stop_manager_ignores_budget_pause():
    settings = {
        "trading": {
            "trailing_stop": {
                "enabled": True,
            }
        }
    }
    mock_exec_svc = MagicMock()
    manager = TrailingStopManager(settings, execution_service=mock_exec_svc)

    mock_session = AsyncMock()
    mock_cfg_budget = MagicMock()
    mock_cfg_budget.key = "budget_pause"
    mock_cfg_budget.value = "true"

    def execute_side_effect(stmt):
        mock_res = MagicMock()
        sql_str = str(stmt).lower()
        if "system_config" in sql_str:
            mock_res.scalars.return_value.all.return_value = []
        elif "position" in sql_str:
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    mock_session.execute.side_effect = execute_side_effect

    with patch("scheduler.trailing_stop_manager.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        result = await manager.run_once()

    assert result.get("skipped") is not True
    assert result.get("positions_checked") == 0


@pytest.mark.asyncio
async def test_trailing_stop_manager_paused_on_kill_switch():
    settings = {
        "trading": {
            "trailing_stop": {
                "enabled": True,
            }
        }
    }
    mock_exec_svc = MagicMock()
    manager = TrailingStopManager(settings, execution_service=mock_exec_svc)

    mock_session = AsyncMock()
    mock_cfg_kill = MagicMock()
    mock_cfg_kill.key = "kill_switch"
    mock_cfg_kill.value = "true"

    def execute_side_effect(stmt):
        mock_res = MagicMock()
        sql_str = str(stmt).lower()
        if "system_config" in sql_str:
            mock_res.scalars.return_value.all.return_value = [mock_cfg_kill]
        return mock_res

    mock_session.execute.side_effect = execute_side_effect

    with patch("scheduler.trailing_stop_manager.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        result = await manager.run_once()

    assert result.get("skipped") is True
    assert result.get("reason") == "kill_switch_active"
