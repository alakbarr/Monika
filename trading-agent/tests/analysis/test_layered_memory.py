import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.memory.layered_memory import LayeredMemoryManager
from utils.llm.prompt_compressor import estimate_tokens

@pytest.mark.asyncio
async def test_layered_memory_core_budget():
    mgr = LayeredMemoryManager()
    core = await mgr.get_core_memory(session=None)
    assert "REGIME:" in core
    assert "LESSONS:" in core
    assert "HEAT:" in core
    assert estimate_tokens(core) <= 800

@pytest.mark.asyncio
async def test_layered_memory_symbol():
    mgr = LayeredMemoryManager()
    mgr.session_search.get_symbol_precedents_hybrid = AsyncMock(return_value=[])
    mgr.session_search.get_symbol_precedents = MagicMock(return_value=[])
    mem = await mgr.get_symbol_memory(session=None, symbol="XAUUSD")
    assert mem == ""


@pytest.mark.asyncio
async def test_layered_memory_hybrid_rrf_precedents():
    """Verify that get_symbol_memory calls get_symbol_precedents_hybrid with RRF."""
    mgr = LayeredMemoryManager()
    mgr.session_search.get_symbol_precedents_hybrid = AsyncMock(return_value=[
        {
            "timestamp": "2026-09-01T10:00:00",
            "stage": "execution",
            "decision": "BUY",
            "confidence": 0.85,
            "pnl": 1.25,
            "content": "Breakout continuation above 2500"
        }
    ])
    mem = await mgr.get_symbol_memory(session=None, symbol="XAUUSD", regime="trending_bullish")
    assert "PRECEDENTS:" in mem
    assert "BUY" in mem
    assert "2500" in mem
    mgr.session_search.get_symbol_precedents_hybrid.assert_awaited_once_with(
        "XAUUSD", current_regime="trending_bullish", setup_text="XAUUSD trending_bullish", limit=2, session=None
    )


@pytest.mark.asyncio
async def test_layered_memory_symbol_budget_cap():
    """Verify that get_symbol_memory enforces <= 400 token budget cap."""
    mgr = LayeredMemoryManager()
    mgr.session_search.get_symbol_precedents_hybrid = AsyncMock(return_value=[
        {
            "timestamp": "2026-09-01T10:00:00",
            "stage": "execution",
            "decision": "BUY",
            "confidence": 0.9,
            "pnl": 2.5,
            "content": "A" * 2000  # Large content
        }
    ])
    mem = await mgr.get_symbol_memory(session=None, symbol="EURUSD")
    assert estimate_tokens(mem) <= 400


@pytest.mark.asyncio
async def test_layered_memory_negative_constraints():
    """Verify that negative constraints from failure taxonomy are injected from reflections."""
    mgr = LayeredMemoryManager()
    mgr.session_search.get_symbol_precedents_hybrid = AsyncMock(return_value=[])
    mgr.session_search.get_symbol_precedents = MagicMock(return_value=[])

    mock_session = AsyncMock()
    mock_reflection = MagicMock()
    mock_reflection.lesson_tags = ["false_breakout", "sl_too_tight"]
    mock_reflection.specific_lesson = "Bought the false top without confirmation"
    mock_reflection.alpha_lesson = None
    mock_reflection.reflection_text = ""
    mock_reflection.next_trade_adjustment = None

    # Calls: 1. Reflections for symbol, 2. Trades for win rate, 3. Losing reflections for negative constraints, 4. Losing trades
    res1 = MagicMock()
    res1.scalars.return_value.all.return_value = [mock_reflection]
    res2 = MagicMock()
    res2.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(side_effect=[res1, res2, res1, res2])

    mem = await mgr.get_symbol_memory(session=mock_session, symbol="GBPUSD", regime="trending")
    assert "NEGATIVE_CONSTRAINTS:" in mem
    assert "FALSE_BREAKOUT" in mem
    assert "SL_TOO_TIGHT" in mem


