import pytest
from unittest.mock import MagicMock
from graph.nodes.state_pruner import (
    prune_after_fundamental,
    prune_after_debate,
    prune_before_execution,
)
from graph.workflow import build_trading_graph


def test_prune_after_fundamental_cleans_raw_conversations():
    state = {
        "summary": {
            "fundamental": {
                "macro_bias": "bullish",
                "conviction": 0.85,
                "raw_conversation": [{"role": "assistant", "content": "long verbose monologue" * 50}],
                "raw_tool_observations": {"scraper": "1000 lines of raw web text"},
                "intermediate_scratchpad": "scratch notes",
                "tool_call_history": ["call_1", "call_2"],
                "raw_prompt": "Huge prompt text...",
                "raw_llm_response": "Raw response string...",
                "unfiltered_headlines": ["headline 1", "headline 2"],
            }
        }
    }

    result = prune_after_fundamental(state)
    fund = result["summary"]["fundamental"]

    # Preserved fields
    assert fund["macro_bias"] == "bullish"
    assert fund["conviction"] == 0.85

    # Pruned verbose fields
    for verbose_key in [
        "raw_conversation",
        "raw_tool_observations",
        "intermediate_scratchpad",
        "tool_call_history",
        "raw_prompt",
        "raw_llm_response",
        "unfiltered_headlines",
    ]:
        assert verbose_key not in fund


def test_prune_after_debate_cleans_transcripts_and_heavy_payloads():
    state = {
        "debate_states": {
            "EURUSD": {
                "consensus": "buy",
                "revised_target": 1.0950,
                "raw_bull_text": "Bull argument turn 1..." * 20,
                "raw_bear_text": "Bear dissent turn 1..." * 20,
                "raw_judge_text": "Judge rationale draft..." * 20,
                "intermediate_dialogue": [{"speaker": "bull", "text": "arg"}],
                "transcript": "Full debate transcript...",
                "dialogue_history": ["turn 1", "turn 2"],
            }
        },
        "asset_analyses": {
            "EURUSD": {
                "decision": "buy",
                "confidence": 0.8,
                "raw_candles": [{"open": 1.08, "close": 1.09}] * 500,
                "raw_order_flow": {"bids": [1.08] * 100},
                "chart_svg": "<svg>huge svg chart</svg>",
                "raw_screener_output": "massive string dump",
                "raw_tool_history": ["get_ohlcv", "calc_rsi"],
                "intermediate_reasoning": "step by step thoughts",
            }
        },
        "risk_debate_states": {
            "EURUSD": {
                "approved_lot": 0.5,
                "raw_conservative_text": "too risky...",
                "raw_aggressive_text": "send it!",
                "raw_neutral_text": "balanced",
                "intermediate_dialogue": ["arg1", "arg2"],
            }
        },
    }

    result = prune_after_debate(state)
    ds = result["debate_states"]["EURUSD"]
    aa = result["asset_analyses"]["EURUSD"]
    rds = result["risk_debate_states"]["EURUSD"]

    # Preserved
    assert ds["consensus"] == "buy"
    assert ds["revised_target"] == 1.0950
    assert aa["decision"] == "buy"
    assert aa["confidence"] == 0.8
    assert rds["approved_lot"] == 0.5

    # Dialogue turns pruned
    for key in ["raw_bull_text", "raw_bear_text", "raw_judge_text", "intermediate_dialogue", "transcript", "dialogue_history"]:
        assert key not in ds

    # Heavy asset analysis payloads pruned
    for heavy in ["raw_candles", "raw_order_flow", "chart_svg", "raw_screener_output", "raw_tool_history", "intermediate_reasoning"]:
        assert heavy not in aa

    # Risk dialogue turns pruned
    for key in ["raw_conservative_text", "raw_aggressive_text", "raw_neutral_text", "intermediate_dialogue"]:
        assert key not in rds


def test_prune_before_execution_strips_heavy_data_from_trades():
    state = {
        "actionable_trades": [
            {
                "symbol": "EURUSD",
                "action": "BUY",
                "volume": 0.1,
                "full_history": [{"time": 1, "price": 1.08}] * 1000,
                "raw_chart_base64": "base64data" * 500,
                "all_candles": [1.08, 1.09, 1.10],
                "raw_indicators_df": "mock_df_dump",
                "raw_mt5_ticks": [1, 2, 3],
                "deep_analysis_dump": "dump",
            },
            (
                "GBPUSD",
                {
                    "symbol": "GBPUSD",
                    "action": "SELL",
                    "volume": 0.2,
                    "raw_chart_base64": "base64data",
                    "all_candles": [1.25, 1.26],
                },
            ),
        ]
    }

    result = prune_before_execution(state)
    clean_trades = result["actionable_trades"]

    assert len(clean_trades) == 2
    # Dict trade
    t1 = clean_trades[0]
    assert t1["symbol"] == "EURUSD"
    assert t1["action"] == "BUY"
    for heavy in ("full_history", "raw_chart_base64", "all_candles", "raw_indicators_df", "raw_mt5_ticks", "deep_analysis_dump"):
        assert heavy not in t1

    # Tuple trade
    sym, t2 = clean_trades[1]
    assert sym == "GBPUSD"
    assert t2["symbol"] == "GBPUSD"
    assert "raw_chart_base64" not in t2
    assert "all_candles" not in t2


def test_workflow_has_prune_execution_node():
    graph = build_trading_graph()
    assert "prune_execution" in graph.nodes
    assert "prune_fundamental" in graph.nodes
    assert "prune_debate" in graph.nodes
    assert "execution" in graph.nodes
