"""Unit tests for Multi-Agent Debate Cache Invariance (Commit 5).

Verifies:
1. Segment A prefix between Bull, Bear, and Judge is 100% byte-identical.
2. Debate ledger serialization preserves chronological order across turns (bull_claim before bear_dissent before bull_rebuttal).
3. Rebuttal round does not mutate original_context prefix.
4. Adjudication verifier system prompt is padded with anchor and passes task_role.
5. Debate judge node explicitly passes fact_sheet to evaluate_debate.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.analysis.debate.bear_analyst import generate_bear_dissent
from monika.application.analysis.debate.bull_analyst import generate_bull_advocacy
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.validators.adjudication_verifier import verify_adjudication
from monika.application.graph.nodes.debate.bear_dissent_node import bear_dissent_node
from monika.application.graph.nodes.debate.debate_judge_node import debate_judge_node
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager


def test_debate_ledger_chronological_ordering():
    """Debate ledger serialization must preserve chronological order across turns.

    bull_claim -> bear_dissent -> bull_rebuttal -> bear_rebuttal -> any other keys.
    Alphabetical sorting must NOT scramble this order.
    """
    append_ledger = {
        "bear_rebuttal": {"thesis": "bear_rebuttal"},
        "bull_rebuttal": {"thesis": "bull_rebuttal"},
        "bear_dissent": {"thesis": "bear_dissent"},
        "bull_claim": {"thesis": "bull_claim"},
        "custom_key": "custom_val",
    }
    msg = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet={"sym": "EURUSD", "atr": 0.0020},
        original_context={"decision": "BUY", "entry": 1.0850},
        append_ledger=append_ledger,
        task_directive="Evaluate debate",
    )

    pos_bull_claim = msg.find('"bull_claim"')
    pos_bear_dissent = msg.find('"bear_dissent"')
    pos_bull_rebuttal = msg.find('"bull_rebuttal"')
    pos_bear_rebuttal = msg.find('"bear_rebuttal"')
    pos_custom = msg.find('"custom_key"')

    assert pos_bull_claim != -1, "bull_claim missing from ledger"
    assert pos_bear_dissent != -1, "bear_dissent missing from ledger"
    assert pos_bull_rebuttal != -1, "bull_rebuttal missing from ledger"
    assert pos_bear_rebuttal != -1, "bear_rebuttal missing from ledger"
    assert pos_custom != -1, "custom_key missing from ledger"

    assert pos_bull_claim < pos_bear_dissent < pos_bull_rebuttal < pos_bear_rebuttal < pos_custom, (
        f"Chronological order violated: {pos_bull_claim=}, {pos_bear_dissent=}, {pos_bull_rebuttal=}, {pos_bear_rebuttal=}, {pos_custom=}"
    )


@pytest.mark.asyncio
async def test_segment_a_prefix_identical_bull_bear_judge():
    """Segment A prefix (before Tier 2 breakpoint) must be 100% byte-identical across Bull, Bear, and Judge."""
    fact_sheet = {
        "symbol": "EURUSD",
        "current_price": 1.0850,
        "atr_14": 0.0035,
        "vix": 16.5,
        "specialist_reliability": {"technical": 0.9, "macro": 0.8},
    }
    original_context = {
        "symbol": "EURUSD",
        "decision": "BUY",
        "entry": 1.0850,
        "sl": 1.0800,
        "tp": 1.0950,
    }
    bull_claim = {"strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]}
    bear_dissent = {"risk_severity": 6, "evidence_cited": ["1.0850", "1.0800"]}

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value='{"bull_thesis": "support", "strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]}'
    )
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096

    # 1. Bull Advocacy
    await generate_bull_advocacy(mock_client, "EURUSD", original_context, fact_sheet)
    bull_msg = mock_client.generate_content.call_args[1]["user_message"]

    # 2. Bear Dissent
    mock_client.generate_content.return_value = (
        '{"bear_dissent": "resistance", "risk_severity": 6, "evidence_cited": ["1.0850", "1.0800"]}'
    )
    await generate_bear_dissent(mock_client, "EURUSD", original_context, bull_claim, fact_sheet)
    bear_msg = mock_client.generate_content.call_args[1]["user_message"]

    # 3. Judge Evaluation with fact_sheet passed explicitly
    mock_client.generate_content.return_value = '{"final_decision": "buy", "reason": "strong", "risk_multiplier": 1.0}'
    await evaluate_debate(
        mock_client,
        "EURUSD",
        original_context,
        bull_claim,
        bear_dissent,
        fact_sheet=fact_sheet,
    )
    judge_msg = mock_client.generate_content.call_args[1]["user_message"]

    split_marker = "=== TIER 2 CYCLE CACHE BREAKPOINT ==="
    assert split_marker in bull_msg
    assert split_marker in bear_msg
    assert split_marker in judge_msg

    prefix_bull = bull_msg.split(split_marker)[0]
    prefix_bear = bear_msg.split(split_marker)[0]
    prefix_judge = judge_msg.split(split_marker)[0]

    assert prefix_bull == prefix_bear, "Bull and Bear Segment A prefix mismatch"
    assert prefix_bear == prefix_judge, "Bear and Judge Segment A prefix mismatch"


@pytest.mark.asyncio
async def test_debate_judge_node_passes_fact_sheet_to_evaluate_debate():
    """debate_judge_node must pass fact_sheet=deb.get('fact_sheet') to evaluate_debate."""
    state = {
        "actionable_trades": [("EURUSD", {"direction": "BUY", "analysis_id": 1})],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]},
                "bear_dissent": {"risk_severity": 5, "evidence_cited": ["1.0850", "1.0800"]},
                "original_context": {"symbol": "EURUSD", "decision": "BUY", "entry": 1.0850},
                "fact_sheet": {"symbol": "EURUSD", "vix": 16.5, "atr_14": 0.0030},
                "analysis_id": 1,
            }
        },
    }

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"agent_architecture": {"enable_debate": True}}
    config = {"configurable": {"scheduler": mock_scheduler}}

    with patch(
        "monika.application.graph.nodes.debate.debate_judge_node.evaluate_debate",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.return_value = {"final_decision": "buy", "reason": "ok", "risk_multiplier": 1.0}
        with patch("monika.application.graph.nodes.debate.debate_judge_node.get_session"):
            with patch("monika.application.graph.nodes.debate.debate_judge_node.get_client_for_task"):
                await debate_judge_node(state, config)

        assert mock_eval.called, "evaluate_debate was not called"
        call_kwargs = mock_eval.call_args[1]
        assert "fact_sheet" in call_kwargs, "fact_sheet was NOT passed to evaluate_debate"
        assert call_kwargs["fact_sheet"] == {
            "symbol": "EURUSD",
            "vix": 16.5,
            "atr_14": 0.0030,
        }, "fact_sheet passed to evaluate_debate does not match deb['fact_sheet']"


@pytest.mark.asyncio
async def test_rebuttal_round_does_not_mutate_original_context_prefix():
    """In Round 2, bull_rebuttal must go into append_ledger (Segment B), not original_context (Segment A)."""
    fact_sheet = {"symbol": "EURUSD", "current_price": 1.0850, "atr_14": 0.0035}
    original_context = {"symbol": "EURUSD", "decision": "BUY", "entry": 1.0850, "sl": 1.0800, "tp": 1.0950}
    bull_claim = {"strength_score": 8, "evidence_cited": ["1.0850"]}
    rebuttal_claim = {"rebuttal_strength": 7, "rebuttal_evidence": ["1.0850"]}

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value='{"bear_dissent": "challenge", "risk_severity": 6, "evidence_cited": ["1.0850", "1.0800"]}'
    )
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096

    # Round 1: normal bear dissent
    await generate_bear_dissent(mock_client, "EURUSD", original_context, bull_claim, fact_sheet)
    msg_r1 = mock_client.generate_content.call_args[1]["user_message"]

    # Round 2: bear dissent with rebuttal
    await generate_bear_dissent(
        mock_client,
        "EURUSD",
        original_context,
        bull_claim,
        fact_sheet,
        rebuttal=rebuttal_claim,
    )
    msg_r2 = mock_client.generate_content.call_args[1]["user_message"]

    split_marker = "=== TIER 2 CYCLE CACHE BREAKPOINT ==="
    prefix_r1 = msg_r1.split(split_marker)[0]
    prefix_r2 = msg_r2.split(split_marker)[0]

    # Segment A MUST be byte-for-byte identical between Round 1 and Round 2
    assert prefix_r1 == prefix_r2, "Round 2 modified Segment A prefix!"

    # Segment B of Round 2 MUST contain bull_rebuttal
    assert "bull_rebuttal" not in prefix_r2, "bull_rebuttal leaked into Segment A!"
    suffix_r2 = msg_r2.split(split_marker)[1]
    assert "bull_rebuttal" in suffix_r2, "bull_rebuttal not found in Segment B ledger!"


@pytest.mark.asyncio
async def test_bear_dissent_node_does_not_mutate_original_context():
    """bear_dissent_node must NOT inject rebuttal into context_to_use (Segment A)."""
    orig_context = {"symbol": "EURUSD", "decision": "BUY", "entry": 1.0850}
    state = {
        "actionable_trades": [("EURUSD", {"direction": "BUY", "analysis_id": 1})],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]},
                "original_context": dict(orig_context),
                "fact_sheet": {"symbol": "EURUSD", "vix": 16.5},
                "bull_rebuttal": {"rebuttal_strength": 7, "rebuttal_evidence": ["1.0850"]},
                "curr_p": 1.0850,
            }
        },
    }

    mock_scheduler = MagicMock()
    mock_scheduler.settings = {"agent_architecture": {"enable_debate": True}}
    config = {"configurable": {"scheduler": mock_scheduler}}

    with patch(
        "monika.application.graph.nodes.debate.bear_dissent_node.generate_bear_dissent",
        new_callable=AsyncMock,
    ) as mock_bear:
        mock_bear.return_value = {
            "bear_dissent": "counter",
            "risk_severity": 6,
            "evidence_cited": ["1.0850", "1.0800"],
        }
        with patch("monika.application.graph.nodes.debate.bear_dissent_node.get_client_for_task"):
            await bear_dissent_node(state, config)

        assert mock_bear.called
        call_args = mock_bear.call_args
        # Arg 2 (0-indexed: client=0, sym=1, original_context=2)
        passed_context = call_args[0][2]
        assert "bull_rebuttal" not in passed_context, "original_context was mutated with bull_rebuttal!"
        assert "rebuttal" not in passed_context, "original_context was mutated with rebuttal!"
        # rebuttal must be passed as keyword arg
        assert call_args[1].get("rebuttal") == {"rebuttal_strength": 7, "rebuttal_evidence": ["1.0850"]}


@pytest.mark.asyncio
async def test_adjudication_verifier_padded_and_passes_task_role():
    """verify_adjudication must pad system_prompt with anchor and pass task_role='stage2_adjudicator'."""
    settings = {"llm": {"small_roles_anchor": {"enabled": True}}}
    mock_client = MagicMock()
    mock_client.model = "gemini-2.5-flash"
    mock_client.classify_json = AsyncMock(
        return_value={
            "verdict": "CONFIRM",
            "adjudication_rule_correctly_applied": True,
            "expected_outcome_per_rules": "buy",
            "is_conditional_wait": False,
        }
    )

    with patch(
        "monika.application.analysis.validators.adjudication_verifier.get_client_for_task",
        return_value=mock_client,
    ):
        await verify_adjudication(
            settings=settings,
            symbol="EURUSD",
            specialist_biases={"technical": "BUY", "macro": "BUY"},
            specialist_confidence={"technical": 0.85, "macro": 0.80},
            final_decision="buy",
            rationale="Aligned bullish specialists",
        )

    assert mock_client.classify_json.called
    call_kwargs = mock_client.classify_json.call_args[1]
    assert call_kwargs.get("task_role") == "stage2_adjudicator", "task_role was not passed to classify_json"
    system_prompt = call_kwargs.get("system_prompt", "")
    assert CacheBreakpointManager.CANONICAL_TIER0_ANCHOR[:80] in system_prompt or len(system_prompt) >= 1000, (
        "system_prompt was not padded with anchor"
    )
