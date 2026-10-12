# ==============================================================================
# File: tests/test_capability_gaps.py
# ==============================================================================

"""
Comprehensive Verification Test Suite for Closed Capability Gaps (Q1-Q150).
Verifies:
  1. Technical indicators (Pivot points, Ichimoku, Chart patterns, Seasonality, Divergences)
  2. Emerging markets & macro fallbacks (BI Rate, BPS, Earnings, GVZ/OVX)
  3. Dynamic skills loading & prompt matching (49+ skills, new SKILL.md packages)
  4. Tool definitions & ToolExecutor dispatch
  5. ChatToolRouter query routing & baseline bundle injection
  6. Persistent script storage & sandbox execution
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# Ensure repo path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ---------------------------------------------------------------------------
# 1. Technical Indicators & Pattern Recognition
# ---------------------------------------------------------------------------

def test_pivot_points_calculation():
    from indicators.technical import compute_pivot_points

    high, low, close = 2660.0, 2640.0, 2650.0

    # Test Classic
    classic = compute_pivot_points(high, low, close, method="classic")
    assert "pivot" in classic
    assert classic["pivot"] == pytest.approx(2650.0)
    assert classic["r1"] > classic["pivot"] > classic["s1"]

    # Test Camarilla
    camarilla = compute_pivot_points(high, low, close, method="camarilla")
    assert "r4" in camarilla and "s4" in camarilla
    assert camarilla["r4"] > camarilla["r3"]

    # Test Woodie
    woodie = compute_pivot_points(high, low, close, method="woodie")
    assert "pivot" in woodie

    # Test All
    all_pivots = compute_pivot_points(high, low, close, method="all")
    assert "classic" in all_pivots
    assert "camarilla" in all_pivots
    assert "woodie" in all_pivots


def test_ichimoku_calculation():
    from indicators.technical import compute_ichimoku

    # Create synthetic OHLCV data (100 bars)
    np.random.seed(42)
    n = 100
    prices = 2000.0 + np.cumsum(np.random.randn(n) * 2.0)
    df = pd.DataFrame({
        "open": prices,
        "high": prices + np.random.uniform(0.5, 3.0, n),
        "low": prices - np.random.uniform(0.5, 3.0, n),
        "close": prices + np.random.uniform(-1.0, 1.0, n),
        "volume": np.random.randint(100, 1000, n),
    })

    result = compute_ichimoku(df)
    assert result["status"] == "success"
    assert "tenkan_sen" in result
    assert "kijun_sen" in result
    assert "senkou_span_a" in result
    assert "senkou_span_b" in result
    assert "chikou_span" in result
    assert "cloud_bias" in result
    assert any(b in result["cloud_bias"] for b in ("bullish", "bearish", "neutral"))


def test_chart_patterns_scanner():
    from indicators.chart_patterns import scan_all_chart_patterns

    # Generate test DataFrame
    n = 120
    t = np.linspace(0, 4 * np.pi, n)
    wave = 2000.0 + 30.0 * np.sin(t)
    df = pd.DataFrame({
        "open": wave,
        "high": wave + 2.0,
        "low": wave - 2.0,
        "close": wave + 0.5,
        "volume": np.full(n, 500),
    })

    res = scan_all_chart_patterns(df, order=4)
    assert "patterns_found" in res
    assert "classical" in res
    assert "harmonic" in res
    assert isinstance(res["patterns_found"], list)


def test_seasonality_calculator():
    from analysis.calculators.seasonality import SeasonalityCalculator

    # Create 3 years of daily bars
    dates = pd.date_range(start="2022-01-01", end="2024-12-31", freq="D")
    n = len(dates)
    prices = 100.0 * np.cumprod(1 + np.random.randn(n) * 0.005)
    df = pd.DataFrame({
        "time": dates,
        "close": prices,
    })

    monthly = SeasonalityCalculator.compute_monthly_seasonality(df)
    assert "monthly_seasonality" in monthly
    assert len(monthly["monthly_seasonality"]) > 0

    dow = SeasonalityCalculator.compute_day_of_week_seasonality(df)
    assert "day_of_week_seasonality" in dow
    assert len(dow["day_of_week_seasonality"]) > 0


# ---------------------------------------------------------------------------
# 2. Skills Hub Discovery & Dynamic Injection
# ---------------------------------------------------------------------------

def test_skills_hub_discovery():
    from skills.skills_hub import SkillsHub

    hub = SkillsHub()
    total = len(hub._skills)
    assert total >= 45, f"Expected >= 45 skills, found {total}"

    # Verify the 7 newly added skills
    new_skills = [
        "intent-resolution",
        "web-research-fallback",
        "system-devops-lifecycle",
        "quant-research-workflow",
        "trading-tutor",
        "mql5-ea-builder",
        "emerging-markets-idr",
    ]
    for s in new_skills:
        skill = hub.get_skill(s)
        assert skill is not None, f"Skill '{s}' was not discovered by SkillsHub"
        assert len(skill.description) <= 80, f"Skill '{s}' description too long: {len(skill.description)}"
        assert len(skill.tags) > 0, f"Skill '{s}' has no tags"


def test_dynamic_skills_matching():
    from skills.unified_runtime import get_skills_runtime

    runtime = get_skills_runtime()

    # Query matching intent-resolution
    matched_intent = runtime.match_skills_for_prompt("tolong analisis gold gimana kondisinya")
    assert any("intent" in m or "smc" in m or "gold" in m for m in matched_intent)

    # Query matching mql5
    matched_mql = runtime.match_skills_for_prompt("tolong buatkan expert advisor mql5 robot trading mt5")
    assert "mql5-ea-builder" in matched_mql

    # Query matching emerging-markets-idr
    matched_idr = runtime.match_skills_for_prompt("bagaimana dampak kenaikan bi rate terhadap rupiah dan usdidr")
    assert "emerging-markets-idr" in matched_idr


# ---------------------------------------------------------------------------
# 3. Tool Definitions & ToolExecutor Dispatch
# ---------------------------------------------------------------------------

def test_new_tools_registration():
    from analysis.tools import tools_definitions as td

    tools_to_verify = [
        "get_pivot_points", "get_ichimoku", "scan_chart_patterns", "get_seasonality",
        "get_divergences", "get_recent_tick_flow", "export_tick_data", "get_latency_breakdown",
        "browser", "save_script", "list_saved_scripts", "run_saved_script",
        "get_indonesia_macro", "get_earnings_calendar", "search_social_sentiment"
    ]

    telegram_names = {t["name"] for t in td.TELEGRAM_TOOLS if isinstance(t, dict)}
    all_names = {t["name"] for t in td.ALL_TOOLS if isinstance(t, dict)}

    for t in tools_to_verify:
        assert t in telegram_names, f"Tool '{t}' missing from TELEGRAM_TOOLS"
        assert t in all_names, f"Tool '{t}' missing from ALL_TOOLS"


@pytest.mark.asyncio
async def test_tool_executor_dispatch():
    from analysis.tools.executor import ToolExecutor
    from config.settings import load_settings

    settings = load_settings()
    executor = ToolExecutor(None, settings=settings)

    tools_to_verify = [
        "get_pivot_points", "get_ichimoku", "scan_chart_patterns", "get_seasonality",
        "get_divergences", "get_recent_tick_flow", "export_tick_data", "get_latency_breakdown",
        "browser", "save_script", "list_saved_scripts", "run_saved_script",
        "get_indonesia_macro", "get_earnings_calendar", "search_social_sentiment"
    ]

    for t in tools_to_verify:
        found = False
        for dh in [executor.execution_handlers, executor.position_handlers, executor.macro_handlers, executor.sentiment_handlers, executor.technical_handlers]:
            if hasattr(dh, t):
                found = True
                break
        if not found and hasattr(executor, f"_tool_{t}"):
            found = True
        if not found:
            from analysis.tools.unified_registry import unified_tool_registry
            if unified_tool_registry.get_tool(t) is not None:
                found = True
        if not found:
            from analysis.tools.registry import default_tool_registry
            if default_tool_registry.get(t, settings=settings) is not None:
                found = True
        assert found, f"Tool '{t}' not dispatchable by ToolExecutor"


# ---------------------------------------------------------------------------
# 4. ChatToolRouter Coverage & Baseline Bundle
# ---------------------------------------------------------------------------

def test_chat_tool_router_routing():
    from analysis.tools.tools_definitions import TELEGRAM_TOOLS
    from telegram_bot.chat_tool_router import ChatToolRouter

    router = ChatToolRouter(TELEGRAM_TOOLS)

    test_queries = [
        ("pivot points gold hari ini", "get_pivot_points"),
        ("ichimoku cloud eurusd h4", "get_ichimoku"),
        ("pola double top xauusd", "scan_chart_patterns"),
        ("musiman bulan oktober untuk emas", "get_seasonality"),
        ("divergensi rsi usdjpy", "get_divergences"),
        ("latensi server mt5 ping", "get_latency_breakdown"),
        ("makro indonesia dan bi rate sekarang", "get_indonesia_macro"),
        ("jadwal earnings rilis apple minggu ini", "get_earnings_calendar"),
        ("sentimen twitter gold hari ini", "search_social_sentiment"),
    ]

    baseline_required = {"search_tools", "get_market_quote", "get_system_health", "get_account_info", "web_search"}

    for query, expected_tool in test_queries:
        tools = router.route_tools_for_query(query)
        tool_names = {t["name"] for t in tools}
        assert expected_tool in tool_names, f"Expected '{expected_tool}' for query '{query}', got {tool_names}"
        # Verify baseline injection
        assert baseline_required.issubset(tool_names), f"Baseline tools missing in query '{query}'"


# ---------------------------------------------------------------------------
# 5. Persistent Script Storage & Execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_saved_scripts_lifecycle():
    from analysis.tools.domain.code_execution_tool import handle_save_script, handle_list_saved_scripts, handle_run_saved_script

    # 1. Save Script
    test_script_name = "test_unit_script.py"
    code = "result = {'computed': 42 * 2}\nprint('Execution complete')"
    save_res = await handle_save_script({"script_name": test_script_name, "code": code, "description": "Unit test script"})
    assert save_res["status"] == "success"

    # 2. List Scripts
    list_res = await handle_list_saved_scripts({})
    assert list_res["status"] == "success"
    assert any(s["name"] == test_script_name for s in list_res["scripts"])

    # 3. Run Script
    run_res = await handle_run_saved_script({"script_name": test_script_name})
    assert run_res["status"] == "success"
    assert "Execution complete" in run_res["output"]

    # Clean up test script
    from pathlib import Path
    test_file = Path("data/user_scripts") / test_script_name
    if test_file.exists():
        test_file.unlink()
