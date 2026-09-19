"""
Test suite for HybridToolCatalog, ToolSpillStorage, and CSV Market Data.
"""

import os
import pytest
from pathlib import Path
from analysis.tools.tool_catalog import HybridToolCatalog
from analysis.tools.tool_spill import ToolSpillStorage, truncate_head_tail


def test_hybrid_tool_catalog():
    catalog = HybridToolCatalog()
    # Register pinned core tool
    catalog.register_tool(
        name="submit_asset_analysis",
        category="core",
        description="Submit final trading decision for asset",
        parameters_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
        is_pinned=True
    )
    # Register deferred specialized tool
    catalog.register_tool(
        name="get_cot_report",
        category="sentiment",
        description="Fetch CFTC Commitments of Traders institutional positioning",
        parameters_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
        is_pinned=False
    )
    catalog.register_tool(
        name="get_funding_rate",
        category="sentiment",
        description="Fetch crypto perpetual futures funding rates and open interest",
        parameters_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
        is_pinned=False
    )

    # 1. Check pinned tools
    pinned = catalog.get_pinned_tools()
    assert len(pinned) == 1
    assert pinned[0]["name"] == "submit_asset_analysis"

    # 2. Search deferred tools
    results = catalog.search_tools("institutional commitments of traders")
    assert len(results) > 0
    assert results[0]["name"] == "get_cot_report"

    crypto_results = catalog.search_tools("crypto perpetual funding")
    assert len(crypto_results) > 0
    assert crypto_results[0]["name"] == "get_funding_rate"

    # 3. Describe tool
    desc = catalog.describe_tool("get_cot_report")
    assert desc is not None
    assert desc["name"] == "get_cot_report"
    assert "parameters" in desc


def test_tool_spill_storage(tmp_path):
    storage = ToolSpillStorage(spill_dir=tmp_path)

    # Short output: no spill
    short_text = "Price at 1.0850, RSI 55."
    spilled, res = storage.maybe_spill("test_tool", "call_1", short_text, threshold_chars=100)
    assert spilled is False
    assert res == short_text

    # Long output: should spill
    long_text = "A" * 500
    spilled2, res2 = storage.maybe_spill("test_tool", "call_2", long_text, threshold_chars=100, preview_chars=50)
    assert spilled2 is True
    assert "<persisted-output>" in res2
    assert "Full output saved to:" in res2

    # Truncate head tail
    head_tail = truncate_head_tail("START" + ("X" * 100) + "END", max_chars=20, head_pct=0.4)
    assert "OUTPUT TRUNCATED" in head_tail
    assert head_tail.startswith("START")
