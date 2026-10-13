# ==============================================================================
# File: tests/data_sources/test_phase9_web_and_search.py
# ==============================================================================

import asyncio
import json
import pytest
from pathlib import Path

from utils.content_distiller import ContentDistiller
from data_sources.web_search import SearchMemo, WebSearchService
from analysis.tools.unified_registry import unified_tool_registry
from analysis.tools.domain.web_tools import handle_web_search, handle_web_fetch, WebSearchInput, WebFetchInput


def test_content_distiller_base64_defuse():
    distiller = ContentDistiller(max_chars=5000)

    # Text containing a large inline base64 image
    fake_base64 = "data:image/png;base64," + "A" * 200
    raw = f"Header text.\n<img src='{fake_base64}' />\nFooter conclusion."

    defused = distiller.defuse_binaries(raw)
    assert "[INLINE_IMAGE_BLOB_DEFUSED]" in defused
    assert fake_base64 not in defused
    assert "Header text." in defused
    assert "Footer conclusion." in defused


def test_content_distiller_disk_spill_and_partitioning(tmp_path):
    distiller = ContentDistiller(max_chars=500, spill_dir=tmp_path)

    # Create a long document with narrative text and a structured table
    narrative = "Market analysis: EURUSD is consolidating above 1.0850 ahead of the ECB rate announcement. " * 10
    table = "\n\n| Currency | Yield | Bias |\n| EUR | 3.50% | Neutral |\n| USD | 5.25% | Bullish |\n\n"
    large_doc = narrative + table + narrative

    result = distiller.distill(large_doc, title="EURUSD Macro Review", url="https://example.com/macro")

    assert result["spilled"] is True
    assert result["storage_key"] is not None
    assert result["original_length"] > 500

    # Ensure spilled file exists on disk
    spill_file = tmp_path / f"{result['storage_key']}.txt"
    assert spill_file.exists()
    with open(spill_file, "r", encoding="utf-8") as f:
        spilled_content = f.read()
    assert "Market analysis" in spilled_content

    # Ensure distilled output includes notice and key table data
    distilled_text = result["distilled_text"]
    assert "retrieve_spilled_context" in distilled_text
    assert result["storage_key"] in distilled_text
    assert "Key Structured Data:" in distilled_text


@pytest.mark.asyncio
async def test_search_memo_single_flight_coalescing():
    memo = SearchMemo()
    call_count = 0

    async def expensive_search():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return {"query": "US 10Y Yield", "results": [{"title": "Treasury Rally", "url": "https://ust.gov"}]}

    # Launch two concurrent identical searches
    t1 = asyncio.create_task(memo.execute_coalesced("key_1", expensive_search))
    t2 = asyncio.create_task(memo.execute_coalesced("key_1", expensive_search))

    res1, res2 = await asyncio.gather(t1, t2)

    # Only one underlying network request should have been made
    assert call_count == 1
    assert res1["query"] == "US 10Y Yield"
    assert res2["query"] == "US 10Y Yield"
    assert res2.get("coalesced") is True or res1.get("coalesced") is True


@pytest.mark.asyncio
async def test_web_tools_unified_registry_and_fetch(monkeypatch, tmp_path):
    # Verify tools registered in unified_tool_registry
    search_tool = unified_tool_registry.get_tool("web_search")
    fetch_tool = unified_tool_registry.get_tool("web_fetch")
    assert search_tool is not None
    assert fetch_tool is not None

    # Mock web reader response
    from analysis.tools.domain import web_tools
    distiller = ContentDistiller(max_chars=2000, spill_dir=tmp_path)
    monkeypatch.setattr(web_tools, "_content_distiller", distiller)

    async def mock_read(url):
        return {
            "success": True,
            "url": url,
            "title": "ECB Policy Statement",
            "content": "The Governing Council decided to keep the three key ECB interest rates unchanged.",
        }

    monkeypatch.setattr(web_tools._web_reader, "read_url", mock_read)

    fetch_output = await handle_web_fetch(WebFetchInput(url="https://ecb.europa.eu/press/statement.htm"))
    assert "# ECB Policy Statement" in fetch_output
    assert "Governing Council" in fetch_output
