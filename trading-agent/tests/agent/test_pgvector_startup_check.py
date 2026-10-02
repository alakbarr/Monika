import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.conftest import create_mock_async_session
from agent.startup_checks import StartupChecker
from database.models import Base


@pytest.mark.asyncio
async def test_startup_check_pgvector_present():
    settings = {"environment": "paper"}
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    # SELECT 1, tables query, columns query, pgvector query
    res_select1 = MagicMock()
    res_tables = MagicMock()
    res_tables.__iter__.return_value = [("news_items",), ("economic_calendar",), ("asset_analysis",),
                                        ("fundamental_briefs",), ("paper_trade_records",), ("trade_outcomes",),
                                        ("positions",), ("risk_state",), ("system_config",),
                                        ("decision_reflections",), ("prescreen_log",), ("candidate_lessons",)]
    all_cols = []
    for t_name, table in Base.metadata.tables.items():
        for col in table.columns.keys():
            all_cols.append((t_name, col))

    res_cols = MagicMock()
    res_cols.__iter__.return_value = all_cols
    res_vector = MagicMock()
    res_vector.scalar.return_value = 1  # pgvector is installed

    mock_conn.execute.side_effect = [res_select1, res_tables, res_cols, res_vector]

    mock_session = create_mock_async_session()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    checker = StartupChecker(settings, db_engine=mock_engine)
    with patch("agent.startup_checks._get_env", return_value="postgresql+asyncpg://user:pass@localhost/db"):
        with patch("database.db.AsyncSessionLocal", mock_session_factory):
            with patch("utils.analytics.cost_tracker.CostTracker.check_and_update_budget_status", new_callable=AsyncMock) as mock_budget, \
                 patch("analysis.memory.chronicle_writer.ChronicleWriter.sync_macro_reality_from_file", new_callable=AsyncMock) as mock_sync:
                mock_budget.return_value = {"mtd_cost": 0.0, "monthly_budget": 100.0, "usage_pct": 0.0, "daily_cost": 0.0, "daily_budget": 20.0, "is_paused": False}
                mock_sync.return_value = 5
                ok, warnings = await checker._check_db_schema()

    assert ok is True
    assert not any("pgvector" in w for w in warnings)


@pytest.mark.asyncio
async def test_startup_check_pgvector_missing_in_live_fails():
    settings = {"environment": "live"}
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    res_select1 = MagicMock()
    res_tables = MagicMock()
    res_tables.__iter__.return_value = [("news_items",), ("economic_calendar",), ("asset_analysis",),
                                        ("fundamental_briefs",), ("paper_trade_records",), ("trade_outcomes",),
                                        ("positions",), ("risk_state",), ("system_config",),
                                        ("decision_reflections",), ("prescreen_log",), ("candidate_lessons",)]
    all_cols = []
    for t_name, table in Base.metadata.tables.items():
        for col in table.columns.keys():
            all_cols.append((t_name, col))

    res_cols = MagicMock()
    res_cols.__iter__.return_value = all_cols
    res_vector = MagicMock()
    res_vector.scalar.return_value = None  # pgvector missing!

    mock_conn.execute.side_effect = [res_select1, res_tables, res_cols, res_vector]

    mock_session = create_mock_async_session()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    checker = StartupChecker(settings, db_engine=mock_engine)
    with patch("agent.startup_checks._get_env", return_value="postgresql+asyncpg://user:pass@localhost/db"):
        with patch("database.db.AsyncSessionLocal", mock_session_factory):
            ok, warnings = await checker._check_db_schema()

    assert ok is False  # Must fail in live environment!
