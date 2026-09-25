import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from analysis.tools.tool_executor import ToolExecutor
from analysis.prefetch.stage1_prefetcher import Stage1DataBundler
from utils.llm.prompt_compressor import ContextCompressor
from utils.llm.caveman_compressor import compress_tool_payload
from database.models import DXYData

@pytest.mark.asyncio
async def test_stage1_prefetch_tuple_and_satisfied_tools():
    session = AsyncMock()
    settings = {}
    
    with patch("analysis.prefetch.stage1_prefetcher.ToolExecutor") as MockExecutor:
        mock_instance = MockExecutor.return_value
        async def mock_execute(tool_name, tool_input):
            return {"status": "ok", "tool": tool_name}
        mock_instance.execute.side_effect = mock_execute
        
        bundler = Stage1DataBundler(session, settings)
        compressed_json, satisfied_tools, raw_data = await bundler.prefetch_all_data()
        
        assert isinstance(compressed_json, str)
        parsed = json.loads(compressed_json)
        assert isinstance(parsed, dict)
        assert "dxy" in parsed
        assert "get_dxy" in satisfied_tools
        assert "get_vix" in satisfied_tools
        assert len(satisfied_tools) >= 13

@pytest.mark.asyncio
async def test_tool_get_dxy_tier1_normal_window():
    session = AsyncMock()
    executor = ToolExecutor(session)
    
    d1 = DXYData(date=datetime.now(timezone.utc), close=104.5)
    d2 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=5), close=103.8)
    
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [d1, d2]
    session.execute = AsyncMock(return_value=mock_result)
    
    res = await executor._tool_get_dxy({"days_back": 10})
    assert res["latest"]["close"] == 104.5
    assert res["trend_5d"] == "strengthening"
    assert res["staleness_note"] is None or "Weekend" in (res["staleness_note"] or "")

@pytest.mark.asyncio
async def test_tool_get_dxy_tier2_stale_fallback():
    session = AsyncMock()
    executor = ToolExecutor(session)
    
    # First query (window 10d) returns empty
    # Second query (fallback limit 10) returns older rows
    d1 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=20), close=102.0)
    d2 = DXYData(date=datetime.now(timezone.utc) - timedelta(days=25), close=101.5)
    
    mock_empty = MagicMock()
    mock_empty.scalars().all.return_value = []
    
    mock_fallback = MagicMock()
    mock_fallback.scalars().all.return_value = [d1, d2]
    
    session.execute = AsyncMock(side_effect=[mock_empty, mock_fallback])
    
    res = await executor._tool_get_dxy({"days_back": 10})
    assert res["latest"]["close"] == 102.0
    assert "fallback" in (res.get("staleness_note") or "").lower()

@pytest.mark.asyncio
async def test_tool_get_dxy_tier3_synthetic_proxy_fallback():
    session = AsyncMock()
    executor = ToolExecutor(session)
    
    # Both queries to DXYData return empty
    mock_empty = MagicMock()
    mock_empty.scalars().all.return_value = []
    session.execute = AsyncMock(return_value=mock_empty)
    
    with patch("utils.market.usd_strength_proxy.compute_usd_strength_proxy") as mock_proxy:
        mock_proxy.return_value = {
            "weighted_usd_change_pct": 0.35,
            "direction": "strengthening",
            "method": "basket_proxy",
            "timeframe": "H4"
        }
        res = await executor._tool_get_dxy({"days_back": 10})
        assert res.get("source") == "synthetic_basket_proxy"
        assert res["latest"]["close"] == 100.35
        assert res["trend_5d"] == "strengthening"

@pytest.mark.asyncio
async def test_validate_fundamental_brief_with_prefetched_tools():
    session = AsyncMock()
    executor = ToolExecutor(session, prefetch_satisfied_tools={"get_dxy", "get_vix"})
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=mock_result)
    
    payload = {
        "macro_narrative": "DXY is trending up with strong USD baseline. VIX is moderate at 16 indicating balanced risk sentiment.",
        "currency_bias": {"USD": "bullish", "EUR": "bearish", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "bearish", "OIL": "neutral", "BTC": "bullish"},
        "invalidation_conditions": {
            "USD": "DXY drops below 102.50 support level for more than 48 hours",
            "EUR": "ECB unexpectedly hikes rates by 25bps at upcoming meeting",
            "XAU": "US 10Y yield falls sharply below 3.80% level triggering rally",
            "BTC": "BTC spot ETF outflows exceed 500M USD over 3 consecutive days"
        },
        "currency_confidence": {"USD": 0.8, "EUR": 0.7, "XAU": 0.75, "BTC": 0.7},
        "strongest_counter_thesis": "If upcoming NFP data comes significantly below 100k, Fed cut expectations could accelerate, reversing USD strength.",
        "priced_in_assessment": {
            "dominant_driver": "Fed rate expectations",
            "priced_in_score": 6,
            "sell_the_news_risk": "medium",
            "cot_positioning_percentile": 60.0
        }
    }
    
    errors = await executor._validate_fundamental_brief_completeness(payload)
    assert not errors, f"Expected no errors, got: {errors}"

@pytest.mark.asyncio
async def test_validate_fundamental_brief_with_uncertain_flag_per_rule2():
    session = AsyncMock()
    # get_dxy was not in called_tools or prefetch_satisfied_tools, but narrative notes DXY is uncertain per Rule 2
    executor = ToolExecutor(session, prefetch_satisfied_tools={"get_vix"})
    
    payload = {
        "macro_narrative": "DXY data unavailable and DXY uncertain due to upstream feed outage. VIX is at 15 indicating normal risk sentiment.",
        "currency_bias": {"USD": "neutral", "EUR": "neutral", "GBP": "neutral", "JPY": "neutral", "AUD": "neutral", "XAU": "neutral", "OIL": "neutral", "BTC": "neutral"},
        "strongest_counter_thesis": "If geopolitical risk escalates over the weekend, safe haven flows could spike unpredictably without DXY baseline.",
        "priced_in_assessment": {
            "dominant_driver": "Macro uncertainty",
            "priced_in_score": 5,
            "sell_the_news_risk": "low",
            "cot_positioning_percentile": 50.0
        }
    }
    
    errors = await executor._validate_fundamental_brief_completeness(payload)
    # Should NOT have MISSING_TOOL for get_dxy because it was flagged as uncertain
    missing_dxy_errs = [e for e in errors if "get_dxy" in e]
    assert len(missing_dxy_errs) == 0

def test_json_safe_compression():
    compressor = ContextCompressor()
    large_bundle = {
        "economic_calendar": {"events": [{"event_name": f"Event {i}", "impact": "high"} for i in range(50)]},
        "news_digest": {"items": [{"headline": f"News headline {i}", "summary": "Detailed summary " * 20} for i in range(40)]},
        "dxy": {"latest": {"close": 104.5}, "history": [{"date": f"2026-08-{i:02d}", "close": 104.0 + i * 0.05} for i in range(30)]},
        "vix": {"latest": {"close": 15.2}, "history": [{"date": f"2026-08-{i:02d}", "close": 15.0} for i in range(30)]}
    }
    
    compressed_str = compressor.compress_stage1_bundle(large_bundle, max_tokens=1000)
    assert isinstance(compressed_str, str)
    # Verify it can always be parsed back as valid JSON
    parsed = json.loads(compressed_str)
    assert "dxy" in parsed
    assert "vix" in parsed
    assert "economic_calendar" in parsed
