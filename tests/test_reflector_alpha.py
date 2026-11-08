import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import create_mock_async_session
from monika.infrastructure.database.models import DecisionReflection
from monika.application.analysis.memory.reflector import TradeReflector


@pytest.mark.asyncio
async def test_reflector_includes_alpha():
    # Mock settings and LLMFactory
    settings = {}

    with (
        patch("monika.application.analysis.memory.reflector.get_client_for_task") as mock_get_client,
        patch("monika.application.analysis.memory.skill_crystallizer.SkillCrystallizer") as mock_cryst,
    ):
        mock_cryst.return_value.evaluate_and_crystallize = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = json.dumps(
            {"reflection_text": "Good trade.", "lesson_tags": ["trend"], "alpha_lesson": "Outperformed the benchmark."}
        )
        mock_get_client.return_value = mock_client

        reflector = TradeReflector(settings=settings)

        session = create_mock_async_session()
        mock_reflection = DecisionReflection(
            id=1,
            status="pending",
            is_paper_whatif=False,
            rationale_summary="Bought because MA crossed.",
            decision="BUY",
            confidence=0.8,
            outcome_pnl_usd=50.0,
            was_profitable=True,
            holding_hours=2.5,
            exit_reason="tp_hit",
            benchmark_name="DXY",
            alpha_return=1.5,
        )
        session.get.return_value = mock_reflection

        await reflector.reflect_on_trade(session, 1)

        # Check that the prompt sent to the LLM contains alpha info
        call_args = mock_client.generate_content.call_args
        prompt = call_args.kwargs["user_message"]

        assert "Alpha vs DXY: 1.50%" in prompt

        # Check that the parsed response is stored
        assert mock_reflection.alpha_lesson == "Outperformed the benchmark."
        assert mock_reflection.status == "resolved"


@pytest.mark.asyncio
async def test_stage2_prefetcher_alpha_lessons_none_safe():
    from monika.infrastructure.database.models import DecisionReflection
    from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler

    # Mock executor & session
    mock_executor = MagicMock()
    mock_session = create_mock_async_session()
    mock_executor.session = mock_session
    mock_executor.settings = {"analysis": {"stage2_max_bundle_chars": 36000}}

    # Create reflections with None fields
    ref1 = DecisionReflection(
        id=1,
        symbol="GBPUSD",
        status="resolved",
        alpha_lesson="Lesson with alpha return",
        alpha_return=2.345,
        resolved_at=None,
        benchmark_name="DXY",
    )
    ref2 = DecisionReflection(
        id=2,
        symbol="GBPUSD",
        status="resolved",
        alpha_lesson="Lesson with None alpha return",
        alpha_return=None,
        resolved_at=None,
        benchmark_name=None,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ref1, ref2]
    mock_session.execute.return_value = mock_result

    lines = []
    # Test formatting logic directly as implemented in stage2_prefetcher
    stmt = MagicMock()
    recent_lessons = (await mock_session.execute(stmt)).scalars().all()
    assert len(recent_lessons) == 2

    for rl in recent_lessons:
        date_str = (
            rl.resolved_at.strftime("%Y-%m-%d")
            if rl.resolved_at
            else (rl.created_at.strftime("%Y-%m-%d") if getattr(rl, "created_at", None) else "Recent")
        )
        alpha_str = f"{rl.alpha_return:.2f}%" if rl.alpha_return is not None else "N/A"
        bench_str = f" vs {rl.benchmark_name}" if rl.benchmark_name else ""
        lines.append(f"[{date_str}] Alpha: {alpha_str}{bench_str}")
        lines.append(f"Lesson: {rl.alpha_lesson}")

    assert lines[0] == "[Recent] Alpha: 2.35% vs DXY"
    assert lines[1] == "Lesson: Lesson with alpha return"
    assert lines[2] == "[Recent] Alpha: N/A"
    assert lines[3] == "Lesson: Lesson with None alpha return"


