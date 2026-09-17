"""
Unit tests for CandidateLesson Shadow Holdout Validation and Adaptive Memory Workflow.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from database.models import CandidateLesson, PaperTradeRecord
from utils.analytics.performance_reviewer import evaluate_candidate_lessons
from analysis.memory.lesson_consolidator import consolidate_lessons_to_playbook, auto_promote_high_confidence_rules


@pytest.mark.asyncio
async def test_consolidate_lessons_creates_shadow_candidate_in_db():
    """Verify that consolidate_lessons_to_playbook proposes shadow CandidateLesson to DB without direct markdown write."""
    mock_session = AsyncMock()
    mock_reflection = MagicMock()
    mock_reflection.status = "resolved"
    mock_reflection.specific_lesson = "Avoid buying XAUUSD during DXY morning expansion"
    mock_reflection.is_paper_whatif = False
    mock_reflection.was_profitable = False
    mock_reflection.process_was_sound = False
    mock_reflection.symbol = "XAUUSD"
    mock_reflection.resolved_at = datetime.now(timezone.utc)
    mock_reflection.next_trade_adjustment = "Wait for H1 close confirmation"

    # Mock 60 reflection rows
    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [mock_reflection] * 60
    mock_session.execute.return_value = mock_exec

    mock_client = AsyncMock()
    mock_client.generate.return_value = "## XAUUSD\n- Do not enter on initial London open spike without FVG mitigation."

    settings = {"llm": {"task_roles": {"trade_reflection": {"primary": "claude-haiku-3.5"}}}}

    with patch("analysis.providers.llm_factory.get_client_for_task", return_value=mock_client):
        res = await consolidate_lessons_to_playbook(mock_session, settings, auto_propose_only=True)
        assert res is not None
        assert "## XAUUSD" in res
        # Verify candidate lesson added to session
        assert mock_session.add.called
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, CandidateLesson)
        assert added_obj.symbol == "XAUUSD"
        assert added_obj.status == "shadow"


@pytest.mark.asyncio
async def test_evaluate_candidate_lessons_promotes_on_positive_delta():
    """Verify that evaluate_candidate_lessons promotes candidate lesson with >=30 trades and positive delta."""
    mock_session = AsyncMock()
    proposed_time = datetime.now(timezone.utc) - timedelta(days=10)

    candidate = CandidateLesson(
        id=1,
        symbol="EURUSD",
        lesson_text="- Prefer buying near H4 OrderBlock",
        status="shadow",
        proposed_at=proposed_time,
        evaluated_trades_count=0
    )

    # 35 post-proposal winning trades (70% win rate)
    post_trades = [
        MagicMock(symbol="EURUSD", status="closed", exit_reason="tp_hit" if i < 24 else "sl_hit", closed_at=proposed_time + timedelta(hours=i), pnl_pct=None)
        for i in range(35)
    ]
    # 30 pre-proposal trades (50% win rate)
    pre_trades = [
        MagicMock(symbol="EURUSD", status="closed", exit_reason="tp_hit" if i < 15 else "sl_hit", closed_at=proposed_time - timedelta(hours=i), pnl_pct=None)
        for i in range(30)
    ]

    mock_exec1 = MagicMock()
    mock_exec1.scalars.return_value.all.return_value = [candidate]

    mock_exec2 = MagicMock()
    mock_exec2.scalars.return_value.all.return_value = post_trades

    mock_exec3 = MagicMock()
    mock_exec3.scalars.return_value.all.return_value = pre_trades

    mock_session.execute.side_effect = [mock_exec1, mock_exec2, mock_exec3]

    with patch("analysis.memory.lesson_consolidator.promote_lesson_to_playbook", new_callable=AsyncMock) as mock_promote:
        summary = await evaluate_candidate_lessons(mock_session)
        assert summary["promoted"] == 1
        assert candidate.status == "promoted"
        assert candidate.promoted_at is not None
        assert mock_promote.called


@pytest.mark.asyncio
async def test_auto_promote_high_confidence_rules():
    """Verify auto_promote_high_confidence_rules promotes high-corroboration or high-delta candidates."""
    mock_session = AsyncMock()
    cand1 = CandidateLesson(
        id=10,
        symbol="XAUUSD",
        lesson_text="- Empirical risk: Entering XAUUSD during NFP spike [Corroborated by 4 trades]",
        status="shadow",
        evaluated_trades_count=2,
        win_rate_delta=0.02
    )
    cand2 = CandidateLesson(
        id=11,
        symbol="EURUSD",
        lesson_text="- Empirical observation: Waiting for H1 FVG mitigation",
        status="shadow",
        evaluated_trades_count=6,
        win_rate_delta=-0.12
    )
    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [cand1, cand2]
    mock_session.execute.return_value = mock_exec

    with patch("analysis.memory.lesson_consolidator.promote_lesson_to_playbook", new_callable=AsyncMock) as mock_promote:
        promoted = await auto_promote_high_confidence_rules(mock_session)
        assert 10 in promoted
        assert cand1.status == "promoted"
        assert cand2.status == "rejected"
        assert cand2.rejection_reason == "negative_delta_-0.12"
        assert mock_promote.called

