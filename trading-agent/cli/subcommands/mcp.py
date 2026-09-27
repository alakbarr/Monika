# ==============================================================================
# File: cli/subcommands/mcp.py
# ==============================================================================

"""
MCP Server Subcommand for Monika.
Exposes Monika trading capabilities to external MCP clients (Cursor, Claude Desktop, Antigravity).
"""

import argparse
from cli.subcommands.base import Subcommand


class McpSubcommand(Subcommand):
    name = "mcp"
    description = "Expose Monika as a Model Context Protocol (MCP) server."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        if "mcp" in subparsers.choices:
            return subparsers.choices["mcp"]
        parser = subparsers.add_parser("mcp", help="Start Monika MCP stdio server.")
        parser.add_argument("--config", default=None, help="Custom settings YAML path.")
        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        from analysis.mcp.dispatcher import MonikaMcpDispatcher
        from config.settings import load_settings
        
        cfg = load_settings(getattr(args, "config", None))
        dispatcher = MonikaMcpDispatcher(settings=cfg)
        await dispatcher.run_stdio()
        return 0
