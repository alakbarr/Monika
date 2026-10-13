# ==============================================================================
# Package: monika.interfaces.dashboard
# File: pty_bridge.py
# ==============================================================================

"""
PTY Console Bridge (Interfaces Facade).
Re-exports canonical PTY bridge components from infrastructure.sandboxes.pty_bridge.
Preserves full backward compatibility for existing dashboard callers.
"""

from __future__ import annotations

from monika.infrastructure.sandboxes.pty_bridge import (
    PtyBridgeManager,
    PtySession,
    get_pty_bridge_manager,
)

__all__ = [
    "PtySession",
    "PtyBridgeManager",
    "get_pty_bridge_manager",
]
