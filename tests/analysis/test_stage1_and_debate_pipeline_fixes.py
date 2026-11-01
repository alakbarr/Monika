import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.prefetch.stage1_prefetcher import Stage1DataBundler
from monika.application.analysis.tools.mixins.brief_submission import (
    _FX_BASE_QUOTE,
    reconcile_fx_pair_macro_matrix,
    sanitize_macro_regime,
)
from monika.application.graph.nodes.debate.debate_judge_node import debate_judge_node
from monika.application.graph.nodes.debate.rebuttal_node import rebuttal_node
from monika.infrastructure.llm.prompt_compressor import PROTECTED_KEYS, truncate_to_budget
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_stage1_cross_asset_momentum_matrix_populates_1d_and_5d_pct():
    session = create_mock_async_session()
    with patch("monika.application.analysis.prefetch.stage1_prefetcher.ToolExecutor") as mock_exec_cls:
        executor_inst = mock_exec_cls.return_value

        async def _fake_execute(tool_name: str, args: dict) -> dict:
            assert tool_name == "get_price_momentum"
            sym = args["symbol"]
            lb = args.get("lookback_bars")
            if lb == 6:
                return {"symbol": sym, "pct_change": 0.45, "direction": "bullish"}
            if lb == 30:
                return {"symbol": sym, "pct_change": -1.25, "direction": "bearish"}
            return {"symbol": sym, "pct_change": 0.10, "direction": "flat"}

        executor_inst.execute = AsyncMock(side_effect=_fake_execute)
        bundler = Stage1DataBundler(session, {})
        matrix = await bundler._fetch_cross_asset_momentum_matrix(
            existing_eurusd={"symbol": "EURUSD", "pct_change": -0.80, "direction": "bearish"}
        )

        assert set(matrix.keys()) == set(Stage1DataBundler.CROSS_ASSET_MOMENTUM_SYMBOLS)
        for sym, entry in matrix.items():
            assert entry["change_1d_pct"] == 0.45
            assert entry["change_5d_pct"] == -1.25
            assert entry["trend"] == "bearish"
            assert entry["direction"] == "bearish"

        terminal = bundler._synthesize_tier1_terminal({"cross_asset_momentum": matrix})
        matrix_str = terminal["cross_asset_momentum_matrix"]
        assert "N/A%" not in matrix_str
        assert "EURUSD: change_1d_pct=0.45% | change_5d_pct=-1.25% | trend=bearish" in matrix_str
        assert "USDJPY: change_1d_pct=0.45% | change_5d_pct=-1.25% | trend=bearish" in matrix_str


def test_stage1_tier1_terminal_falls_back_to_pct_change():
    session = create_mock_async_session()
    bundler = Stage1DataBundler(session, {})
    terminal = bundler._synthesize_tier1_terminal(
        {
            "cross_asset_momentum": {
                "EURUSD": {"pct_change": 0.62, "direction": "bullish"},
                "USDJPY": {"pct_change": -0.38, "direction": "bearish"},
            }
        }
    )
    matrix_str = terminal["cross_asset_momentum_matrix"]
    assert "N/A%" not in matrix_str
    assert "EURUSD: change_1d_pct=0.62% | change_5d_pct=0.62% | trend=bullish" in matrix_str
    assert "USDJPY: change_1d_pct=-0.38% | change_5d_pct=-0.38% | trend=bearish" in matrix_str


def test_prompt_compressor_protects_stage1_terminal_and_momentum_keys():
    assert "_tier1_executive_macro_terminal" in PROTECTED_KEYS
    assert "cross_asset_momentum" in PROTECTED_KEYS
    assert "cross_asset_momentum_matrix" in PROTECTED_KEYS

    payload = {
        "_tier1_executive_macro_terminal": {
            "cross_asset_momentum_matrix": "EURUSD: change_1d_pct=0.55% | change_5d_pct=-0.10% | trend=bullish"
        },
        "cross_asset_momentum": {"EURUSD": {"change_1d_pct": 0.55, "change_5d_pct": -0.10}},
        "unimportant_noise": [{"idx": i, "blob": "x" * 200} for i in range(40)],
    }
    compressed_str = truncate_to_budget(json.dumps(payload), max_tokens=400)
    parsed = json.loads(compressed_str)
    assert "_tier1_executive_macro_terminal" in parsed
    assert "cross_asset_momentum" in parsed


