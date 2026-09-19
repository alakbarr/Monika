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