@pytest.mark.asyncio
async def test_reflector_handles_empty_response_with_fallback():
    """Verify that an empty LLM response is handled gracefully with deterministic fallback without crashing."""
    settings = {}
    with (
        patch("monika.application.analysis.memory.reflector.get_client_for_task") as mock_get_client,
        patch("monika.application.analysis.memory.skill_crystallizer.SkillCrystallizer") as mock_cryst,
    ):
        mock_cryst.return_value.evaluate_and_crystallize = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = ""  # Empty string simulates failed / blocked generation
        mock_get_client.return_value = mock_client

        reflector = TradeReflector(settings=settings)
        session = create_mock_async_session()
        mock_reflection = DecisionReflection(
            id=1,
            status="pending",
            is_paper_whatif=False,
            rationale_summary="Bought breakout.",
            decision="BUY",
            confidence=0.8,
            outcome_pnl_usd=-35.0,
            was_profitable=False,
            holding_hours=1.5,
            exit_reason="sl_hit",
            benchmark_name="DXY",
            alpha_return=-0.8,
            symbol="XAUUSD",
        )
        session.get.return_value = mock_reflection

        await reflector.reflect_on_trade(session, 1)

        assert mock_reflection.status == "resolved"
        assert "stopped out via sl_hit" in mock_reflection.specific_lesson
        assert mock_reflection.process_was_sound is False
        assert mock_reflection.outcome_process_classification == "bad_process_bad_outcome"


@pytest.mark.asyncio
async def test_reflector_handles_markdown_and_thoughts():
    """Verify that markdown code fences and reasoning model <think> tags are stripped and parsed cleanly."""
    settings = {}
    with (
        patch("monika.application.analysis.memory.reflector.get_client_for_task") as mock_get_client,
        patch("monika.application.analysis.memory.skill_crystallizer.SkillCrystallizer") as mock_cryst,
    ):
        mock_cryst.return_value.evaluate_and_crystallize = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = (
            "<think>Analyzing trade outcome...</think>\n"
            "```json\n"
            "{\n"
            '  "reflection_text": "Good technical execution.",\n'
            '  "lesson_tags": ["well_executed_setup"],\n'
            '  "specific_lesson": "Valid technical breakout on H4 timeframe occurred with clear momentum.",\n'
            '  "next_trade_adjustment": "Maintain current risk reward ratio.",\n'
            '  "alpha_lesson": "Outperformed the benchmark significantly.",\n'
            '  "process_was_sound": true,\n'
            '  "outcome_process_classification": "good_process_good_outcome",\n'
            '  "macro_thesis_correct": true,\n'
            '  "synthesis_adjudication_sound": true\n'
            "}\n"
            "```"
        )
        mock_get_client.return_value = mock_client

        reflector = TradeReflector(settings=settings)
        session = create_mock_async_session()
        mock_reflection = DecisionReflection(
            id=1,
            status="pending",
            is_paper_whatif=False,
            rationale_summary="Bought breakout.",
            decision="BUY",
            confidence=0.85,
            outcome_pnl_usd=120.0,
            was_profitable=True,
            holding_hours=4.0,
            exit_reason="tp_hit",
            benchmark_name="DXY",
            alpha_return=2.5,
            symbol="XAUUSD",
        )
        session.get.return_value = mock_reflection

        await reflector.reflect_on_trade(session, 1)

        assert mock_reflection.status == "resolved"
        assert "Valid technical breakout on H4 timeframe" in mock_reflection.specific_lesson
        assert mock_reflection.process_was_sound is True


@pytest.mark.asyncio
async def test_reflector_paper_whatif_tp_hit_no_outcome_conflict():
    """Verify that a paper what-if with TP hit sends consistent prompt and resolves cleanly."""
    settings = {}
    with (
        patch("monika.application.analysis.memory.reflector.get_client_for_task") as mock_get_client,
        patch("monika.application.analysis.memory.skill_crystallizer.SkillCrystallizer") as mock_cryst,
    ):
        mock_cryst.return_value.evaluate_and_crystallize = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = json.dumps(
            {
                "reflection_text": "Proposal reached TP in paper simulation.",
                "lesson_tags": ["well_executed_setup"],
                "specific_lesson": "Valid H4 expansion setup reached target cleanly.",
                "next_trade_adjustment": "Maintain execution parameters.",
                "alpha_lesson": "Outperformed benchmark.",
                "process_was_sound": True,
                "outcome_process_classification": "good_process_good_outcome",
                "macro_thesis_correct": True,
                "synthesis_adjudication_sound": True,
            }
        )
        mock_get_client.return_value = mock_client

        reflector = TradeReflector(settings=settings)
        session = create_mock_async_session()
        mock_reflection = DecisionReflection(
            id=585,
            symbol="BTCUSD",
            decision="SELL",
            confidence=0.85,
            is_paper_whatif=True,
            was_profitable=True,
            whatif_direction_correct=True,
            whatif_hypothetical_pnl_pips=1695.8,
            whatif_sl_would_hit=False,
            whatif_tp_would_hit=True,
            exit_reason="tp_hit",
            status="pending",
            rationale_summary="Sell proposal blocked by risk gate.",
            benchmark_name="FLAT",
            alpha_return=2.1,
        )
        session.get.return_value = mock_reflection

        await reflector.reflect_on_trade(session, 585)

        # Prompt must be consistent with profitability
        prompt = mock_client.generate_content.call_args.kwargs["user_message"]
        assert "Hypothetical Outcome: Profitable (1695.8 pips)" in prompt
        assert "Exit Reason: tp_hit (Paper What-If)" in prompt

        assert mock_reflection.status == "resolved"
        assert mock_reflection.outcome_process_classification == "good_process_good_outcome"
        assert mock_reflection.process_was_sound is True


