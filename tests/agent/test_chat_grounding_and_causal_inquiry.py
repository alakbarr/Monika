"""Tests for market catalyst inquiries, query complexity classification, epistemic humility, and pseudo-tool parsing."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.agent.chat.prompt_builder import PromptBuilderMixin
from monika.application.agent.chat.coordinator import ChatAgent
from monika.domain.market.news_impact_keywords import HIGH_IMPACT_KEYWORDS, DEESCALATION_KEYWORDS
from monika.application.analysis.memory.chronicle_writer import CHRONICLE_CATEGORIES
from monika.application.agent.harness.pseudo_tool_parser import extract_pseudo_tool_calls


class DummyPromptBuilder(PromptBuilderMixin):
    def __init__(self):
        pass


@pytest.mark.asyncio
async def test_classify_query_complexity_incident_questions():
    """Verify that all 5 causal and challenge questions from the reported incident classify as complex."""
    builder = DummyPromptBuilder()

    incident_questions = [
        "Apa yang membuat Emas kemarin naik?",
        "Bukan karena ada perkembangan baik terkait perundingan Iran-Amerika dan harga minyak yang turun?",
        "Sumbermu dari mana?",
        "Lalu kenapa kamu mengatak eskalasi geopolitik selat hormuz dan dan lonjakan harga minyak?",
        "Kenapa 'Jika'? Apakah di data yang aku sediakan tidak ada?",
        "Kenapa order buy XAUUSD tadi ditolak?",
        "Faktor apa yang menyebabkan WTI anjlok 5% kemarin?",
        "Why did gold rally during yesterday's London session?",
    ]

    for q in incident_questions:
        complexity = await builder._classify_query_complexity(q)
        assert complexity in ("complex", "deep_research"), f"Failed for query: {q} (got {complexity})"


def test_deescalation_keywords_integrated():
    """Verify de-escalation, peace talks, and diplomacy keywords are part of high-impact news keywords."""
    for kw in ["us-iran talks", "doha talks", "hormuz reopening", "ceasefire", "peace agreement"]:
        assert kw in HIGH_IMPACT_KEYWORDS, f"Keyword '{kw}' missing from HIGH_IMPACT_KEYWORDS"
        assert kw in DEESCALATION_KEYWORDS, f"Keyword '{kw}' missing from DEESCALATION_KEYWORDS"


def test_chronicle_categories_contain_diplomacy():
    """Verify geopolitical chronicle categories index diplomacy, peace, and negotiation milestones."""
    geopol_keywords = CHRONICLE_CATEGORIES["geopolitical"]
    for kw in ["diplomacy", "peace", "negotiation", "talks"]:
        assert kw in geopol_keywords, f"Keyword '{kw}' missing from geopolitical chronicle keywords"


@pytest.mark.asyncio
async def test_sticky_tier_escalates_on_complex_query():
    """Verify that sticky tier escalates from tier_lite to tier_deep when a complex inquiry arrives."""
    agent = ChatAgent.__new__(ChatAgent)
    agent.settings = {"llm": {"chat_sticky_model": True}}
    agent._active_session_tier = "tier_lite"
    agent._classify_query_complexity = AsyncMock(return_value="complex")

    resolved = await agent._resolve_tier_with_sticky("Apa yang membuat Emas kemarin naik?", "auto")
    assert resolved == "tier_deep", f"Expected tier_deep, got {resolved}"
    assert agent._active_session_tier == "tier_deep"


def test_extract_pseudo_tool_calls_xml():
    """Verify pseudo tool calls emitted in XML syntax are cleanly parsed."""
    raw_text = """
    I will analyze the market using the tool:
    <tool_call name="get_news_items">
    {"query": "iran talks", "limit": 5}
    </tool_call>
    """
    calls = extract_pseudo_tool_calls(raw_text, available_tool_names={"get_news_items"})
    assert len(calls) == 1
    assert calls[0]["name"] == "get_news_items"
    assert calls[0]["input"]["query"] == "iran talks"
    assert calls[0]["input"]["limit"] == 5


def test_extract_pseudo_tool_calls_markdown_json():
    """Verify pseudo tool calls emitted in Markdown JSON codeblock are parsed."""
    raw_text = """
    ```json
    {
        "name": "get_price_history",
        "parameters": {
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "count": 50
        }
    }
    ```
    """
    calls = extract_pseudo_tool_calls(raw_text, available_tool_names={"get_price_history"})
    assert len(calls) == 1
    assert calls[0]["name"] == "get_price_history"
    assert calls[0]["input"]["symbol"] == "XAUUSD"
    assert calls[0]["input"]["count"] == 50
