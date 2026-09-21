"""
Unit tests for Pydantic Configuration Schemas (H6) and Modular Split (I8).
"""
import pytest
import tempfile
import os
import yaml
from pydantic import ValidationError
from config.schemas import RiskConfig, TradingAgentConfig, HarnessConfig, EvalsConfig, BenchmarkConfig
from config.settings import _deep_merge, load_settings, validate_config


def test_h6_risk_config_valid_bounds():
    """H6: Valid risk parameters pass schema validation."""
    valid_data = {
        "max_daily_drawdown_percent": 3.0,
        "max_weekly_drawdown_percent": 6.0,
        "max_concurrent_positions": 5,
        "max_portfolio_heat_pct": 4.0,
        "min_rr_ratio": 1.5,
    }
    cfg = RiskConfig.model_validate(valid_data)
    assert cfg.max_daily_drawdown_percent == 3.0
    assert cfg.min_rr_ratio == 1.5


def test_h6_risk_config_invalid_bounds_rejected():
    """H6: Out-of-bounds risk parameters raise ValidationError."""
    # Drawdown too extreme (> 15%)
    with pytest.raises(ValidationError):
        RiskConfig.model_validate({"max_daily_drawdown_percent": 25.0})

    # Drawdown too small (< 0.5%)
    with pytest.raises(ValidationError):
        RiskConfig.model_validate({"max_daily_drawdown_percent": 0.1})

    # Risk-reward too low (< 0.5)
    with pytest.raises(ValidationError):
        RiskConfig.model_validate({"min_rr_ratio": 0.2})


def test_h6_trading_agent_config_nested_validation():
    """H6: TradingAgentConfig automatically validates nested trading.risk dictionary."""
    valid_settings = {
        "app_name": "AI Trading Agent",
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 4.0,
                "min_rr_ratio": 2.0,
            }
        }
    }
    validated = validate_config(valid_settings)
    assert validated.app_name == "AI Trading Agent"

    # Invalid nested risk must fail
    invalid_settings = {
        "trading": {
            "risk": {
                "max_daily_drawdown_percent": 50.0  # Violates <= 15.0
            }
        }
    }
    with pytest.raises(ValueError):
        validate_config(invalid_settings)


def test_i8_deep_merge():
    """I8: _deep_merge merges nested dicts properly without overwriting unmentioned keys."""
    base = {
        "trading": {
            "cost_mode": "standard",
            "risk": {"max_daily_drawdown_percent": 3.0, "max_concurrent_positions": 5}
        },
        "llm": {"providers": {"openai": {"enabled": True}}}
    }
    overlay = {
        "trading": {
            "risk": {"max_daily_drawdown_percent": 4.5}  # Override one field
        },
        "scheduler": {"news_check_minutes": 10}
    }
    merged = _deep_merge(base, overlay)
    assert merged["trading"]["cost_mode"] == "standard"
    assert merged["trading"]["risk"]["max_concurrent_positions"] == 5
    assert merged["trading"]["risk"]["max_daily_drawdown_percent"] == 4.5
    assert merged["scheduler"]["news_check_minutes"] == 10
    assert merged["llm"]["providers"]["openai"]["enabled"] is True


def test_i8_modular_split_loading():
    """I8: load_settings merges modular split files (e.g. risk.yaml) if present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        main_yaml = os.path.join(tmpdir, "settings.yaml")
        risk_yaml = os.path.join(tmpdir, "risk.yaml")

        with open(main_yaml, "w", encoding="utf-8") as f:
            yaml.dump({"app_name": "Split Test", "trading": {"risk": {"max_concurrent_positions": 2}}}, f)

        # Modular risk.yaml overrides max_daily_drawdown_percent
        with open(risk_yaml, "w", encoding="utf-8") as f:
            yaml.dump({"max_daily_drawdown_percent": 5.0}, f)

        settings = load_settings(main_yaml, validate=True)
        assert settings["app_name"] == "Split Test"
        assert settings["trading"]["risk"]["max_concurrent_positions"] == 2
        assert settings["trading"]["risk"]["max_daily_drawdown_percent"] == 5.0


def test_m3_m4_complete_schemas_and_return_model():
    """M-3 & M-4: Schemas validate execution, indicators, trading, and return_model works."""
    raw_data = {
        "app_name": "Full Schema Test",
        "execution": {
            "max_price_staleness_seconds": 90,
            "adapter_type": "live",
        },
        "indicators": {
            "rsi_period": 14,
            "bollinger_std": 2.5,
        },
        "trading": {
            "auto_execute": False,
            "min_paper_win_rate_pct": 60.0,
            "risk": {
                "max_daily_drawdown_percent": 3.5,
            }
        }
    }
    model = validate_config(raw_data)
    assert isinstance(model, TradingAgentConfig)
    assert model.execution.max_price_staleness_seconds == 90
    assert model.indicators.bollinger_std == 2.5
    assert model.trading.min_paper_win_rate_pct == 60.0

    # Invalid execution staleness (< 5s) must fail
    with pytest.raises(ValueError):
        validate_config({"execution": {"max_price_staleness_seconds": 1}})


def test_subscriptable_config_dict_mapping_parity():
    """Verify SubscriptableConfig provides complete dict-like mapping access."""
    data = {
        "max_daily_drawdown_percent": 3.5,
        "max_weekly_drawdown_percent": 7.0,
        "custom_extra_key": "active_val"
    }
    cfg = RiskConfig.model_validate(data)
    assert cfg["max_daily_drawdown_percent"] == 3.5
    assert cfg.get("max_weekly_drawdown_percent") == 7.0
    assert cfg.get("non_existent", "fallback") == "fallback"
    assert "max_daily_drawdown_percent" in cfg
    assert "custom_extra_key" in cfg
    assert "totally_missing" not in cfg

    # Test keys, values, items
    keys = cfg.keys()
    assert "max_daily_drawdown_percent" in keys
    assert "custom_extra_key" in keys

    items = dict(cfg.items())
    assert items["max_daily_drawdown_percent"] == 3.5
    assert items["custom_extra_key"] == "active_val"
    assert len(cfg.values()) == len(keys)


def test_harness_evals_benchmark_schemas():
    """Verify HarnessConfig, EvalsConfig, and BenchmarkConfig validation and integration."""
    harness = HarnessConfig.model_validate({
        "compaction_cooldown_seconds": 60.0,
        "max_context_chars": 50000,
        "retain_recent_turns": 3,
    })
    assert harness.compaction_cooldown_seconds == 60.0
    assert harness.max_context_chars == 50000
    assert harness.retain_recent_turns == 3

    evals = EvalsConfig.model_validate({"simulation_clock_enabled": False})
    assert evals.simulation_clock_enabled is False

    benchmark = BenchmarkConfig.model_validate({"max_drift_pct": 20.0})
    assert benchmark.max_drift_pct == 20.0

    # Integration via TradingAgentConfig
    raw = {
        "app_name": "TestHarnessApp",
        "harness": {"compaction_cooldown_seconds": 90.0},
        "evals": {"simulation_clock_enabled": True},
        "benchmark": {"max_drift_pct": 12.5},
    }
    validated = validate_config(raw)
    assert validated.harness.compaction_cooldown_seconds == 90.0
    assert validated.evals.simulation_clock_enabled is True
    assert validated.benchmark.max_drift_pct == 12.5

    # Test invalid constraints
    with pytest.raises(ValidationError):
        HarnessConfig.model_validate({"max_context_chars": 100})  # < 1000

    with pytest.raises(ValidationError):
        BenchmarkConfig.model_validate({"max_drift_pct": -5.0})  # < 0.0



