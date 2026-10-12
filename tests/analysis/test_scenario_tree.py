import pytest
import json
from analysis.scenario_tree import ScenarioTreeEngine, ScenarioTree, ScenarioNode


def test_scenario_tree_generation_bullish():
    engine = ScenarioTreeEngine(settings={"scenario_tree": {"ev_threshold": 0.5, "min_dominant_prob": 0.40}})
    tree = engine.create_deterministic_tree(
        symbol="EURUSD",
        current_price=1.0850,
        d1_trend="BULLISH",
        atr_14=0.0050,
        macro_bias="BULLISH"
    )
    assert tree.symbol == "EURUSD"
    assert "bull" in tree.branches
    assert "bear" in tree.branches
    assert "chop" in tree.branches
    assert tree.branches["bull"].probability >= tree.branches["bear"].probability
    assert tree.final_decision == "BUY"
    assert tree.expected_value > 0


def test_scenario_tree_jsonl_serialization():
    engine = ScenarioTreeEngine()
    tree = engine.create_deterministic_tree(
        symbol="XAUUSD",
        current_price=2650.0,
        d1_trend="BEARISH",
        atr_14=15.0,
        macro_bias="BEARISH"
    )
    jsonl_output = tree.serialize_jsonl()
    lines = jsonl_output.strip().split("\n")
    # Must have 5 lines: root, bull, bear, chop, convergence
    assert len(lines) == 5
    for line in lines:
        node = json.loads(line)
        assert "uuid" in node
        assert "node_type" in node
        assert node["symbol"] == "XAUUSD"


def test_stage2_bundle_price_extraction_robustness():
    """Verify that Stage2DataBundler timeframe-suffixed keys successfully extract current price."""
    raw_bundle_data = {
        "get_technical_indicators_H4": {"indicators": {"close": 2655.20}},
        "get_technical_indicators_D1": {"indicators": {"close": 2640.00}},
        "get_price_history_H4": {"bars": [{"close": 2655.20}]}
    }
    cur_p = 0.0
    for k in ("get_technical_indicators_H4", "get_technical_indicators_D1", "get_technical_indicators_H1", "get_technical_indicators"):
        t_val = raw_bundle_data.get(k)
        if isinstance(t_val, dict):
            ind = t_val.get("indicators", t_val)
            if isinstance(ind, dict) and (ind.get("close") or ind.get("price")):
                cur_p = float(ind.get("close") or ind.get("price"))
                break
    assert cur_p == 2655.20
    engine = ScenarioTreeEngine()
    tree = engine.create_deterministic_tree(
        symbol="XAUUSD",
        current_price=cur_p,
        d1_trend="BULLISH",
        macro_bias="BULLISH"
    )
    assert tree.expected_value != 0.0
