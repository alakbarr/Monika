"""
Abstract Telemetry Sinks for decoupled observability.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class TelemetrySink(Protocol):
    """Protocol for decoupled telemetry and span persistence."""

    async def persist_activity(
        self,
        category: str,
        description: str,
        related_id: Optional[int] = None,
        actor: str = "system",
        session: Any = None,
    ) -> Optional[int]:
        """Persist an activity log entry."""
        ...

    async def persist_spans(self, spans: List[Any]) -> None:
        """Persist evicted tracing spans."""
        ...


_DEFAULT_SINK: Optional[TelemetrySink] = None


def set_telemetry_sink(sink: Optional[TelemetrySink]) -> None:
    """Set the active global telemetry sink."""
    global _DEFAULT_SINK
    _DEFAULT_SINK = sink


def get_telemetry_sink() -> Optional[TelemetrySink]:
    """Get the active global telemetry sink, or None."""
    return _DEFAULT_SINK
