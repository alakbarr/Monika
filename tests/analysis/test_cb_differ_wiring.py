import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.agent.chat_tool_router import ChatToolRouter
from monika.application.analysis.calculators.universal_cb_differ import UniversalCentralBankDiffer
from monika.application.analysis.prefetch.stage1_prefetcher import (
    PREFETCH_KEY_TO_TOOL,
    Stage1DataBundler,
)
from monika.application.scheduler.post_release_analyzer import PostReleaseAnalyzer
from monika.application.analysis.tools.tool_registry import ProgressiveToolRegistry
from monika.infrastructure.database.models import CentralBankDocument
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_universal_cb_differ_success_and_robust_parsing():
    """Verify UniversalCentralBankDiffer returns status success and handles varied paragraph formats."""
    mock_session = AsyncMock()

    # Create 2 mock documents
    doc1 = MagicMock(spec=CentralBankDocument)
    doc1.title = "FOMC Meeting 2"
    doc1.meeting_date = MagicMock()
    doc1.meeting_date.strftime.return_value = "2026-10-28"
    doc1.hawkish_dovish_score = 0.5
    doc1.paragraphs_json = '["Economic activity expanding at a strong pace.", "Inflation remains elevated."]'
    doc1.full_text = "Economic activity expanding at a strong pace.\n\nInflation remains elevated."

    doc2 = MagicMock(spec=CentralBankDocument)
    doc2.title = "FOMC Meeting 1"
    doc2.meeting_date = MagicMock()
    doc2.meeting_date.strftime.return_value = "2026-09-16"
    doc2.hawkish_dovish_score = 0.2
    # Test list format for paragraphs_json
    doc2.paragraphs_json = ["Economic activity expanding at a solid pace.", "Inflation remains elevated."]
    doc2.full_text = "Economic activity expanding at a solid pace.\n\nInflation remains elevated."

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [doc1, doc2]
    mock_session.execute.return_value = mock_res

    differ = UniversalCentralBankDiffer(mock_session)
    differ.router.ensure_cb_document_available = AsyncMock()

    res = await differ.diff_cb_documents(bank="FED", doc_type="STATEMENT")

    assert res["status"] == "success"
    assert res["bank"] == "FED"
    assert res["doc_type"] == "STATEMENT"
    assert res["current_meeting"]["date"] == "2026-10-28"
    assert res["previous_meeting"]["date"] == "2026-09-16"
    assert res["monetary_tone_shift"]["delta_score"] == 0.3
    assert res["monetary_tone_shift"]["classification"] == "HAWKISH_TIGHTENING"
    assert len(res["redline_modifications"]["key_additions"]) >= 1


def test_tool_registry_has_cb_differ_in_macro_category():
    """Verify diff_central_bank_documents is mapped under the MACRO category pack."""
    registry = ProgressiveToolRegistry()
    macro_tools = registry.CATEGORY_MAP.get("MACRO", [])
    assert "diff_central_bank_documents" in macro_tools

    loaded = registry.load_category("MACRO")
    tool_names = [t.get("name") for t in loaded]
    assert "diff_central_bank_documents" in tool_names


def test_stage1_prefetcher_cb_redline_diff_mapping():
    """Verify cb_redline_diff is registered in PREFETCH_KEY_TO_TOOL and compressed in terminal."""
    assert PREFETCH_KEY_TO_TOOL.get("cb_redline_diff") == "diff_central_bank_documents"

    # Test terminal compression
    session = create_mock_async_session()
    bundler = Stage1DataBundler(session, settings={})

    mock_data = {
        "cb_redline_diff": {
            "status": "success",
            "bank": "FED",
            "doc_type": "STATEMENT",
            "monetary_tone_shift": {
                "classification": "NEUTRAL_STATUS_QUO",
                "delta_score": 0.0,
                "summary": "Policy maintained unchanged.",
            },
            "redline_modifications": {
                "key_additions": ["+ [NEW] Economic activity expanding at a strong pace."],
                "key_deletions": [],
            },
        }
    }

    terminal = bundler._synthesize_tier1_terminal(mock_data)
    assert "central_bank_redline_shift" in terminal
    assert "FED STATEMENT: NEUTRAL_STATUS_QUO" in terminal["central_bank_redline_shift"]
    assert "Economic activity expanding at a strong pace." in terminal["central_bank_redline_shift"]


def test_post_release_analyzer_build_surprise_context_with_cb_diff():
    """Verify PostReleaseAnalyzer appends redline delta into surprise context."""
    analyzer = PostReleaseAnalyzer(settings={})
    event = MagicMock()
    event.event_name = "Fed Interest Rate Decision"
    event.actual = "4.00%"
    event.forecast = "4.00%"
    event.previous = "4.00%"

    cb_summary = (
        "[CENTRAL BANK STATEMENT REDLINE DELTA]\n"
        "• FED Statement Stance: NEUTRAL_STATUS_QUO (Delta: +0.00)\n"
        "  Key Additions: + [NEW] 10 - 2 vote"
    )

    context = analyzer._build_surprise_context([event], cb_diff_summary=cb_summary)
    assert "POST-RELEASE ANALYSIS" in context
    assert "Fed Interest Rate Decision" in context
    assert "[CENTRAL BANK STATEMENT REDLINE DELTA]" in context
    assert "10 - 2 vote" in context


def test_chat_tool_router_cb_diff_routing():
    """Verify ChatToolRouter routes central bank statement comparison queries."""
    sample_tools = [
        {"name": "get_economic_calendar", "description": "Calendar"},
        {"name": "diff_central_bank_documents", "description": "Diff central bank documents"},
        {"name": "get_news_digest", "description": "News digest"},
    ]
    router = ChatToolRouter(all_tools=sample_tools)

    # 1. Macro command
    tools_cmd = [t["name"] for t in router.route_tools_for_query("/macro")]
    assert "diff_central_bank_documents" in tools_cmd

    # 2. Natural language question about statement diff
    tools_nlp = [
        t["name"]
        for t in router.route_tools_for_query("Tolong bandingkan statement FOMC terbaru dengan notulen sebelumnya")
    ]
    assert "diff_central_bank_documents" in tools_nlp
