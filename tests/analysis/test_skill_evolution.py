import pytest
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import create_mock_async_session
from monika.application.analysis.memory.skill_evolution import MicroPlaybookCompiler, PLAYBOOKS_DIR


@pytest.mark.asyncio
async def test_micro_playbook_compiler_compiles_streak(tmp_path):
    mock_session = create_mock_async_session()

    # Create 4 mock reflections with positive pnl (streak of 4 wins)
    reflections = []
    for i in range(4):
        r = MagicMock()
        r.symbol = "EURUSD"
        r.status = "resolved"
        r.pnl = 150.0 + i
        r.market_regime = "BALANCED"
        r.specific_lesson = f"SMC liquidity sweep at London open verified #{i}"
        r.next_trade_adjustment = "Wait for 15m displacement"
        reflections.append(r)

    mock_execute = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = reflections
    mock_execute.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_execute

    from unittest.mock import patch

    with patch("monika.application.analysis.memory.skill_evolution.PLAYBOOKS_DIR", tmp_path):
        compiled = await MicroPlaybookCompiler.evaluate_and_compile(
            session=mock_session,
            settings={"trading": {"asset_universe": ["EURUSD"]}},
            min_consecutive_wins=3,
            min_sample_size=3,
        )
        assert len(compiled) == 1
        assert compiled[0]["symbol"] == "EURUSD"
        assert compiled[0]["regime"] == "BALANCED"
        assert compiled[0]["streak"] == 4

        # Verify file was written to tmp_path
        playbook_file = tmp_path / "eurusd_balanced_playbook.md"
        assert playbook_file.exists()
        content = playbook_file.read_text(encoding="utf-8")
        assert "Micro-Playbook: EURUSD in BALANCED Regime" in content
        assert "SMC liquidity sweep at London open" in content
