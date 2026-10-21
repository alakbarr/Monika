"""Phase 1: one canonical risk contract across config, prompt, and adaptive policy.

The code defaults, ``config/settings.example.yaml``, the LLM prompt, and the
adaptive threshold policy must never disagree about the risk limits.
"""

from pathlib import Path

import pytest
import yaml

from monika.application.analysis.calculators.adaptive_policy import AdaptiveRiskPolicy
from monika.application.analysis.prompt.prompt_assembler import (
    MANDATORY_RULES,
    PromptAssembler,
)
from monika.core.config.risk_defaults import (
    DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE,
    DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE,
    DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT,
    DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT,
    DEFAULT_MIN_RR_RATIO,
)
from monika.core.config.schemas import RiskConfig, TradingConfig

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "settings.example.yaml"


@pytest.fixture(scope="module")
def example_settings() -> dict:
    return yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))


class TestCanonicalContract:
    def test_example_config_matches_canonical_constants(self, example_settings):
        risk = example_settings["trading"]["risk"]
        assert risk["min_rr_ratio"] == DEFAULT_MIN_RR_RATIO
        assert risk["max_daily_drawdown_percent"] == DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT
        assert risk["max_weekly_drawdown_percent"] == DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT
        assert example_settings["trading"]["auto_execute_min_confluence"] == (DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE)
        assert example_settings["trading"]["auto_execute_min_confidence"] == (DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE)

    def test_code_defaults_match_example_config(self, example_settings):
        risk_cfg = RiskConfig()
        trading_cfg = TradingConfig()
        assert risk_cfg.min_rr_ratio == example_settings["trading"]["risk"]["min_rr_ratio"]
        assert (
            risk_cfg.max_daily_drawdown_percent == (example_settings["trading"]["risk"]["max_daily_drawdown_percent"])
        )
        assert (
            risk_cfg.max_weekly_drawdown_percent == (example_settings["trading"]["risk"]["max_weekly_drawdown_percent"])
        )
        assert trading_cfg.auto_execute_min_confluence == (example_settings["trading"]["auto_execute_min_confluence"])
        assert trading_cfg.auto_execute_min_confidence == (example_settings["trading"]["auto_execute_min_confidence"])

    def test_canonical_values_are_the_agreed_contract(self):
        assert DEFAULT_MIN_RR_RATIO == 1.5
        assert DEFAULT_MAX_DAILY_DRAWDOWN_PERCENT == 4.0
        assert DEFAULT_MAX_WEEKLY_DRAWDOWN_PERCENT == 15.0
        assert DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE == 7
        assert DEFAULT_AUTO_EXECUTE_MIN_CONFIDENCE == 0.60


class TestPromptFollowsConfig:
    def test_thresholds_are_resolved_from_config(self, example_settings):
        assembler = PromptAssembler(settings=example_settings)
        threshold, min_rr = assembler._resolve_stage2_thresholds(None, None)
        assert threshold == example_settings["trading"]["auto_execute_min_confluence"]
        assert min_rr == example_settings["trading"]["risk"]["min_rr_ratio"]

    def test_mandatory_rules_use_the_configured_values(self, example_settings):
        assembler = PromptAssembler(settings=example_settings)
        threshold, min_rr = assembler._resolve_stage2_thresholds(None, None)
        rules = assembler._mandatory_rules(threshold, min_rr)
        assert f">= {threshold}/14.0" in rules
        assert f"R:R {min_rr:.2f}" in rules
        assert "5.0 to 7.0" not in rules

    def test_default_mandatory_rules_use_canonical_contract(self):
        assert f">= {DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE}/14.0" in MANDATORY_RULES
        assert f"R:R {DEFAULT_MIN_RR_RATIO:.2f}" in MANDATORY_RULES

    def test_assembled_stage2_prompt_embeds_config_values(self, example_settings):
        assembler = PromptAssembler(settings=example_settings)
        tier1, _tier2, _tier3 = assembler.assemble_stage2_tiers("EURUSD", include_target_in_system=True)
        assert f"R:R {DEFAULT_MIN_RR_RATIO:.2f}" in tier1
        assert f">= {DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE}/14.0" in tier1


class TestAdaptiveThresholdBounds:
    def test_threshold_moves_at_most_one_point(self, example_settings):
        policy = AdaptiveRiskPolicy(example_settings)
        base = policy.base_min_confluence
        assert policy._clamp_threshold(base - 1) == base - 1
        assert policy._clamp_threshold(base + 1) == base + 1
        assert policy._clamp_threshold(base - 5) == base - 1
        assert policy._clamp_threshold(base + 5) == base + 1

    def test_bounds_follow_the_configured_base(self):
        policy = AdaptiveRiskPolicy({"trading": {"auto_execute_min_confluence": 5}})
        assert policy.base_min_confluence == 5
        assert policy._clamp_threshold(4) == 4
        assert policy._clamp_threshold(6) == 6
        assert policy._clamp_threshold(99) == 6
        assert policy._clamp_threshold(0) == 4

    def test_default_base_comes_from_canonical_constant(self):
        policy = AdaptiveRiskPolicy({})
        assert policy.base_min_confluence == DEFAULT_AUTO_EXECUTE_MIN_CONFLUENCE
