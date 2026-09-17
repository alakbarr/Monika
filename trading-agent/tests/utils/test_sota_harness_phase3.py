import pytest
from unittest.mock import MagicMock, AsyncMock

from analysis.memory.reflector import TradeReflector
from utils.llm.prompt_compressor import truncate_to_budget, estimate_tokens
from analysis.tools.tool_registry import ProgressiveToolRegistry
from utils.llm.prompt_ab_test import OfflinePromptOptimizer


def test_reflector_critique_gate_platitudes():
    """Verify TradeReflector rejects generic platitudes and outcome contradictions."""
    reflector = TradeReflector()

    # 1. Platitude rejection
    bad_data = {
        "specific_lesson": "You must be more careful and follow the plan next time",
        "lesson_tags": ["sl_too_tight"],
        "outcome_process_classification": "good_process_bad_outcome"
    }
    is_valid, critique = reflector._verify_reflection_quality(bad_data, was_profitable=False)
    assert not is_valid
    assert "generic platitude" in critique

    # 2. Outcome contradiction rejection (profitable trade classified as bad outcome)
    bad_outcome = {
        "specific_lesson": "Wait for H1 ChoCH on Asian low sweep before entering",
        "lesson_tags": ["well_executed_setup"],
        "outcome_process_classification": "good_process_bad_outcome"
    }
    is_valid2, critique2 = reflector._verify_reflection_quality(bad_outcome, was_profitable=True)
    assert not is_valid2
    assert "Outcome conflict" in critique2

    # 3. Valid concrete reflection
    good_data = {
        "specific_lesson": "Wait for H1 ChoCH on Asian low sweep before entering buy setups",
        "lesson_tags": ["well_executed_setup"],
        "outcome_process_classification": "good_process_good_outcome"
    }
    is_valid3, critique3 = reflector._verify_reflection_quality(good_data, was_profitable=True)
    assert is_valid3
    assert critique3 == ""


def test_domain_aware_lossless_semantic_slicing():
    """Verify LSS preserves active unmitigated zones and prioritizes high-impact events."""
    import json
    
    # Test economic calendar prioritization
    data = {
        "symbol": "EURUSD",
        "events": [
            {"event": "Minor Retail", "impact": "LOW"},
            {"event": "Consumer Confidence", "impact": "LOW"},
            {"event": "CPI MoM", "impact": "HIGH"},
            {"event": "Core CPI", "impact": "HIGH"},
            {"event": "Housing Starts", "impact": "LOW"},
            {"event": "FOMC Rate Decision", "impact": "HIGH"},
        ]
    }
    json_text = json.dumps(data)
    # Truncate with tight budget
    truncated = truncate_to_budget(json_text, max_tokens=60)
    parsed = json.loads(truncated)
    
    event_names = [e["event"] for e in parsed["events"]]
    assert "CPI MoM" in event_names or "Core CPI" in event_names or "FOMC Rate Decision" in event_names


def test_progressive_tool_schema_pruning():
    """Verify tool registry prunes schemas for prescreen and tailors per asset class."""
    registry = ProgressiveToolRegistry()

    # 1. Prescreen tool schemas (only ~4 tools)
    prescreen_schemas = registry.get_prescreen_schemas()
    assert len(prescreen_schemas) == 4
    names = [t["name"] for t in prescreen_schemas]
    assert "get_price_history" in names
    assert "submit_asset_analysis" not in names

    # 2. Asset tailoring: Crypto gets funding rate; Forex gets bond spreads and COT
    btc_schemas = registry.get_schemas_for_asset("BTCUSD")
    btc_names = [t["name"] for t in btc_schemas]
    assert "get_funding_rate" in btc_names
    assert "get_bond_yield_spreads" not in btc_names

    eur_schemas = registry.get_schemas_for_asset("EURUSD")
    eur_names = [t["name"] for t in eur_schemas]
    assert "get_bond_yield_spreads" in eur_names
    assert "get_funding_rate" not in eur_names


def test_offline_prompt_optimizer_scoring_and_champion():
    """Verify OfflinePromptOptimizer scores variants and identifies statistically sound champions."""
    optimizer = OfflinePromptOptimizer()

    control_trades = [
        {"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 15.0}, {"pnl": -8.0}, {"pnl": 12.0},
        {"pnl": -10.0}, {"pnl": 20.0}, {"pnl": -5.0}, {"pnl": 5.0}, {"pnl": -10.0}
    ]  # 6 wins, 4 losses -> 60% WR

    treatment_trades = [
        {"pnl": 25.0}, {"pnl": 20.0}, {"pnl": -5.0}, {"pnl": 15.0}, {"pnl": 30.0},
        {"pnl": 12.0}, {"pnl": -10.0}, {"pnl": 18.0}, {"pnl": 22.0}, {"pnl": -5.0}
    ]  # 7 wins, 3 losses -> 70% WR

    score_a = optimizer.score_variant_performance("A", control_trades)
    score_b = optimizer.score_variant_performance("B", treatment_trades)

    assert score_a["win_rate"] == 50.0
    assert score_b["win_rate"] == 70.0

    scores = {"A": score_a, "B": score_b}
    champion, is_promotable = optimizer.select_champion(scores, min_win_rate_delta=5.0)

    assert champion == "B"
    assert is_promotable is True