def test_reconcile_fx_pair_macro_matrix_handles_neutral_legs_and_xauusd():
    assert "XAUUSD" in _FX_BASE_QUOTE
    assert _FX_BASE_QUOTE["XAUUSD"] == ("XAU", "USD")

    currency_biases = {
        "USD": "bullish",
        "JPY": "neutral",
        "EUR": "neutral",
        "GBP": "bearish",
        "XAU": "bearish",
    }
    raw_matrix = {
        "USDJPY": {"directional_bias": "bearish", "key_driver": "BoJ rate hike speculation"},
        "EURUSD": {"directional_bias": "bullish", "key_driver": "ECB hold"},
        "GBPUSD": {"directional_bias": "neutral", "key_driver": "UK gilts"},
        "XAUUSD": {"directional_bias": "bullish", "key_driver": "Geopolitical bid"},
    }

    reconciled = reconcile_fx_pair_macro_matrix(currency_biases, raw_matrix)
    assert reconciled["USDJPY"]["directional_bias"] == "bullish"
    assert "[AUTO-RECONCILED: USD=bullish vs JPY=neutral -> USDJPY=bullish]" in reconciled["USDJPY"]["key_driver"]

    assert reconciled["EURUSD"]["directional_bias"] == "bearish"
    assert "[AUTO-RECONCILED: EUR=neutral vs USD=bullish -> EURUSD=bearish]" in reconciled["EURUSD"]["key_driver"]

    assert reconciled["GBPUSD"]["directional_bias"] == "bearish"
    assert "[AUTO-RECONCILED: GBP=bearish vs USD=bullish -> GBPUSD=bearish]" in reconciled["GBPUSD"]["key_driver"]

    assert reconciled["XAUUSD"]["directional_bias"] == "bearish"
    assert "[AUTO-RECONCILED: XAU=bearish vs USD=bullish -> XAUUSD=bearish]" in reconciled["XAUUSD"]["key_driver"]

    assert sanitize_macro_regime(",") == "transition"
    assert sanitize_macro_regime(" ,.;:-_\"' ") == "transition"


@pytest.mark.asyncio
async def test_rebuttal_node_runs_both_bull_and_bear_rebuttals_on_wait():
    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "wait"})],
        "debate_states": {
            "EURUSD": {
                "needs_rebuttal": True,
                "verified_bull_claim": {"thesis": "Long discount OB 1.0850", "strength_score": 8},
                "bear_dissent": {"bear_dissent": "Short supply zone 1.0850", "risk_severity": 8},
                "original_context": {"decision": "wait", "entry_price": 1.0850},
                "fact_sheet": {"symbol": "EURUSD", "price": 1.0850},
                "curr_p": 1.0850,
                "turn": 1,
            }
        },
    }
    config = {
        "configurable": {
            "scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True, "debate_rounds": 2}})
        }
    }

    with (
        patch(
            "monika.application.graph.nodes.debate.rebuttal_node.generate_bull_rebuttal",
            AsyncMock(return_value={"rebuttal": "Bull defense at 1.0850", "rebuttal_strength": 8}),
        ) as mock_bull_reb,
        patch(
            "monika.application.graph.nodes.debate.rebuttal_node.generate_bear_rebuttal",
            AsyncMock(return_value={"rebuttal": "Bear defense at 1.0850", "rebuttal_strength": 7}),
        ) as mock_bear_reb,
    ):
        res = await rebuttal_node(state, config)
        mock_bull_reb.assert_awaited_once()
        mock_bear_reb.assert_awaited_once()
        deb = res["debate_states"]["EURUSD"]
        assert deb["bull_rebuttal"]["rebuttal"] == "Bull defense at 1.0850"
        assert deb["bear_rebuttal"]["rebuttal"] == "Bear defense at 1.0850"
        assert deb["rebuttal"]["rebuttal_strength"] == 8


