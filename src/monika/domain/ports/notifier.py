# ==============================================================================
# File: domain/ports/notifier.py
# ==============================================================================

"""
Domain Notifier Port.

Defines pure abstract interfaces for alert broadcasting, trade notifications,
and critical system warning dispatches (Dependency Inversion Principle).
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class NotifierPort(Protocol):
    """Standardized pure domain protocol for outgoing notifications and alerts."""

    async def send_message(self, message: str) -> None:
        """Send raw broadcast message."""
        ...

    async def send_info(self, message: str) -> None:
        """Send informational notification."""
        ...

    async def send_warning(self, message: str) -> None:
        """Send warning notification."""
        ...

    async def send_critical(self, message: str) -> None:
        """Send critical emergency alert."""
        ...
