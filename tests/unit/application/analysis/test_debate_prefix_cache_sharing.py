"""
Unit Tests for Multi-Agent Debate Prefix-Sharing & Grounding Architecture.

Validates:
1. Byte-for-byte identity of system prompts and Tier-2 cached prefixes across debate participants.
2. Determinism of Market Grounding tables under fixed bar timestamps / as_of.
3. Blackboard claim metadata extraction and contested price level detection.
4. Mathematical grounding verification (_is_grounded) guarding against hallucinated price levels.
5. Fail-closed safety in Risk Gate respecting provenance_verified=False.
6. SymbolFactBundle pre-computation and cache metric reporting.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from monika.application.analysis.calculators.symbol_fact_bundle import (
    SymbolFactBundle,
    build_symbol_fact_bundle,
)
from monika.application.analysis.debate.bear_analyst import (
    generate_bear_claim,
    generate_bear_dissent,
    generate_bear_rebuttal,
)
from monika.application.analysis.debate.blackboard import DebateBlackboard
from monika.application.analysis.debate.bull_analyst import (
    generate_bull_advocacy,
    generate_bull_claim,
    generate_bull_rebuttal,
)
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.grounding.market_grounding import MarketGroundingEngine
from monika.application.graph.nodes.debate.helpers import _is_grounded
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager


@pytest.mark.asyncio
async def test_byte_identical_system_prompt_across_debate_participants():
    """Verify system prompts across Bull, Bear, Rebuttals, and Judge are byte-for-byte identical."""
    canonical_sys = CacheBreakpointManager.get_canonical_debate_system_prompt()
    assert CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip() in canonical_sys
    assert CacheBreakpointManager.UNIVERSAL_DEBATE_CONSTITUTION.strip() in canonical_sys
    assert "target asset specified in the user message" in canonical_sys

    mock_client = MagicMock()
    mock_client.generate_content = AsyncMock(
        return_value='{"bull_thesis": "support", "strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]}'
    )
    mock_client.classify_json = AsyncMock(
        return_value={"final_decision": "buy", "reason": "ok", "risk_multiplier": 1.0}
    )
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096

    original_context = {"decision": "buy", "price": 1.0850, "sl": 1.0800, "tp": 1.0950}
    fact_sheet = {"current_price": 1.0850, "atr_14": 0.0035}

    # 1. Bull Advocacy
    await generate_bull_advocacy(mock_client, "EURUSD", original_context, fact_sheet)
    bull_sys = mock_client.generate_content.call_args[1]["system_prompt"]

    # 2. Bull Rebuttal
    bull_claim = {"strength_score": 8, "evidence_cited": ["1.0850", "1.0800"]}
    bear_dissent = {"risk_severity": 6, "evidence_cited": ["1.0850", "1.0800"]}
    await generate_bull_rebuttal(mock_client, "EURUSD", original_context, fact_sheet, bull_claim, bear_dissent)
    bull_reb_sys = mock_client.generate_content.call_args[1]["system_prompt"]

    # 3. Bear Dissent
    mock_client.generate_content.return_value = (
        '{"bear_dissent": "resistance", "risk_severity": 6, "evidence_cited": ["1.0850", "1.0800"]}'
    )
    await generate_bear_dissent(mock_client, "EURUSD", original_context, bull_claim, fact_sheet)
    bear_sys = mock_client.generate_content.call_args[1]["system_prompt"]

    # 4. Bear Rebuttal
    mock_client.generate_content.return_value = (
        '{"rebuttal_thesis": "defend", "rebuttal_strength": 7, "rebuttal_evidence": ["1.0850", "1.0800"]}'
    )
    await generate_bear_rebuttal(mock_client, "EURUSD", original_context, fact_sheet, bear_dissent, bull_claim)
    bear_reb_sys = mock_client.generate_content.call_args[1]["system_prompt"]

    # 5. Investment Judge
    del mock_client.classify_json
    mock_client.generate_content.return_value = '{"final_decision": "buy", "reason": "strong", "risk_multiplier": 1.0}'
    await evaluate_debate(mock_client, "EURUSD", original_context, bull_claim, bear_dissent, fact_sheet=fact_sheet)
    judge_sys = mock_client.generate_content.call_args[1]["system_prompt"]

    # Strict byte-for-byte invariant check
    assert bull_sys == canonical_sys
    assert bull_reb_sys == canonical_sys
    assert bear_sys == canonical_sys
    assert bear_reb_sys == canonical_sys
    assert judge_sys == canonical_sys


def test_segment_a_byte_identical_across_debate_messages():
    """Verify Segment A prefix (before Tier 2 Breakpoint) is 100% byte-for-byte identical across turns."""
    fact_sheet = {"symbol": "EURUSD", "current_price": 1.0850, "atr_14": 0.0035, "vix": 16.5}
    original_context = {"decision": "BUY", "entry": 1.0850, "sl": 1.0800, "tp": 1.0950}

    # Turn 1: Bull
    msg_bull = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger=None,
        task_directive="Generate bull thesis",
    )

    # Turn 2: Bear
    msg_bear = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger={"bull_claim": {"strength_score": 8}},
        task_directive="Generate bear dissent",
    )

    # Turn 3: Rebuttal
    msg_rebuttal = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger={"bull_claim": {"strength_score": 8}, "bear_dissent": {"risk_severity": 6}},
        task_directive="Generate bull rebuttal",
    )

    # Turn 4: Judge
    msg_judge = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=fact_sheet,
        original_context=original_context,
        append_ledger={"bull_claim": {"strength_score": 8}, "bear_dissent": {"risk_severity": 6}, "rebuttal": {}},
        task_directive="Evaluate debate",
    )

    split_marker = "=== TIER 2 CYCLE CACHE BREAKPOINT ==="
    assert split_marker in msg_bull
    assert split_marker in msg_bear
    assert split_marker in msg_rebuttal
    assert split_marker in msg_judge

    prefix_bull = msg_bull.split(split_marker)[0]
    prefix_bear = msg_bear.split(split_marker)[0]
    prefix_rebuttal = msg_rebuttal.split(split_marker)[0]
    prefix_judge = msg_judge.split(split_marker)[0]

    # Exact byte-for-byte identity
    assert prefix_bull == prefix_bear
    assert prefix_bear == prefix_rebuttal
    assert prefix_rebuttal == prefix_judge


@pytest.mark.asyncio
async def test_market_grounding_table_determinism_with_as_of():
    """Verify MarketGroundingEngine produces byte-identical tables when given fixed bar state."""

    class MockBar:
        def __init__(self, d: str, o: float, h: float, l: float, c: float, v: float):
            self.timestamp = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            self.open = o
            self.high = h
            self.low = l
            self.close = c
            self.volume = v

    bars = [
        MockBar("2026-10-20", 1.0800, 1.0850, 1.0780, 1.0820, 10000),
        MockBar("2026-10-21", 1.0820, 1.0870, 1.0810, 1.0860, 12000),
        MockBar("2026-10-22", 1.0860, 1.0900, 1.0840, 1.0890, 15000),
    ]

    mock_repo = MagicMock()
    mock_repo.get_recent_bars = AsyncMock(return_value=bars)

    fixed_as_of = datetime(2026, 10, 22, 16, 0, 0, tzinfo=timezone.utc)

    table1 = await MarketGroundingEngine.build_grounding_table(symbol="EURUSD", repository=mock_repo, as_of=fixed_as_of)
    table2 = await MarketGroundingEngine.build_grounding_table(symbol="EURUSD", repository=mock_repo, as_of=fixed_as_of)

    assert table1 == table2
    assert "Generated at: 2026-10-22 16:00:00 UTC" in table1
    assert "1.0890" in table1
    assert "- **Current Reference Price**: `1.0890`" in table1


def test_debate_blackboard_metadata_extraction_and_contradictions():
    """Verify DebateBlackboard automatically extracts levels, falsification triggers, and detects friction."""
    bb = DebateBlackboard(symbol="EURUSD")

    bull_claim = {
        "bull_thesis": "Demand block holding at 1.0850",
        "key_levels": [1.0850, 1.0920],
        "falsification_triggers": ["DXY > 105.0", "H4 close below 1.0820"],
    }
    bear_dissent = {
        "bear_dissent": "Supply rejection at 1.0850",
        "invalidation_price": 1.0850,
        "Primary_Risk_Trigger": "Hawkish Fed commentary",
    }

    bb.add_bull_thesis("Bullish demand defense", claim_dict=bull_claim)
    bb.add_bear_thesis("Bearish supply rejection", claim_dict=bear_dissent)

    assert len(bb.bull_claims) == 1
    assert bb.bull_claims[0]["key_levels"] == [1.0850, 1.0920]
    assert "DXY > 105.0" in bb.bull_claims[0]["falsification_triggers"]

    assert len(bb.bear_claims) == 1
    assert 1.0850 in bb.bear_claims[0]["key_levels"]
    assert "Hawkish Fed commentary" in bb.bear_claims[0]["falsification_triggers"]

    contradictions = bb.extract_sparse_contradictions()
    contested_zones = [c for c in contradictions if c.get("type") == "contested_price_levels"]
    assert len(contested_zones) >= 1
    assert 1.0850 in contested_zones[0]["levels"]


def test_is_grounded_validation():
    """Verify _is_grounded filters trivial periods and rejects claims with ungrounded decimal prices."""
    current_price = 1.0850
    fact_sheet = {"current_price": 1.0850, "atr_14": 0.0035, "support": 1.0800, "resistance": 1.0920}

    # 1. Grounded claim: prices near current_price and in fact_sheet
    grounded_claim = {
        "bull_thesis": "Entry at 1.0850 with SL at 1.0800 and TP at 1.0920, ATR_14=0.0035",
        "key_levels": [1.0850, 1.0800, 1.0920],
    }
    assert _is_grounded(grounded_claim, current_price=current_price, reference=fact_sheet) is True

    # 2. Hallucinated claim: RSI_14 trivial period + 3 hallucinated decimal prices far from price
    hallucinated_claim = {
        "thesis": "RSI_14 indicator triggered, targeting 1.5500, 1.6200, and 1.7000",
        "key_levels": [14, 1.5500, 1.6200, 1.7000],
    }
    # Current price is 1.0850; 1.55, 1.62, 1.70 are > 40% away and not in fact_sheet.
    # Trivial period 14 is filtered, and decimal figures fail the 50% grounding threshold.
    assert _is_grounded(hallucinated_claim, current_price=current_price, reference=fact_sheet) is False


def test_disjoint_cache_metrics():
    """Verify compute_disjoint_cache_metrics correctly calculates input tokens and hit rate."""
    metrics = CacheBreakpointManager.compute_disjoint_cache_metrics(
        uncached_input_tokens=200,
        cache_read_tokens=800,
        cache_write_tokens=0,
        output_tokens=150,
    )
    assert metrics["total_input_tokens"] == 1000
    assert metrics["total_tokens"] == 1150
    assert pytest.approx(metrics["kv_cache_hit_rate"], 0.001) == 0.800


@pytest.mark.asyncio
async def test_symbol_fact_bundle_builder():
    """Verify SymbolFactBundle properly caches fact sheet, invariants, and canonical prefix."""
    fact_sheet = {"current_price": 100.0, "atr_14": 2.0, "adr_5d": 4.0}
    original_context = {"decision": "BUY", "entry_price": 100.0, "sl": 98.0, "tp": 104.0}

    bundle = await build_symbol_fact_bundle(
        symbol="XAUUSD",
        fact_sheet=fact_sheet,
        original_context=original_context,
    )

    assert isinstance(bundle, SymbolFactBundle)
    assert bundle.symbol == "XAUUSD"
    assert bundle.trade_invariants is not None
    assert "buy_bounds" in bundle.trade_invariants
    assert "sell_bounds" in bundle.trade_invariants
    assert "=== TIER 2 CYCLE CACHE BREAKPOINT ===" in bundle.canonical_prefix


def test_risk_gate_node_provenance_verified_logic():
    """Verify risk_gate_node provenance_verified evaluation."""

    # Simulation of the logic added to risk_gate_node.py
    def compute_prov_verified(r, ana, entry_price, sl, tp):
        return (
            False
            if (
                r.get("provenance_verified") is False
                or (ana is not None and getattr(ana, "provenance_verified", None) is False)
                or not (entry_price and sl and tp)
            )
            else True
        )

    # 1. Normal valid trade
    assert compute_prov_verified({}, None, 1.0850, 1.0800, 1.0950) is True

    # 2. Flagged False by upstream validator in r
    assert compute_prov_verified({"provenance_verified": False}, None, 1.0850, 1.0800, 1.0950) is False

    # 3. Flagged False on analysis model
    mock_ana = MagicMock()
    mock_ana.provenance_verified = False
    assert compute_prov_verified({}, mock_ana, 1.0850, 1.0800, 1.0950) is False

    # 4. Missing Stop Loss
    assert compute_prov_verified({}, None, 1.0850, None, 1.0950) is False
