import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.stages.per_asset_stage import PerAssetStage
from analysis.stages.fundamental_stage import FundamentalStage
from main import run_startup_checks
from config.settings import load_all_config


@pytest.mark.asyncio
async def test_per_asset_preflight_gate_skips_turn_zero_tokens():
    settings = load_all_config()
    stage = PerAssetStage(settings)
    mock_session = AsyncMock()

    # Force time during rollover window (22:30 UTC)
    rollover_time = datetime(2026, 9, 4, 22, 30, tzinfo=timezone.utc)
    with patch("analysis.stages.per_asset_stage.clock.now", return_value=rollover_time):
        res = await stage.run_one(mock_session, "EURUSD", skip_cooldown=True)

    assert res["success"] is True
    assert res["symbol"] == "EURUSD"
    assert res["decision"] == "wait"
    assert res.get("skipped_by_preflight") is True
    assert "Rollover/Off-peak" in res["rationale"]


@pytest.mark.asyncio
async def test_per_asset_stage_mt5_client_injection():
    settings = load_all_config()
    mock_mt5 = MagicMock()
    stage = PerAssetStage(settings, mt5_client=mock_mt5)
    assert stage.mt5_client is mock_mt5


@pytest.mark.asyncio
@patch("anthropic.AsyncAnthropic")
@patch("database.db.AsyncSessionLocal")
@patch("sqlalchemy.ext.asyncio.AsyncEngine.connect")
async def test_main_startup_checks_with_preflight(mock_connect, mock_session_local, mock_anthropic):
    from database.models import Base
    all_tables = [(table.name,) for table in Base.metadata.sorted_tables]
    all_cols = []
    for table in Base.metadata.sorted_tables:
        for c in table.columns:
            all_cols.append((table.name, c.name))

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=[[(1,)], all_tables, all_cols, [], []])
    mock_connect.return_value.__aenter__.return_value = mock_conn

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    mock_session_local.return_value.__aenter__.return_value = mock_session

    mock_client = AsyncMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create = AsyncMock()

    settings = {
        "paper_trading": {"enabled": True, "tp_detection_method": "close_price"},
        "trading": {"risk": {"intraday_range_strategy_enabled": False}},
    }
    ok = await run_startup_checks(settings)
    assert ok is True


@pytest.mark.asyncio
async def test_fundamental_stage_quantized_thinking():
    settings = load_all_config()
    stage = FundamentalStage(settings)
    assert hasattr(stage, "client")
    if hasattr(stage.client, "thinking_budget"):
        # Budget should belong to one of the 4 quantized buckets: 1024, 4096, 10000, 16000
        assert stage.client.thinking_budget in (1024, 4096, 10000, 16000)
