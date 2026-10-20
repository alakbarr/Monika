"""
Unit tests for Unified Risk Contract, Stage 2 Tool Alignment, and Validation Gate Splitting.
Verifies Phase 4 requirements of the Monika Profitability Remediation Plan.
"""

import pytest

from monika.application.analysis.prompt.prompt_assembler import (
    STAGE2_TOOL_STUBS,
    TIER2_TOOL_STUBS,
    PromptAssembler,
)
from monika.application.analysis.prompt.risk_contract import (
    RiskContract,
    build_risk_contract,
)
from monika.application.analysis.tools.mixins.analysis_validation import (
    AssetAnalysisValidationMixin,
)


def test_build_risk_contract_defaults():
    contract = build_risk_contract("EURUSD", settings={})
    assert contract.symbol == "EURUSD"
    assert contract.min_rr_ratio == 1.3
    assert contract.min_sl_atr_multiplier == 1.0
    assert contract.max_sl_adr_pct == 0.35
    assert contract.target_tp_min_adr_pct == 0.50
    assert contract.target_tp_max_adr_pct == 0.80

    rendered = contract.render_prompt_contract()
    assert "CANONICAL RISK CONTRACT (EURUSD)" in rendered
    assert "Minimum Reward-to-Risk (R:R) Ratio: >= 1.30" in rendered
    assert "Stop Loss (SL) Minimum Distance: >= 1.00x H4 ATR" in rendered


def test_build_risk_contract_symbol_overrides():
    settings = {
        "trading": {
            "risk": {
                "min_rr_ratio": 1.8,
                "min_sl_atr_multiplier_by_symbol": {
                    "XAUUSD": 1.5,
                    "default": 1.0,
                },
            }
        }
    }
    xau_contract = build_risk_contract("XAUUSD", settings=settings)
    assert xau_contract.symbol == "XAUUSD"
    assert xau_contract.min_rr_ratio == 1.8
    assert xau_contract.min_sl_atr_multiplier == 1.5

    eur_contract = build_risk_contract("EURUSD", settings=settings)
    assert eur_contract.symbol == "EURUSD"
    assert eur_contract.min_rr_ratio == 1.8
    assert eur_contract.min_sl_atr_multiplier == 1.0


def test_validation_gate_splitting():
    # 1. GATE_FATAL errors must classify as GATE or GATE_FATAL
    gate_fatal_errs = [
        "ENTRY BLOCKED: only 12% of today's typical ADR range remains",
        "volatility regime gate active: market in extreme crash",
        "Priced-in conflict HARD BLOCKED: Stage 1 says fully priced in",
    ]
    for err in gate_fatal_errs:
        assert AssetAnalysisValidationMixin._classify_validation_errors([err]) in ("GATE", "GATE_FATAL")

    # 2. GATE_FIXABLE errors must classify as GATE_FIXABLE
    gate_fixable_errs = [
        "SSVP BLOCKED: Price inside value area without limit trigger",
        "Liquidity sweep required for entry zone",
        "PRICED-IN CONFLICT (REVERSE): Your asset score contradicts Stage 1",
    ]
    for err in gate_fixable_errs:
        assert AssetAnalysisValidationMixin._classify_validation_errors([err]) == "GATE_FIXABLE"

    # 3. STRUCTURAL errors must classify as STRUCTURAL
    structural_errs = [
        "R:R ratio 1.10 is below minimum 1.3 required for positive expected value",
        "SL distance (0.0010) is less than required minimum (1.0x ATR_14)",
        "TP too close for intraday-range strategy: distance=0.0020 < minimum band",
        "TP too far for intraday-range strategy: distance=0.0150 > maximum band",
    ]
    for err in structural_errs:
        assert AssetAnalysisValidationMixin._classify_validation_errors([err]) == "STRUCTURAL"

    # 4. FATAL data errors must classify as FATAL
    fatal_errs = [
        "No H4 technical indicators found for EURUSD",
        "H4 technical indicators for EURUSD are 6.2h old (stale — MT5 may be disconnected)",
    ]
    for err in fatal_errs:
        assert AssetAnalysisValidationMixin._classify_validation_errors([err]) == "FATAL"


def test_stage2_tool_alignment():
    # Verify STAGE2_TOOL_STUBS contains the exact tools available in ASSET_RESTRICTED_TOOLS
    assert "submit_asset_analysis" in STAGE2_TOOL_STUBS
    assert "calculate_position_size" in STAGE2_TOOL_STUBS
    assert "get_market_quote" in STAGE2_TOOL_STUBS
    assert "get_verified_market_snapshot" in STAGE2_TOOL_STUBS
    assert "get_optimal_intraday_levels" in STAGE2_TOOL_STUBS
    assert "get_price_data" in STAGE2_TOOL_STUBS
    assert "get_technical_analysis" in STAGE2_TOOL_STUBS

    # And does NOT advertise obsolete / unavailable tools in Stage 2
    assert "get_open_positions" not in STAGE2_TOOL_STUBS
    assert "execute_order_guard" not in STAGE2_TOOL_STUBS
    assert "submit_fundamental_brief" not in STAGE2_TOOL_STUBS

    # PromptAssembler injects STAGE2_TOOL_STUBS into Stage 2 prompt
    assembler = PromptAssembler()
    t1, t2, t3 = assembler.assemble_stage2_tiers(symbol="EURUSD", include_target_in_system=True)
    assert "AVAILABLE TOOLS FOR INTRADAY ASSET ANALYSIS" in t2
    assert "submit_asset_analysis" in t2
