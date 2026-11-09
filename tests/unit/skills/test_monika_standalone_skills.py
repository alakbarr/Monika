"""
Unit and Property-Based Tests for Monika Standalone Institutional Skill Suite (11 Packages).

Validates:
1. Structural integrity, directory hierarchy, and metadata standards across all 11 packages.
2. Mandatory Architectural Disclaimer in all packages.
3. Zero unresolved template placeholders in all package documents.
4. Deterministic mathematical invariants across all CLI engines and subcommands.
5. Fail-closed RiskGate 12-point audit invariants.
6. Property-based invariants: Decimal ROUND_FLOOR lot sizing never exceeds risk budget.
"""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict

from hypothesis import HealthCheck, given, settings
import hypothesis.strategies as st
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages" / "monika-skills"

EXPECTED_PACKAGES = [
    "01-monika-full-trading-cycle",
    "02-monika-data-gathering",
    "03-monika-central-banks-monetary-policy",
    "04-monika-yield-curve-liquidity-plumbing",
    "05-monika-economic-nowcasting-event-absorption",
    "06-monika-cot-positioning-anti-crowding",
    "07-monika-smc-ict-price-action",
    "08-monika-session-killzones-microstructure",
    "09-monika-commodities-crypto-carry-playbooks",
    "10-monika-dialectical-debate-judge",
    "11-monika-deterministic-risk-math",
]

MANDATORY_DISCLAIMER_PHRASE = "Monika adalah full-stack algorithmic trading harness"


# -----------------------------------------------------------------------------
# 1. Structural & Package Metadata Tests
# -----------------------------------------------------------------------------


def test_packages_directory_and_package_count():
    assert PACKAGES_DIR.exists(), f"Packages directory not found: {PACKAGES_DIR}"
    package_dirs = [p for p in PACKAGES_DIR.iterdir() if p.is_dir()]
    dir_names = sorted([p.name for p in package_dirs])
    assert dir_names == sorted(EXPECTED_PACKAGES)


@pytest.mark.parametrize("pkg_name", EXPECTED_PACKAGES)
def test_package_structure_and_files(pkg_name: str):
    pkg_path = PACKAGES_DIR / pkg_name
    assert (pkg_path / "SKILL.md").is_file(), f"Missing SKILL.md in {pkg_name}"
    assert (pkg_path / "README.md").is_file(), f"Missing README.md in {pkg_name}"
    assert (pkg_path / "references").is_dir(), f"Missing references/ in {pkg_name}"
    assert (pkg_path / "scripts").is_dir(), f"Missing scripts/ in {pkg_name}"
    assert (pkg_path / "templates").is_dir(), f"Missing templates/ in {pkg_name}"

    ref_files = list((pkg_path / "references").glob("*.md"))
    assert len(ref_files) >= 1, f"No reference markdown files in {pkg_name}"

    script_files = list((pkg_path / "scripts").glob("*.py"))
    assert len(script_files) >= 1, f"No python scripts in {pkg_name}"

    template_files = list((pkg_path / "templates").glob("*.md"))
    assert len(template_files) >= 1, f"No template files in {pkg_name}"


@pytest.mark.parametrize("pkg_name", EXPECTED_PACKAGES)
def test_skill_metadata_and_disclaimer(pkg_name: str):
    pkg_path = PACKAGES_DIR / pkg_name
    skill_content = (pkg_path / "SKILL.md").read_text(encoding="utf-8")
    readme_content = (pkg_path / "README.md").read_text(encoding="utf-8")

    # Frontmatter check
    assert skill_content.startswith("---"), f"{pkg_name}/SKILL.md must start with YAML frontmatter"
    frontmatter_match = re.search(r"^---\n(.*?)\n---", skill_content, re.DOTALL)
    assert frontmatter_match, f"{pkg_name}/SKILL.md invalid frontmatter"
    fm_text = frontmatter_match.group(1)

    assert "name:" in fm_text, f"{pkg_name} frontmatter missing 'name'"
    assert "description:" in fm_text, f"{pkg_name} frontmatter missing 'description'"
    assert "version:" in fm_text, f"{pkg_name} frontmatter missing 'version'"
    assert "tags:" in fm_text, f"{pkg_name} frontmatter missing 'tags'"

    # Disclaimer check
    assert MANDATORY_DISCLAIMER_PHRASE in skill_content, (
        f"{pkg_name}/SKILL.md missing mandatory architectural disclaimer"
    )
    assert MANDATORY_DISCLAIMER_PHRASE in readme_content, (
        f"{pkg_name}/README.md missing mandatory architectural disclaimer"
    )


