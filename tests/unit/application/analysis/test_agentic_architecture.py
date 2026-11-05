# ==============================================================================
# File: tests/unit/application/analysis/test_agentic_architecture.py
# Description: Unit tests for Agentic prompt assembly, bottom anchor,
#              and SmartGuard schema boundary normalization.
# ==============================================================================

import pytest
from monika.application.analysis.prompt.prompt_assembler import (
    PromptAssembler,
    build_stage1_agentic_prompt,
    build_stage2_agentic_prompt,
)
from monika.application.analysis.schemas.analysis_schemas import SubmitAssetAnalysisSchema
from monika.application.skills.loader import compose_system_prompt


def test_compose_system_prompt_with_sandwich_bottom_anchor():
    """Verify that sandwich_bottom_anchor is placed strictly at the bottom of the prompt."""
    anchor = "## FINAL MANDATORY CONTRACT ANCHOR: DO NOT VIOLATE"
    prompt = compose_system_prompt(
        "central_banks_framework",
        sandwich_bottom_anchor=anchor,
    )
    assert anchor in prompt
    assert prompt.strip().endswith(anchor)


def test_stage1_agentic_prompt_structure_and_skills():
    """Verify Stage 1 agentic prompt includes all canonical skills and 5-phase SOP."""
    settings = {"trading": {"caveman_mode": False}}
    sys_prompt, user_msg = build_stage1_agentic_prompt(settings)

    # 1. Zero prefetch dump in user message
    assert "[PRE-FETCHED DATA]" not in user_msg
    assert "sequential 5-phase investigation workflow" in user_msg

    # 2. 5-Phase Sequential Investigation Directive
    assert "PHASE 1: Sovereign Yields, Curve Health & Dollar Dominance" in sys_prompt
    assert "PHASE 2: Central Bank Policy & Market Rate Pricing" in sys_prompt
    assert "PHASE 3: Macro Stress, Volatility & Institutional Positioning" in sys_prompt
    assert "PHASE 4: Web Research Escalation Gate" in sys_prompt
    assert "PHASE 5: Synthesis & Decision Submission" in sys_prompt

    # 3. Canonical trading skills presence
    assert "Central Banks Framework" in sys_prompt or "central_banks_framework" in sys_prompt.lower()
    assert "Macro Yield Curve Regimes" in sys_prompt or "macro_yield_curve_regimes" in sys_prompt.lower()

    # 4. Bottom anchor contract placed at the very end
    assert "FINAL MANDATORY SUBMISSION CONTRACT & SCHEMA ANCHOR" in sys_prompt
    assert "macro_narrative" in sys_prompt
    assert "currency_bias" in sys_prompt


def test_stage2_agentic_prompt_structure_and_skills():
    """Verify Stage 2 agentic prompt includes full SMC skills, 5-phase SOP, and bottom anchor."""
    settings = {"trading": {"risk": {"min_rr_ratio": 1.75}}}
    sys_prompt, user_msg = build_stage2_agentic_prompt(
        settings, symbol="EURUSD", cot_code="099741", effective_threshold=9, min_rr_ratio=1.75
    )

    # 1. Zero prefetch dump in user message
    assert "[PRE-FETCHED SYMBOL DATA]" not in user_msg
    assert "Symbol: EURUSD" in user_msg
    assert "Threshold: 9/14" in user_msg

    # 2. 5-Phase Sequential Investigation Directive
    assert "PHASE 1: Macro Alignment & Core Trend Baseline" in sys_prompt
    assert "PHASE 2: Market Structure & Smart Money Concepts (SMC)" in sys_prompt
    assert "PHASE 3: Volatility Environment, Intraday Geometry & Institutional / Retail Positioning" in sys_prompt
    assert "PHASE 4: Web Research Escalation Gate" in sys_prompt
    assert "PHASE 5: Confluence Scorecard, Sizing & Submission" in sys_prompt

    # 3. Canonical SMC & trading skills presence
    assert "smc_ict_playbook" in sys_prompt.lower() or "smart money concepts" in sys_prompt.lower()
    assert "adjudication_framework" in sys_prompt.lower() or "adjudication" in sys_prompt.lower()

    # 4. Bottom anchor contract mapped to target symbol
    assert "FINAL MANDATORY SUBMISSION CONTRACT & SCHEMA ANCHOR" in sys_prompt
    assert '`symbol`: "EURUSD"' in sys_prompt


def test_smartguard_boundary_auto_normalization_confluence():
    """SmartGuard auto-extracts confluence_score from rationale if omitted from root dict."""
    payload = {
        "symbol": "EURUSD",
        "decision": "wait",
        "confidence": 0.85,
        "rationale": "Dealing range pos=0.48 indicates EQUILIBRIUM CHOP. Calculated Confluence Score: 5/14.",
        "invalidation": "Thesis invalid if price breaks above 1.14050 on H4 close.",
    }
    schema = SubmitAssetAnalysisSchema.model_validate(payload)
    assert schema.confluence_score == 5
    assert schema.invalidation_price == 1.14050
    assert schema.invalidation_direction == "above"


