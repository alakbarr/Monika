"""
Tests for NegativeConstraintGenerator (PR-13).
Verifies automatic synthesis of "DO NOT" constraints from past loss patterns,
reflections, and regime context.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.memory.negative_constraint_generator import NegativeConstraintGenerator
from analysis.memory.failure_taxonomy import FailureCategory


@pytest.mark.asyncio
async def test_generate_from_reflections_with_tags():
    mock_session = AsyncMock()
    
    # Mock reflection with lesson tags
    ref1 = MagicMock()
    ref1.id = 1
    ref1.symbol = "EURUSD"
    ref1.was_profitable = False
    ref1.outcome_pnl_usd = -50.0
    ref1.lesson_tags = '["sl_too_tight", "timing_early"]'
    ref1.next_trade_adjustment = None
    ref1.specific_lesson = None
    ref1.reflection_text = None
    ref1.exit_reason = "sl_hit"

    # Mock execute result
    mock_result_ref = MagicMock()
    mock_result_ref.scalars.return_value.all.return_value = [ref1]
    
    mock_result_trades = MagicMock()
    mock_result_trades.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [mock_result_ref, mock_result_trades]

    constraints = await NegativeConstraintGenerator.generate_negative_constraints_from_losses(
        session=mock_session,
        symbol="EURUSD",
        current_regime="trending",
        max_constraints=2,
    )

    assert len(constraints) == 2
    assert any("SL_TOO_TIGHT" in c for c in constraints)
    assert any("TIMING_EARLY" in c for c in constraints)
    assert all("[DO NOT]" in c for c in constraints)
    assert all("EURUSD" in c for c in constraints)


@pytest.mark.asyncio
async def test_generate_from_paper_trades():
    mock_session = AsyncMock()

    mock_result_ref = MagicMock()
    mock_result_ref.scalars.return_value.all.return_value = []

    trade1 = MagicMock()
    trade1.id = 1
    trade1.symbol = "XAUUSD"
    trade1.status = "closed"
    trade1.pnl_pct = -1.5
    trade1.holding_hours = 0.2
    trade1.exit_reason = "sl_hit"

    mock_result_trades = MagicMock()
    mock_result_trades.scalars.return_value.all.return_value = [trade1]

    mock_session.execute.side_effect = [mock_result_ref, mock_result_trades]

    constraints = await NegativeConstraintGenerator.generate_negative_constraints_from_losses(
        session=mock_session,
        symbol="XAUUSD",
        current_regime=None,
        max_constraints=2,
    )

    assert len(constraints) >= 1
    assert any("SL_TOO_TIGHT" in c for c in constraints)
    assert "[DO NOT]" in constraints[0]


@pytest.mark.asyncio
async def test_generate_fallback_to_regime():
    # When session is None or no history, regime cautionary rules should fill
    constraints = await NegativeConstraintGenerator.generate_negative_constraints_from_losses(
        session=None,
        symbol="BTCUSD",
        current_regime="choppy",
        max_constraints=2,
    )

    assert len(constraints) == 2
    assert any("FALSE_BREAKOUT" in c or "REGIME_MISCLASSIFICATION" in c for c in constraints)
    assert all("[DO NOT]" in c for c in constraints)


def test_format_for_prompt():
    raw_constraints = [
        "- [DO NOT][SL_TOO_TIGHT] For EURUSD: Do not set tight stop",
        "- [DO NOT][TIMING_EARLY] For EURUSD: Wait for confirmation",
    ]
    prompt = NegativeConstraintGenerator.format_for_prompt(raw_constraints)
    assert "NEGATIVE CONSTRAINTS" in prompt
    assert "- [DO NOT][SL_TOO_TIGHT]" in prompt
    assert "- [DO NOT][TIMING_EARLY]" in prompt


def test_format_for_prompt_empty():
    assert NegativeConstraintGenerator.format_for_prompt([]) == ""
