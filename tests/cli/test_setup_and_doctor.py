"""
Unit tests for SetupWizard and SystemDoctor enhancements.
"""

import pytest
from unittest.mock import MagicMock, patch
from cli.doctor import SystemDoctor
from cli.main import MonikaArgumentParser


def test_monika_argument_parser_fuzzy_suggestions(capsys):
    parser = MonikaArgumentParser()
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor")
    sub.add_parser("positions")
    sub.add_parser("status")

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["docter"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "Did you mean: doctor?" in captured.err


@pytest.mark.asyncio
async def test_system_doctor_offline_probes():
    doctor = SystemDoctor(fix=False, live_probes=False, verbose=False)
    diagnostics = await doctor.run_diagnostics()

    categories = {d.category for d in diagnostics}
    assert "Filesystem" in categories
    assert "Dependencies" in categories
    assert "Market" in categories
    assert "Config" in categories
    assert "Credentials" in categories
    assert "MT5" in categories

    # Database live probes should be skipped when live_probes is False
    assert "Database" not in categories


def test_setup_wizard_clean_terminal_input():
    from cli.setup_wizard import clean_terminal_input
    assert clean_terminal_input("  normal_input  ") == "normal_input"
    # Bracketed paste sequence
    pasted = "\x1b[200~pasted_token_12345\x1b[201~"
    assert clean_terminal_input(pasted) == "pasted_token_12345"


def test_setup_wizard_missing_items():
    from cli.setup_wizard import SetupWizard
    missing = SetupWizard.get_missing_setup_items()
    assert "mt5" in missing
    assert "db" in missing
    assert "llm" in missing


def test_setup_wizard_headless_guard():
    from cli.setup_wizard import SetupWizard
    wizard = SetupWizard()
    with patch("sys.stdin.isatty", return_value=False):
        res = wizard.run_wizard()
        assert res is False