@pytest.mark.asyncio
async def test_investment_judge_does_not_override_conflict_wait_verdict_to_avoid_when_opposing_score_is_9():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(
        return_value={
            "final_decision": "sell",
            "reason": "Bear short setup in premium zone has superior structure",
            "risk_multiplier": 0.80,
            "adjusted_entry": 1.0900,
            "adjusted_sl": 1.0950,
            "adjusted_tp": 1.0800,
        }
    )

    verdict_sell = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "wait", "market_regime": "trending"},
        bull_claim={"strength_score": 9, "proposed_entry": 1.0900, "proposed_sl": 1.0850, "proposed_tp": 1.1000},
        bear_dissent={"risk_severity": 8, "proposed_entry": 1.0900, "proposed_sl": 1.0950, "proposed_tp": 1.0800},
    )
    assert verdict_sell["final_decision"] == "sell"
    assert verdict_sell["risk_multiplier"] == 0.80

    mock_client.classify_json = AsyncMock(
        return_value={
            "final_decision": "buy",
            "reason": "Bull long setup in discount zone has superior structure",
            "risk_multiplier": 0.75,
            "adjusted_entry": 1.0850,
            "adjusted_sl": 1.0800,
            "adjusted_tp": 1.0950,
        }
    )
    verdict_buy = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "wait", "market_regime": "trending"},
        bull_claim={"strength_score": 8, "proposed_entry": 1.0850, "proposed_sl": 1.0800, "proposed_tp": 1.0950},
        bear_dissent={"risk_severity": 9, "proposed_entry": 1.0850, "proposed_sl": 1.0900, "proposed_tp": 1.0750},
    )
    assert verdict_buy["final_decision"] == "buy"
    assert verdict_buy["risk_multiplier"] == 0.75


@pytest.mark.asyncio
async def test_debate_judge_node_hydrates_confluence_score_when_upgrading_wait_to_buy_or_sell():
    mock_ana = MagicMock()
    mock_ana.id = 555
    mock_ana.symbol = "USDJPY"
    mock_ana.decision = "wait"
    mock_ana.confluence_score = None
    mock_ana.confidence = 0.50
    mock_ana.entry_zone = json.dumps({"price": 155.00})
    mock_ana.stop_loss = None
    mock_ana.take_profit = None
    mock_ana.price_at_analysis = 155.00
    mock_ana.risk_multiplier = 1.0
    mock_ana.timeframe = "H1"
    mock_ana.was_debate_modified = False

    class _MockSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, model, pk):
            return mock_ana

        def add(self, obj):
            pass

        async def commit(self):
            pass

    state = {
        "actionable_trades": [("USDJPY", {"analysis_id": 555, "decision": "wait"})],
        "precomputed_confluence": {"USDJPY": {"buy_score": 9, "sell_score": 7}},
        "debate_states": {
            "USDJPY": {
                "verified_bull_claim": {
                    "strength_score": 8,
                    "proposed_entry": 155.00,
                    "proposed_sl": 154.20,
                    "proposed_tp": 156.50,
                },
                "bear_dissent": {"risk_severity": 5},
                "original_context": {"decision": "wait", "price_at_analysis": 155.00},
                "fact_sheet": {"symbol": "USDJPY", "atr": 0.50},
                "curr_p": 155.00,
            }
        },
        "investment_verdicts": {},
        "summary": {},
    }
    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}

    with (
        patch("monika.application.graph.nodes.debate.debate_judge_node.get_session", side_effect=_MockSession),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.evaluate_debate",
            AsyncMock(
                return_value={
                    "final_decision": "buy",
                    "confidence": 0.80,
                    "risk_multiplier": 0.85,
                    "reason": "Upgraded WAIT to BUY on strong carry + discount OB",
                }
            ),
        ),
        patch(
            "monika.application.graph.nodes.debate.debate_judge_node.validate_and_apply_judge_adjustments",
            AsyncMock(return_value=(True, None)),
        ),
    ):
        res = await debate_judge_node(state, config)
        assert len(res["actionable_trades"]) == 1
        assert mock_ana.decision == "buy"
        assert mock_ana.confluence_score == 9
        _, trade_dict = res["actionable_trades"][0]
        assert trade_dict["confluence_score"] == 9
