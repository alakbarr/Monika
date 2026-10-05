# ==============================================================================
# File: tests/test_installation_tiers.py
# ==============================================================================

import pytest
import os
from config.settings import get_installation_tier
from config.schemas import TradingAgentConfig
from cli.subcommands.upgrade import UpgradeSubcommand
from cli.setup_wizard import SetupWizard
from cli.doctor import SystemDoctor


def test_schema_installation_tier():
    """Verify TradingAgentConfig accepts and defaults installation_tier properly."""
    cfg = TradingAgentConfig(installation_tier="trial")
    assert cfg.installation_tier == "trial"

    cfg_full = TradingAgentConfig(installation_tier="full")
    assert cfg_full.installation_tier == "full"

    # Default should be trial
    cfg_default = TradingAgentConfig()
    assert cfg_default.installation_tier == "trial"


def test_get_installation_tier_helper():
    """Verify get_installation_tier extracts correctly from dict or defaults."""
    assert get_installation_tier({"installation_tier": "full"}) == "full"
    assert get_installation_tier({"installation_tier": "trial"}) == "trial"
    assert get_installation_tier({}) == "trial"
    assert get_installation_tier(None) in ("trial", "full", "unconfigured")


def test_upgrade_subcommand_registration():
    """Verify UpgradeSubcommand implements the Subcommand protocol properly."""
    cmd = UpgradeSubcommand()
    assert cmd.name == "upgrade"
    assert "upgrade" in cmd.description.lower()

    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    subp = cmd.register_subparser(subparsers)
    assert subp is not None

    parsed = parser.parse_args(["upgrade", "--yes", "--skip-npm"])
    assert parsed.yes is True
    assert parsed.skip_npm is True
    assert parsed.command == "upgrade"


def test_setup_wizard_detection_helpers():
    """Verify MT5 and 9router detection helpers return valid types without crashing."""
    mt5_path = SetupWizard.detect_mt5_path()
    assert mt5_path is None or isinstance(mt5_path, str)

    router_info = SetupWizard.detect_9router_status()
    assert isinstance(router_info, dict)
    assert "node" in router_info
    assert "npx" in router_info
    assert "router_installed" in router_info
    assert "running" in router_info


def test_doctor_tier_aware_dependencies():
    """Verify SystemDoctor runs check_dependencies with tier awareness without failing."""
    doc = SystemDoctor(fix=False, live_probes=False, verbose=False)
    doc.check_dependencies({"installation_tier": "trial"})
    # Ensure items were recorded
    assert len(doc.diagnostics) >= 2
    for diag in doc.diagnostics:
        assert diag.category == "Dependencies"