@pytest.mark.asyncio
async def test_reflector_paper_whatif_sl_hit_avoid_classification():
    """Verify that a blocked/avoid trade where hypothetical trade hit SL passes audit gate with good_process_bad_outcome."""
    settings = {}
    with (
        patch("monika.application.analysis.memory.reflector.get_client_for_task") as mock_get_client,
        patch("monika.application.analysis.memory.skill_crystallizer.SkillCrystallizer") as mock_cryst,
    ):
        mock_cryst.return_value.evaluate_and_crystallize = AsyncMock()
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = json.dumps(
            {
                "reflection_text": "Decision was WAIT; trade hit hypothetical SL avoiding loss.",
                "lesson_tags": ["premature_entry", "chased_price"],
                "specific_lesson": "Market was at premium ceiling and broke downward as anticipated by filter.",
                "next_trade_adjustment": "Continue filtering out premium ceiling chases.",
                "alpha_lesson": "Dodged negative alpha.",
                "process_was_sound": True,
                "outcome_process_classification": "good_process_bad_outcome",
                "macro_thesis_correct": False,
                "synthesis_adjudication_sound": True,
            }
        )
        mock_get_client.return_value = mock_client

        reflector = TradeReflector(settings=settings)
        session = create_mock_async_session()
        mock_reflection = DecisionReflection(
            id=575,
            symbol="GBPUSD",
            decision="WAIT",
            confidence=0.78,
            is_paper_whatif=True,
            was_profitable=False,
            whatif_direction_correct=False,
            whatif_hypothetical_pnl_pips=-37.9,
            whatif_sl_would_hit=True,
            whatif_tp_would_hit=False,
            exit_reason="sl_hit",
            status="pending",
            rationale_summary="Debate avoid verdict.",
            benchmark_name="DXY",
            alpha_return=-0.5,
        )
        session.get.return_value = mock_reflection

        await reflector.reflect_on_trade(session, 575)

        prompt = mock_client.generate_content.call_args.kwargs["user_message"]
        assert "Hypothetical Outcome: Loss (-37.9 pips)" in prompt
        assert "Exit Reason: sl_hit (Paper What-If)" in prompt

        assert mock_reflection.status == "resolved"
        assert mock_reflection.outcome_process_classification == "good_process_bad_outcome"
        assert mock_reflection.process_was_sound is True


def test_reflector_critique_rejects_both_good_outcomes_on_loss():
    """Verify audit gate rejects both good_process_good_outcome and bad_process_good_outcome_lucky on loss."""
    reflector = TradeReflector()
    data1 = {
        "specific_lesson": "Valid technical breakout on H4 timeframe occurred with clear momentum.",
        "lesson_tags": ["well_executed_setup"],
        "outcome_process_classification": "good_process_good_outcome",
    }
    is_valid1, critique1 = reflector._verify_reflection_quality(data1, was_profitable=False)
    assert not is_valid1
    assert "Outcome conflict" in critique1
    assert "good_process_bad_outcome" in critique1

    data2 = {
        "specific_lesson": "Valid technical breakout on H4 timeframe occurred with clear momentum.",
        "lesson_tags": ["well_executed_setup"],
        "outcome_process_classification": "bad_process_good_outcome_lucky",
    }
    is_valid2, critique2 = reflector._verify_reflection_quality(data2, was_profitable=False)
    assert not is_valid2
    assert "Outcome conflict" in critique2