def test_smartguard_boundary_auto_normalization_buy_order():
    """SmartGuard auto-normalizes buy order with missing priced_in_score and extracted invalidation."""
    payload = {
        "symbol": "XAUUSD",
        "decision": "buy",
        "confidence": 0.90,
        "rationale": (
            "Bullish order block confirmed at discount pos=0.28. Confluence Score: 10/14. "
            "Priced-in score: 3. Measured H4 ATR=18.5."
        ),
        "stop_loss": 2630.0,
        "take_profit": 2680.0,
        "invalidation": "Thesis invalid if price closes below 2630.00.",
    }
    schema = SubmitAssetAnalysisSchema.model_validate(payload)
    assert schema.confluence_score == 10
    assert schema.invalidation_price == 2630.0
    assert schema.invalidation_direction == "below"
    assert schema.priced_in_score == 3
    assert schema.entry_condition is not None
    assert schema.entry_condition.type == "market"


def test_dynamic_subagent_pool_agentic_contract_and_skills():
    """Verify DynamicSubagentPool creates Bottom-Anchor contracts for specialist workers."""
    from monika.application.analysis.subagent_spawner import DynamicSubagentPool

    dummy_tools = [
        {"name": "get_bond_yield_spreads"},
        {"name": "get_treasury_yields"},
        {"name": "get_central_bank_expectations"},
        {"name": "get_interest_rates"},
        {"name": "get_fedwatch_probabilities"},
        {"name": "get_technical_indicators"},
        {"name": "get_smc_zones"},
        {"name": "get_structure_breaks"},
        {"name": "get_swing_points"},
        {"name": "get_daily_range_context"},
        {"name": "get_cot_report"},
        {"name": "get_retail_sentiment"},
    ]

    # Agentic mode ON (default)
    pool_agentic = DynamicSubagentPool(settings={"analysis": {"agentic": {"enabled": True}}})
    specs_ag = pool_agentic.decompose_research_query(
        query="Analisis EURUSD makro dan teknikal SMC",
        available_tools=dummy_tools,
    )
    macro_ag = next(s for s in specs_ag if s.worker_id == "worker_macro")
    tech_ag = next(s for s in specs_ag if s.worker_id == "worker_tech")

    assert "AUTONOMOUS INVESTIGATION CONTRACT: MACRO & CENTRAL BANK SPECIALIST" in macro_ag.query
    assert "MANDATORY SEQUENTIAL EXECUTION PROTOCOL (AGENTIC WORKER):" in macro_ag.query
    assert "get_bond_yield_spreads" in macro_ag.query
    assert "Phase 3 (Escalation Gate):" in macro_ag.query

    assert "AUTONOMOUS INVESTIGATION CONTRACT: TECHNICAL & SMC LIQUIDITY SPECIALIST" in tech_ag.query
    assert "get_smc_zones" in tech_ag.query

    # Agentic mode OFF (legacy fallback)
    pool_legacy = DynamicSubagentPool(settings={"analysis": {"agentic": {"enabled": False}}})
    specs_leg = pool_legacy.decompose_research_query(
        query="Analisis EURUSD makro",
        available_tools=dummy_tools,
    )
    macro_leg = next(s for s in specs_leg if s.worker_id == "worker_macro")
    assert "AUTONOMOUS INVESTIGATION CONTRACT" not in macro_leg.query


@pytest.mark.asyncio
async def test_macro_judge_agentic_verification_turn():
    """Verify Chief Macro Judge executes run_chat_loop with verification tools under agentic mode."""
    from unittest.mock import AsyncMock, MagicMock
    from monika.application.analysis.debate.macro_judge import run_macro_judge

    mock_client = MagicMock()
    mock_client.run_chat_loop = AsyncMock(
        return_value={
            "reply": (
                '```json\n{\n  "bull_arguments_score": 2,\n  "bear_arguments_score": 9,\n'
                '  "rationale": "Bull claims falsified by tool verification.",\n'
                '  "winner": "RISK_OFF_USD_BULL",\n  "dxy_bias": "BULLISH",\n'
                '  "risk_asset_bias": "BEARISH",\n  "escalation_required": false\n}\n```'
            )
        }
    )

    fake_executor = MagicMock()
    settings = {"analysis": {"agentic": {"enabled": True}}}

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "monika.application.analysis.debate.macro_judge.get_client_for_task",
            lambda task, cfg: mock_client,
        )
        res = await run_macro_judge(
            bull_thesis={"thesis": "Bull claims fake yield"},
            bear_thesis={"thesis": "Bear claims real yield"},
            context="Macro Context",
            settings=settings,
            tool_executor=fake_executor,
        )

    assert mock_client.run_chat_loop.called
    assert res["winner"] == "RISK_OFF_USD_BULL"
    assert res["bull_arguments_score"] == 2
    assert res["bear_arguments_score"] == 9
    assert res["dxy_bias"] == "BULLISH"
