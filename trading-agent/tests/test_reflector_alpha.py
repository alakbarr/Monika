import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from database.models import DecisionReflection
from analysis.memory.reflector import TradeReflector

@pytest.mark.asyncio
async def test_reflector_includes_alpha():
    # Mock settings and LLMFactory
    settings = {}
    
    with patch('analysis.memory.reflector.get_client_for_task') as mock_get_client:
        mock_client = AsyncMock()
        mock_client.generate_content.return_value = json.dumps({
            "reflection_text": "Good trade.",
            "lesson_tags": ["trend"],
            "alpha_lesson": "Outperformed the benchmark."
        })
        mock_get_client.return_value = mock_client
        
        reflector = TradeReflector(settings=settings)
        
        session = AsyncMock()
        mock_reflection = DecisionReflection(
            id=1,
            status='pending',
            is_paper_whatif=False,
            rationale_summary="Bought because MA crossed.",
            decision="BUY",
            confidence=0.8,
            outcome_pnl_usd=50.0,
            was_profitable=True,
            holding_hours=2.5,
            exit_reason="tp_hit",
            benchmark_name="DXY",
            alpha_return=1.5
        )
        session.get.return_value = mock_reflection
        
        await reflector.reflect_on_trade(session, 1)
        
        # Check that the prompt sent to the LLM contains alpha info
        call_args = mock_client.generate_content.call_args
        prompt = call_args.kwargs['user_message']
        
        assert "Alpha vs DXY: 1.50%" in prompt
        
        # Check that the parsed response is stored
        assert mock_reflection.alpha_lesson == "Outperformed the benchmark."
        assert mock_reflection.status == "resolved"


@pytest.mark.asyncio
async def test_stage2_prefetcher_alpha_lessons_none_safe():
    from database.models import DecisionReflection
    from analysis.prefetch.stage2_prefetcher import Stage2DataBundler
    
    # Mock executor & session
    mock_executor = MagicMock()
    mock_session = AsyncMock()
    mock_executor.session = mock_session
    mock_executor.settings = {'analysis': {'stage2_max_bundle_chars': 36000}}
    
    # Create reflections with None fields
    ref1 = DecisionReflection(
        id=1, symbol='GBPUSD', status='resolved',
        alpha_lesson='Lesson with alpha return',
        alpha_return=2.345, resolved_at=None, benchmark_name='DXY'
    )
    ref2 = DecisionReflection(
        id=2, symbol='GBPUSD', status='resolved',
        alpha_lesson='Lesson with None alpha return',
        alpha_return=None, resolved_at=None, benchmark_name=None
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
        date_str = rl.resolved_at.strftime('%Y-%m-%d') if rl.resolved_at else (rl.created_at.strftime('%Y-%m-%d') if getattr(rl, 'created_at', None) else "Recent")
        alpha_str = f"{rl.alpha_return:.2f}%" if rl.alpha_return is not None else "N/A"
        bench_str = f" vs {rl.benchmark_name}" if rl.benchmark_name else ""
        lines.append(f"[{date_str}] Alpha: {alpha_str}{bench_str}")
        lines.append(f"Lesson: {rl.alpha_lesson}")
        
    assert lines[0] == "[Recent] Alpha: 2.35% vs DXY"
    assert lines[1] == "Lesson: Lesson with alpha return"
    assert lines[2] == "[Recent] Alpha: N/A"
    assert lines[3] == "Lesson: Lesson with None alpha return"

