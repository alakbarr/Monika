"""
Unit tests for Bulletproof Agent Harness, Benchmark Fixture Dispatcher,
and Fundamental Stage Recovery.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from analysis.schemas.pydantic_schemas import SubmitFundamentalBriefSchema
from analysis.stages.fundamental_stage_recovery import recover_fundamental_brief_from_text
from benchmark.db_access import BenchmarkFixtureDispatcher, guarded_tool_executor
from analysis.tools.tool_executor import ToolExecutor
from analysis.tools.tools_definitions import STAGE1_TOOLS
from analysis.prefetch.stage1_prefetcher import CORE_STAGE1_PREFETCH_TOOLS, prune_stage1_tools


def test_fundamental_brief_schema_auto_healing():
    """Verify that SubmitFundamentalBriefSchema auto-heals missing auxiliary fields."""
    raw = {
        "macro_regime": "HAWKISH_PLATEAU_WITH_GEOPOLITICAL_FRICTION",
        "market_sentiment": "RISK_OFF",
        "currency_bias": {
            "USD": "BULLISH",
            "EUR": "BEARISH",
            "GBP": "NEUTRAL",
            "JPY": "BULLISH",
            "AUD": "BEARISH",
            "XAU": "BULLISH",
            "XTI": "BULLISH",
            "BTC": "NEUTRAL",
        },
        "confidence": 0.85,
        "key_drivers": ["US labor resiliency", "Middle East tensions"],
        "narrative": "DXY trades at 101.48 while VIX remains at 16.7 under elevated geopolitical risk.",
        # Omitted: key_data_points_used, dxy_context, vix_context, strongest_counter_thesis, invalidation_conditions
    }

    brief = SubmitFundamentalBriefSchema.model_validate(raw)
    assert brief.macro_regime.value in ("risk_off", "mixed")
    assert brief.currency_bias["USD"] == "bullish"
    assert brief.key_data_points_used.vix_close == 16.7
    assert len(brief.key_drivers) == 2
    assert len(brief.strongest_counter_thesis) >= 50
    assert all(len(cond) >= 40 for cond in brief.invalidation_conditions.values())


def test_fundamental_stage_recovery_from_text():
    """Verify that recover_fundamental_brief_from_text extracts structured brief from markdown text."""
    sample_text = """
    ## Macro Analysis & Synthesis
    Macro Regime: Risk-Off / Geopolitical Friction
    Market Sentiment: Risk-Off
    Confidence: 0.80

    ### Currency Biases
    - USD: BULLISH (Safe haven flows and high yields)
    - EUR: BEARISH (Stagflation and energy drag)
    - GBP: NEUTRAL (Stagnant growth vs inflation)
    - JPY: BULLISH (Unwinding carry trade)
    - AUD: BEARISH (China weakness)
    - XAU: BULLISH (Record safe-haven bid)
    - XTI: BULLISH (Middle East supply disruption)
    - BTC: NEUTRAL (Consolidation)

    DXY is currently at 101.50 and VIX is 16.8.
    Key drivers include US labor market softness and Middle East war risks.
    """

    recovered = recover_fundamental_brief_from_text(sample_text)
    assert recovered is not None
    assert recovered["macro_regime"].lower() in ("risk_off", "hawkish_plateau_with_geopolitical_friction", "neutral")
    assert recovered["risk_sentiment"] == "risk-off"
    assert recovered["currency_bias"]["USD"] == "bullish"
    assert recovered["currency_bias"]["EUR"] == "bearish"
    assert recovered["currency_bias"]["XAU"] == "bullish"
    assert recovered["confidence"] >= 0.50
    assert len(recovered["key_drivers"]) >= 1


def test_benchmark_fixture_dispatcher():
    """Verify that BenchmarkFixtureDispatcher serves Stage 1 read tools deterministically."""
    # Calendar
    cal = BenchmarkFixtureDispatcher.dispatch("get_economic_calendar", {"currency_filter": "USD"})
    assert cal["status"] == "success"
    assert isinstance(cal.get("events"), list)

    # Interest rates
    rates = BenchmarkFixtureDispatcher.dispatch("get_interest_rates", {})
    assert rates["status"] == "success"
    rate_list = rates.get("interest_rates", [])
    cbs = {r.get("central_bank") for r in rate_list}
    assert "FED" in cbs
    assert "ECB" in cbs
    assert "BOE" in cbs
    assert "BOJ" in cbs
    assert "RBA" in cbs

    # Treasury yields
    yields = BenchmarkFixtureDispatcher.dispatch("get_treasury_yields", {})
    assert yields["status"] == "success"
    assert yields["data"]["us10y"] == 3.82

    # Web search
    search = BenchmarkFixtureDispatcher.dispatch("web_search", {"query": "US NFP rate cut"})
    assert search["status"] == "success"
    assert len(search["results"]) > 0

    # Quotes
    quote = BenchmarkFixtureDispatcher.dispatch("get_market_quote", {"symbol": "XAUUSD"})
    assert quote["status"] == "success"
    assert quote["price"] == 2658.50


@pytest.mark.asyncio
async def test_guarded_tool_executor_context():
    """Verify guarded_tool_executor intercepts read tools and submission tools in memory."""
    with guarded_tool_executor() as box:
        executor = ToolExecutor(session=None, settings={})

        # Test read tool dispatch
        res_read = await executor.execute("get_interest_rates", {})
        assert res_read["status"] == "success"
        assert len(res_read.get("interest_rates", [])) >= 5

        # Test write tool capture
        brief_payload = {
            "macro_regime": "HAWKISH_PLATEAU_WITH_GEOPOLITICAL_FRICTION",
            "market_sentiment": "RISK_OFF",
            "currency_bias": {
                "USD": "BULLISH", "EUR": "BEARISH", "GBP": "NEUTRAL", "JPY": "BULLISH",
                "AUD": "BEARISH", "XAU": "BULLISH", "XTI": "BULLISH", "BTC": "NEUTRAL"
            },
            "confidence": 0.85,
            "key_drivers": ["US labor resiliency", "Middle East tensions"],
            "narrative": "DXY trades at 101.48 while VIX is 16.7.",
        }
        res_write = await executor.execute("submit_fundamental_brief", brief_payload)
        assert res_write["status"] == "saved"
        assert box.get("result") is not None
        assert box["result"]["tool"] == "submit_fundamental_brief"
        assert box["result"]["payload"]["macro_regime"] in ("risk_off", "mixed")


def test_prune_stage1_tools_healthy_prefetch():
    """Verify that 100% healthy prefetch prunes all read tools and leaves only submit_fundamental_brief."""
    healthy_satisfied = set(CORE_STAGE1_PREFETCH_TOOLS) | {
        "get_interest_rates",
        "get_bond_yield_spreads",
        "get_central_bank_expectations",
        "get_precomputed_cot_signals",
        "get_surprise_summary",
        "get_price_momentum",
        "get_funding_rate",
        "get_market_session",
    }
    pruned = prune_stage1_tools(STAGE1_TOOLS, healthy_satisfied)
    names = [t["name"] for t in pruned]
    assert names == ["submit_fundamental_brief"]


def test_prune_stage1_tools_partial_prefetch_failure():
    """Verify that if a core indicator (e.g. yields) fails prefetch, it is preserved as an operational fallback."""
    partial_satisfied = (set(CORE_STAGE1_PREFETCH_TOOLS) - {"get_treasury_yields"}) | {
        "get_vix",
        "get_dxy",
        "get_news_digest",
    }
    pruned = prune_stage1_tools(STAGE1_TOOLS, partial_satisfied)
    names = [t["name"] for t in pruned]
    assert "submit_fundamental_brief" in names
    assert "get_treasury_yields" in names
    # Tools that were satisfied should NOT be present
    assert "get_vix" not in names
    assert "get_dxy" not in names


def test_prune_stage1_tools_zero_prefetch_fallback():
    """Verify that zero prefetch preserves all base tools untouched."""
    pruned = prune_stage1_tools(STAGE1_TOOLS, set())
    assert len(pruned) == len(STAGE1_TOOLS)
    names = [t["name"] for t in pruned]
    assert "submit_fundamental_brief" in names
    assert "get_treasury_yields" in names
    assert "get_vix" in names

