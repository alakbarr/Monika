"""
Test suite for ConfigManager, Security Guards, and TraderOnboarding.
"""

import os
import json
import pytest
from pathlib import Path
from config.security import validate_env_mutation, BLOCKED_ENV_VARS
from config.config_manager import ConfigManager
from cli.onboarding_trader import TraderProfile, TraderOnboarding
from cli.setup_wizard import SetupWizard


def test_security_blocked_env_vars():
    for blocked in BLOCKED_ENV_VARS:
        with pytest.raises(ValueError, match="dilarang demi keamanan"):
            validate_env_mutation(blocked)
        with pytest.raises(ValueError, match="dilarang demi keamanan"):
            validate_env_mutation(blocked.lower())

    # Safe vars should pass
    validate_env_mutation("MT5_ACCOUNT")
    validate_env_mutation("TELEGRAM_BOT_TOKEN")


def test_config_manager_pub_sub():
    received = []

    def _on_risk_update(payload):
        received.append(payload)

    ConfigManager.subscribe("risk", _on_risk_update)
    ConfigManager.publish("risk", {"max_daily_drawdown_percent": 3.5})

    assert len(received) == 1
    assert received[0]["max_daily_drawdown_percent"] == 3.5


def test_trader_onboarding_persistence(tmp_path):
    onboarding = TraderOnboarding(base_dir=str(tmp_path))
    profile = TraderProfile(
        trader_name="TestTrader",
        trading_style="day_trader",
        risk_appetite="moderate",
        risk_pct_per_trade=1.0,
        max_daily_loss_pct=3.0,
        primary_symbols=["XAUUSD", "EURUSD"],
        session_focus=["London", "New York"]
    )

    onboarding.save_profile(profile)
    loaded = onboarding.load_profile()
    assert loaded is not None
    assert loaded.trader_name == "TestTrader"
    assert loaded.primary_symbols == ["XAUUSD", "EURUSD"]

    onboarding.sync_to_trading_soul(profile)
    soul_content = onboarding.soul_file.read_text(encoding="utf-8")
    assert "TestTrader" in soul_content
    assert "XAUUSD, EURUSD" in soul_content


def test_setup_wizard_missing_items():
    missing = SetupWizard.get_missing_setup_items()
    assert isinstance(missing, dict)
    assert "mt5" in missing
    assert "db" in missing
    assert "llm" in missing
