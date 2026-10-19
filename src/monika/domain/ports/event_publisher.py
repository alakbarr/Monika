# ==============================================================================
# File: domain/ports/event_publisher.py
# ==============================================================================

"""
Domain Event Publisher Port.

Defines pure abstract interfaces for publishing and emitting domain events.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisherPort(Protocol):
    """Protocol for emitting audit, telemetry, and business events."""

    async def emit(
        self,
        session: Any,
        event_type: str,
        payload: dict[str, Any],
        source: str = "risk_gate",
    ) -> Any:
        """Emit a domain or system event."""
        ...
