# ==============================================================================
# File: cli/subcommands/__init__.py
# ==============================================================================

"""
Subcommands Registry for Monika Modular CLI.
"""

from typing import Dict, List
from cli.subcommands.base import Subcommand
from cli.subcommands.daemon import DaemonSubcommand
from cli.subcommands.trading import TradingSubcommand
from cli.subcommands.simulation import SimulationSubcommand
from cli.subcommands.mcp import McpSubcommand
from cli.subcommands.runcard import RunCardSubcommand
from cli.subcommands.upgrade import UpgradeSubcommand

AVAILABLE_SUBCOMMANDS: List[Subcommand] = [
    DaemonSubcommand(),
    TradingSubcommand(),
    SimulationSubcommand(),
    McpSubcommand(),
    RunCardSubcommand(),
    UpgradeSubcommand(),
]
