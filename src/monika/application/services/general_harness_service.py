# ==============================================================================
# Package: monika.application.services
# File: general_harness_service.py
# ==============================================================================

"""
General Harness Application Service.
Provides general-purpose agent harness workflows, safe sandboxed terminal execution,
and modular tool orchestration (TRADING, DEVELOPER, RESEARCH).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from monika.application.analysis.tools.unified_registry import (
    unified_tool_registry,
    TRADING_TOOLSET,
    DEVELOPER_TOOLSET,
    RESEARCH_TOOLSET,
    TOOLSETS,
)
from monika.interfaces.dashboard.pty_bridge import get_pty_bridge_manager, PtySession

logger = logging.getLogger("Monika.Application.GeneralHarnessService")


class GeneralHarnessService:
    """Canonical Application Service managing multi-purpose harness and execution environments."""

    @classmethod
    async def create_terminal_session(
        cls,
        session_id: Optional[str] = None,
        cols: int = 80,
        rows: int = 24,
    ) -> PtySession:
        """Create or retrieve a safe, TerminalGuard-inspected interactive PTY terminal session."""
        mgr = get_pty_bridge_manager()
        return await mgr.get_or_create_session(session_id=session_id, cols=cols, rows=rows)

    @classmethod
    async def close_terminal_session(cls, session_id: str) -> bool:
        """Terminate and clean up active terminal session."""
        mgr = get_pty_bridge_manager()
        return await mgr.close_session(session_id)

    @classmethod
    async def dispatch_tool(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Any = None,
    ) -> str:
        """Execute tool through centralized UnifiedToolRegistry with security interceptors."""
        return await unified_tool_registry.dispatch(
            name=tool_name,
            arguments=arguments,
            context=context,
        )

    @classmethod
    def get_toolset_schema(
        cls,
        toolset: str,
        format: str = "openai",
    ) -> List[Dict[str, Any]]:
        """Return serialized tool schemas for specified toolset ('TRADING', 'DEVELOPER', 'RESEARCH')."""
        return unified_tool_registry.get_toolset(toolset=toolset, format=format)

    @classmethod
    def get_toolset_names(cls, toolset: str) -> List[str]:
        """Return list of tool names belonging to toolset."""
        return unified_tool_registry.list_toolset_names(toolset=toolset)
