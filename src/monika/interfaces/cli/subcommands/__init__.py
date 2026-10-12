# ==============================================================================
# File: cli/subcommands/__init__.py
# ==============================================================================

"""
Subcommands Registry for Monika Modular CLI.
"""

from typing import Dict, List
from monika.interfaces.cli.subcommands.base import Subcommand
from monika.interfaces.cli.subcommands.daemon import DaemonSubcommand
from monika.interfaces.cli.subcommands.trading import TradingSubcommand
from monika.interfaces.cli.subcommands.simulation import SimulationSubcommand
from monika.interfaces.cli.subcommands.mcp import McpSubcommand
from monika.interfaces.cli.subcommands.runcard import RunCardSubcommand
from monika.interfaces.cli.subcommands.upgrade import UpgradeSubcommand

AVAILABLE_SUBCOMMANDS: List[Subcommand] = [
    DaemonSubcommand(),
    TradingSubcommand(),
    SimulationSubcommand(),
    McpSubcommand(),
    RunCardSubcommand(),
    UpgradeSubcommand(),
]
