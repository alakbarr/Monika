"""
Unit tests for fuzzy configuration key validation.
"""

from config.key_validator import validate_config_key


def test_validate_config_key_valid():
    assert validate_config_key("trading.cost_mode") is None
    assert validate_config_key("risk.max_daily_drawdown_percent") is None
    assert validate_config_key("llm.providers") is None
    assert validate_config_key("scheduler.cycle_interval_hours") is None


def test_validate_config_key_typo_suggests_match():
    err = validate_config_key("tradin.cost_mode")
    assert err is not None
    assert "Did you mean: trading" in err

    err2 = validate_config_key("riskk.max_loss")
    assert err2 is not None
    assert "Did you mean: risk" in err2


def test_validate_config_key_empty():
    assert validate_config_key("") is not None