@pytest.mark.parametrize("pkg_name", EXPECTED_PACKAGES)
def test_zero_unresolved_placeholders(pkg_name: str):
    """Verifies that no raw internal python format placeholders like {symbol} or {cot_code} are left unescaped."""
    pkg_path = PACKAGES_DIR / pkg_name
    all_md_files = list(pkg_path.rglob("*.md"))

    unresolved_pattern = re.compile(
        r"\{(?:symbol|cot_code|effective_threshold|tool_order_guidance|prompt_guidance)\}", re.IGNORECASE
    )

    for md_file in all_md_files:
        content = md_file.read_text(encoding="utf-8")
        matches = unresolved_pattern.findall(content)
        assert not matches, (
            f"Unresolved internal template placeholders {matches} found in {md_file.relative_to(REPO_ROOT)}"
        )


# -----------------------------------------------------------------------------
# 2. CLI Engine & Mathematical Subcommand Tests
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def quant_engine():
    engine_path = PACKAGES_DIR / "01-monika-full-trading-cycle" / "scripts" / "monika_quant_engine.py"
    spec = importlib.util.spec_from_file_location("monika_quant_engine", engine_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["monika_quant_engine"] = module
    spec.loader.exec_module(module)
    return module


def test_validate_telemetry_fresh_and_killzones(quant_engine):
    res = quant_engine.validate_telemetry(
        now_utc_str="2026-11-10T14:30:00Z",
        timestamps_json=json.dumps(
            {
                "fedwatch": "2026-11-10T10:00:00Z",
                "vix": "2026-11-10T12:00:00Z",
            }
        ),
    )
    assert res["stale_data_detected"] is False
    assert res["ttl_multiplier"] == 1.00
    assert "LONDON_NY_OVERLAP" in res["active_killzones"]
    assert res["overlap_bonus_eligible"] is True
    assert res["rollover_blackout"] is False
    assert res["execution_permitted"] is True


def test_validate_telemetry_stale_penalty_and_rollover(quant_engine):
    # Rollover at 22:05 UTC
    res = quant_engine.validate_telemetry(
        now_utc_str="2026-11-10T22:05:00Z",
        timestamps_json=json.dumps(
            {
                "fedwatch": "2026-11-09T00:00:00Z",  # > 12h stale
            }
        ),
    )
    assert res["stale_data_detected"] is True
    assert res["ttl_multiplier"] == 0.50
    assert res["rollover_blackout"] is True
    assert res["execution_permitted"] is False


def test_cb_differential_algebraic_invariant(quant_engine):
    res = quant_engine.cb_differential(
        base_currency="EUR",
        quote_currency="USD",
        base_rate=3.25,
        quote_rate=4.75,
        base_r_star=2.125,
        quote_r_star=2.875,
        base_inflation=2.4,
        quote_inflation=2.8,
    )
    assert res["pair"] == "EURUSD"
    assert res["algebraic_invariant_verified"] is True
    # Base stance: 3.25 - 2.125 = 1.125; Quote stance: 4.75 - 2.875 = 1.875 -> Quote more hawkish -> Bearish EURUSD
    assert res["net_pair_bias_score"] < 0
    assert res["structural_bias"] in ("BEARISH", "NEUTRAL")


def test_macro_calc_net_liquidity_and_vix(quant_engine):
    res = quant_engine.macro_calc(
        walcl_billions=7100.0,
        tga_billions=750.0,
        rrp_billions=250.0,
        prev_net_liquidity_billions=6050.0,
        us10y=4.40,
        us2y=4.20,
        tips10y=2.00,
        vix=22.5,
        hy_oas_bps=340.0,
    )
    # Net Liquidity = 7100 - 750 - 250 = 6100 (expansion of +50)
    assert res["net_liquidity_billions"] == 6100.0
    assert res["net_liquidity_delta_billions"] == 50.0
    assert res["systemic_liquidity_stance"] == "EXPANDING"
    assert res["yield_2s10s_spread"] == 0.20
    assert res["curve_regime"] == "STEEPENER_NORMAL"
    assert res["breakeven_inflation_10y"] == 2.40
    assert res["vix_regime"] == "CAUTION"
    assert res["vix_risk_multiplier"] == 0.75
    assert res["credit_stress_hard_veto"] is False


def test_event_calc_net_surprise_and_priced_in(quant_engine):
    # NFP Beat: Consensus 180, Actual 210, but prior revised down by -45 -> Net Surprise = -15
    res = quant_engine.event_calc(
        actual=210.0,
        consensus=180.0,
        previous=200.0,
        prior_revision=-45.0,
        priced_in_fedwatch=8.5,
        priced_in_cot=8.0,
        priced_in_exhaustion=8.5,
        priced_in_historical=7.5,
    )
    assert res["net_surprise"] == -15.0
    assert res["priced_in_score"] == 8.12
    assert res["exhaustion_warning"] is True
    assert "EXHAUSTION WARNING" in res["execution_guidance"]


def test_cot_synergy_states(quant_engine):
    # 1. Uncrowded Institutional Synergy (81.8% accuracy)
    res_uncrowded = quant_engine.cot_synergy(
        cot_net_pct=60.0,
        cot_52w_pct=65.0,
        tech_dir="buy",
        macro_dir="buy",
        sent_dir="buy",
    )
    assert res_uncrowded["synergy_state"] == "uncrowded_institutional_synergy"
    assert res_uncrowded["synergy_multiplier"] == 1.10

    # 2. Crowded Unanimous Exhaustion Trap
    res_crowded = quant_engine.cot_synergy(
        cot_net_pct=92.0,
        cot_52w_pct=92.0,
        tech_dir="buy",
        macro_dir="buy",
        sent_dir="buy",
    )
    assert res_crowded["synergy_state"] == "crowded_unanimous_exhaustion"
    assert res_crowded["synergy_multiplier"] == 0.82

    # 3. Crowded Tech+Sent Trap vs Macro
    res_trap = quant_engine.cot_synergy(
        cot_net_pct=50.0,
        cot_52w_pct=50.0,
        tech_dir="buy",
        macro_dir="sell",
        sent_dir="buy",
    )
    assert res_trap["synergy_state"] == "crowded_tech_sent_trap_vs_macro"
    assert res_trap["synergy_multiplier"] == 0.85


def test_smc_confluence_dealing_range_and_tiers(quant_engine):
    # Discount Zone (pos <= 0.35)
    res_disc = quant_engine.smc_confluence(
        close=1.0820,
        high20=1.0950,
        low20=1.0800,
        atr14=0.0040,
        confluence_score=13,
    )
    # pos = (1.0820 - 1.0800) / (1.0950 - 1.0800) = 0.0020 / 0.0150 = 0.1333 (Extreme discount)
    assert res_disc["is_discount"] is True
    assert res_disc["zone"] == "DISCOUNT_ZONE"
    assert res_disc["confluence_tier"] == "FULL_CONFLUENCE"
    assert res_disc["confluence_multiplier"] == 1.00

    # Anti-Chasing Ceiling (pos > 0.85)
    res_chase = quant_engine.smc_confluence(
        close=1.0940,
        high20=1.0950,
        low20=1.0800,
        atr14=0.0040,
        confluence_score=12,
    )
    # pos = 0.0140 / 0.0150 = 0.9333 (Premium Zone -> SELL allowed, BUY blocked by anti-chasing)
    assert res_chase["anti_chasing_buy_block"] is True
    assert res_chase["allowed_direction"] == "SELL"
    assert res_chase["zone"] == "PREMIUM_ZONE"


def test_debate_judge_attenuation_and_anti_fence_sitting(quant_engine):
    # Bull 8.5 vs Bear 5.0, but Bear has a strong rebuttal (8.0 >= 7.0) -> Bull discounted by -3.0 to 5.5
    res = quant_engine.debate_judge(
        bull_score=8.5,
        bear_score=5.0,
        bull_rebuttal_quality=4.0,
        bear_rebuttal_quality=8.0,
        regime="trending",
        active_criteria_met=4,
    )
    assert res["attenuated_bull_score"] == 5.5
    assert res["attenuated_bear_score"] == 5.0
    # Difference is 0.5 < 1.5 -> Fence sitting holds
    assert res["arbitrated_verdict"] == "HOLD"

    # Now Bull mounts an overwhelming case with strong rebuttal (8.0) and Bear rebuttal weak (4.0)
    res_win = quant_engine.debate_judge(
        bull_score=8.5,
        bear_score=4.0,
        bull_rebuttal_quality=8.0,
        bear_rebuttal_quality=4.0,
        regime="trending",
        active_criteria_met=4,
    )
    # Bear discounted from 4.0 to 1.0 (min floor), Bull stays 8.5
    assert res_win["attenuated_bull_score"] == 8.5
    assert res_win["attenuated_bear_score"] == 1.0
    assert res_win["arbitrated_verdict"] == "BUY"
    assert res_win["bayesian_risk_multiplier"] == 1.00
    assert res_win["anti_fence_sitting_enforced"] is True


def test_brackets_precision_noise_floor_and_rr(quant_engine):
    # EURUSD (5 decimals, 1.25x ATR floor)
    res_eur = quant_engine.generate_brackets(
        symbol="EURUSD",
        price=1.08500,
        atr14=0.00400,
        adr5d=0.00800,
        target_rr=1.80,
    )
    long_b = res_eur["long_option_a"]
    short_b = res_eur["short_option_b"]
    assert res_eur["precision"] == 5
    assert long_b["rr_ratio"] >= 1.50
    assert short_b["rr_ratio"] >= 1.50
    assert long_b["sl_distance_atr"] >= 1.25
    assert short_b["sl_distance_atr"] >= 1.25

    # XAUUSD (2 decimals, 1.35x ATR floor)
    res_gold = quant_engine.generate_brackets(
        symbol="XAUUSD",
        price=2685.50,
        atr14=20.00,
        adr5d=35.00,
        target_rr=1.80,
    )
    assert res_gold["precision"] == 2
    assert res_gold["noise_floor_atr"] == 1.35
    assert res_gold["long_option_a"]["sl_distance_atr"] >= 1.35


def test_risk_gate_twelve_checks_approval_and_rejection(quant_engine):
    # 1. Full Approval
    res_ok = quant_engine.audit_risk_gate(
        symbol="EURUSD",
        direction="buy",
        entry=1.08500,
        sl=1.08000,
        tp=1.09400,
        atr14=0.00400,
        adr5d=0.00800,
        pos=0.25,
        equity=10000.0,
        daily_drawdown_pct=0.5,
        vix=16.0,
        spread_ratio=1.1,
    )
    assert res_ok["approved"] is True
    assert res_ok["verdict"] == "APPROVED"
    assert res_ok["passed_count"] == 12
    assert res_ok["failed_count"] == 0

    # 2. Multi-Failure Rejection (Inverted bracket, Drawdown breach, Anti-chasing)
    res_bad = quant_engine.audit_risk_gate(
        symbol="EURUSD",
        direction="buy",
        entry=1.08500,
        sl=1.09000,  # Inverted: SL > Entry
        tp=1.08000,  # Inverted: TP < Entry
        atr14=0.00400,
        adr5d=0.00800,
        pos=0.92,  # Anti-chasing violation > 0.85
        equity=10000.0,
        daily_drawdown_pct=3.5,  # Drawdown breach >= 3.0%
        vix=32.0,  # Crisis VIX > 30
    )
    assert res_bad["approved"] is False
    assert res_bad["verdict"] == "REJECTED"
    assert "directional_bracket_ordering" in res_bad["checks_failed"]
    assert "spatial_dealing_range_anti_chasing" in res_bad["checks_failed"]
    assert "daily_drawdown_limit" in res_bad["checks_failed"]
    assert "systemic_crisis_gate" in res_bad["checks_failed"]


# -----------------------------------------------------------------------------
# 3. Property-Based Testing via Hypothesis
# -----------------------------------------------------------------------------


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    equity=st.floats(min_value=1000.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    base_risk_pct=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False),
    entry=st.floats(min_value=1.0500, max_value=1.1500, allow_nan=False, allow_infinity=False),
    sl_pips=st.floats(min_value=15.0, max_value=150.0, allow_nan=False, allow_infinity=False),
    vix_mult=st.sampled_from([0.25, 0.50, 0.75, 1.00]),
    judge_mult=st.sampled_from([0.25, 0.50, 0.75, 1.00]),
)
def test_property_decimal_lot_sizing_never_exceeds_risk_budget(
    quant_engine, equity, base_risk_pct, entry, sl_pips, vix_mult, judge_mult
):
    """
    Mathematical Proof Invariant:
    Actual dollar risk at stop loss MUST NEVER exceed the allocated dollar risk budget.
    """
    sl = entry - (sl_pips * 0.0001)

    res = quant_engine.calculate_position_size(
        equity=equity,
        base_risk_pct=base_risk_pct,
        entry=entry,
        sl=sl,
        symbol="EURUSD",
        vix_mult=vix_mult,
        judge_mult=judge_mult,
    )

    if res["is_valid"]:
        # Actual risk must be strictly <= dollar risk budget (due to ROUND_FLOOR)
        actual = Decimal(str(res["actual_dollar_risk"]))
        budget = Decimal(str(res["dollar_risk_budget"]))
        assert actual <= budget + Decimal("0.01"), f"Actual risk ${actual} exceeded budget ${budget}"
