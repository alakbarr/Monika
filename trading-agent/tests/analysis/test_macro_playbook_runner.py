# ==============================================================================
# File: tests/analysis/test_macro_playbook_runner.py
# Monika Macro Playbook Runner Test Suite
# ==============================================================================

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from analysis.research.macro_playbook_runner import (
    MacroPlaybookRunner,
    PlaybookMetadata,
    SymbolVerdict,
    VALID_VERDICT_STATES,
)


def test_parse_playbook_file(tmp_path):
    pb_file = tmp_path / "test_playbook.md"
    pb_file.write_text(
        """---
title: Test Macro Playbook
suggested_schedule: "08:00 UTC Mon-Fri"
timezone: "UTC"
target_symbols: ["EURUSD", "XAUUSD"]
data_capabilities: ["economic_calendar", "prediction_market"]
---

# Test Body
Research details...

## Verdict:
- EURUSD: HOT_BULLISH - Rate cut expectations
- XAUUSD: RISK_OFF - Safe haven bid
""",
        encoding="utf-8",
    )

    runner = MacroPlaybookRunner()
    meta, body = runner.parse_playbook_file(pb_file)

    assert meta.title == "Test Macro Playbook"
    assert meta.suggested_schedule == "08:00 UTC Mon-Fri"
    assert meta.target_symbols == ["EURUSD", "XAUUSD"]
    assert "economic_calendar" in meta.data_capabilities
    assert "Research details..." in body


def test_valid_verdict_states_includes_all_biases():
    """Verify all 6 bias labels used in system are recognized."""
    assert "HOT_BULLISH" in VALID_VERDICT_STATES
    assert "BULLISH" in VALID_VERDICT_STATES
    assert "NEUTRAL" in VALID_VERDICT_STATES
    assert "BEARISH" in VALID_VERDICT_STATES
    assert "HOT_BEARISH" in VALID_VERDICT_STATES
    assert "RISK_OFF" in VALID_VERDICT_STATES


def test_parse_verdicts_from_text():
    text = """
Some analysis notes.

## Verdict:
- EURUSD: HOT_BEARISH - Strong DXY breakout above 104.50
- GBPUSD: NEUTRAL - Range consolidation
- XAUUSD: HOT_BULLISH - Real yields sliding
- BTCUSD: RISK_OFF - Liquidation cascade
- AUDUSD: BULLISH - RBA hawkish hold
- USDJPY: BEARISH - BoJ rate hike speculation
- INVALID: UNKNOWN_STATE - Fallback check
- {SYMBOL}: {BIAS} - Template variable skipped
"""
    runner = MacroPlaybookRunner()
    verdicts = runner.parse_verdicts_from_text(text)

    assert len(verdicts) == 7
    assert verdicts["EURUSD"].state == "HOT_BEARISH"
    assert verdicts["GBPUSD"].state == "NEUTRAL"
    assert verdicts["XAUUSD"].state == "HOT_BULLISH"
    assert verdicts["BTCUSD"].state == "RISK_OFF"
    assert verdicts["AUDUSD"].state == "BULLISH"
    assert verdicts["USDJPY"].state == "BEARISH"
    # Unrecognized state defaults to NEUTRAL
    assert verdicts["INVALID"].state == "NEUTRAL"
    # Template variable {SYMBOL} is skipped
    assert "{SYMBOL}" not in verdicts


@pytest.mark.asyncio
async def test_compute_and_persist_deltas():
    session = AsyncMock()
    # Mock previous state: EURUSD was NEUTRAL
    mock_row = MagicMock()
    mock_row.value = json.dumps({
        "verdicts": {
            "EURUSD": {"state": "NEUTRAL", "reason": "Old range"}
        }
    })
    session.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_row)

    runner = MacroPlaybookRunner(session=session)
    current = {
        "EURUSD": SymbolVerdict("EURUSD", "HOT_BULLISH", "New bullish catalyst"),
        "GBPUSD": SymbolVerdict("GBPUSD", "NEUTRAL", "No prior record"),
    }

    deltas = await runner.compute_and_persist_deltas("test_pb", current)
    assert len(deltas) == 2

    # EURUSD changed from NEUTRAL to HOT_BULLISH
    d_eur = next(d for d in deltas if d.symbol == "EURUSD")
    assert d_eur.changed is True
    assert d_eur.previous_state == "NEUTRAL"
    assert d_eur.current_state == "HOT_BULLISH"

    # GBPUSD had no prior record -> changed is True
    d_gbp = next(d for d in deltas if d.symbol == "GBPUSD")
    assert d_gbp.changed is True
    assert d_gbp.previous_state is None
    assert d_gbp.current_state == "NEUTRAL"


@pytest.mark.asyncio
async def test_fetch_playbook_data_handles_errors():
    """Verify data fetching handles unknown capabilities and exceptions gracefully."""
    runner = MacroPlaybookRunner()
    meta = PlaybookMetadata(
        title="Test",
        data_capabilities=["nonexistent_capability", "economic_calendar"]
    )
    data = await runner._fetch_playbook_data(meta)
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_execute_real_playbook_template():
    pb_path = Path(__file__).resolve().parents[2] / "skills" / "research" / "playbooks" / "premarket_london_brief.md"
    if not pb_path.is_file():
        pb_path = Path("skills/research/playbooks/premarket_london_brief.md")
    assert pb_path.is_file(), "premarket_london_brief.md should exist"

    runner = MacroPlaybookRunner()
    with patch.object(runner, "_fetch_playbook_data", new=AsyncMock(return_value={})), \
         patch.object(runner, "_generate_verdicts_via_llm", new=AsyncMock(return_value="")):
        res = await runner.execute_playbook(pb_path)

    assert res["playbook_file"] == "premarket_london_brief.md"
    assert "EURUSD" in res["target_symbols"]
    assert "GBPUSD" in res["target_symbols"]
    assert "XAUUSD" in res["target_symbols"]
    assert "USDJPY" in res["target_symbols"]
    assert "execution_time" in res
    assert "generation_method" in res
