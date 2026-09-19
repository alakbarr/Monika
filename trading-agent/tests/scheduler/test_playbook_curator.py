import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from scheduler.playbook_curator import PlaybookCurator


@pytest.mark.asyncio
async def test_playbook_curator_insufficient_trades(tmp_path):
    curator = PlaybookCurator(settings={"trading": {"asset_universe": ["EURUSD"]}})
    curator.playbooks_dir = tmp_path / "playbooks"
    curator.crystallized_dir = tmp_path / "crystallized"
    curator.playbooks_dir.mkdir(parents=True, exist_ok=True)
    curator.crystallized_dir.mkdir(parents=True, exist_ok=True)

    mock_session = AsyncMock()
    # 0 trades found
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=res)

    result = await curator.curate_symbol(mock_session, "EURUSD")
    assert result is None


@pytest.mark.asyncio
async def test_playbook_curator_successful_curation(tmp_path):
    curator = PlaybookCurator(settings={"trading": {"asset_universe": ["EURUSD"]}})
    curator.playbooks_dir = tmp_path / "playbooks"
    curator.crystallized_dir = tmp_path / "crystallized"
    curator.playbooks_dir.mkdir(parents=True, exist_ok=True)
    curator.crystallized_dir.mkdir(parents=True, exist_ok=True)

    from analysis.memory.playbook_ledger import PlaybookLedger
    curator.ledger = PlaybookLedger(str(curator.playbooks_dir))

    # Mock 3 closed winning trades
    mock_trade1 = MagicMock(pnl_pct=2.5, symbol="EURUSD")
    mock_trade2 = MagicMock(pnl_pct=1.8, symbol="EURUSD")
    mock_trade3 = MagicMock(pnl_pct=-0.5, symbol="EURUSD")

    # Mock reflection
    mock_reflection = MagicMock()
    mock_reflection.symbol = "EURUSD"
    mock_reflection.was_profitable = True
    mock_reflection.specific_lesson = "Check higher timeframe liquidity sweep before entering"
    mock_reflection.alpha_lesson = None
    mock_reflection.reflection_text = ""

    mock_session = AsyncMock()
    res_trades = MagicMock()
    res_trades.scalars.return_value.all.return_value = [mock_trade1, mock_trade2, mock_trade3]

    res_reflections = MagicMock()
    res_reflections.scalars.return_value.all.return_value = [mock_reflection]

    mock_session.execute = AsyncMock(side_effect=[res_trades, res_reflections])

    result = await curator.curate_symbol(mock_session, "EURUSD")
    assert result is not None
    assert result["symbol"] == "EURUSD"
    assert result["trades_count"] == 3
    assert result["win_rate"] == pytest.approx(2 / 3, rel=1e-2)

    # Verify file was written
    playbook_file = curator.playbooks_dir / "eurusd_playbook.md"
    assert playbook_file.exists()
    content = playbook_file.read_text(encoding="utf-8")
    assert "EURUSD" in content
    assert "Trigger Conditions" in content
    assert "Invalidation" in content

    # Verify linter passed
    lint_check = curator.linter.lint(content)
    assert lint_check.is_valid is True


@pytest.mark.asyncio
async def test_playbook_curator_run_once(tmp_path):
    curator = PlaybookCurator(settings={"trading": {"asset_universe": ["GBPUSD"]}})
    curator.playbooks_dir = tmp_path / "playbooks"
    curator.crystallized_dir = tmp_path / "crystallized"
    curator.playbooks_dir.mkdir(parents=True, exist_ok=True)
    curator.crystallized_dir.mkdir(parents=True, exist_ok=True)

    mock_session = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=res)

    results = await curator.run_once(session=mock_session)
    assert isinstance(results, dict)
