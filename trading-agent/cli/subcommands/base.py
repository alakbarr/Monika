# ==============================================================================
# File: cli/subcommands/base.py
# ==============================================================================

"""
Base Protocol for Modular CLI Subcommands in Monika.
Each subcommand group manages its own argument parsing and execution pipeline.
"""

import argparse
from abc import ABC, abstractmethod
from typing import Any, Optional


class Subcommand(ABC):
    """Abstract base class for modular CLI subcommand groups."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        """Register argument parser flags and subcommands."""
        pass

    @abstractmethod
    async def execute(self, args: argparse.Namespace) -> int:
        """Asynchronously execute subcommand. Return exit code (0 for success)."""
        pass
