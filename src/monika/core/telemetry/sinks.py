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
        related_id: int | None = None,
        actor: str = "system",
        session: Any = None,
    ) -> int | None:
        """Persist an activity log entry."""
        ...

    async def persist_spans(self, spans: list[Any]) -> None:
        """Persist evicted tracing spans."""
        ...


class TelemetrySinkRegistry:
    """Centralized, resettable registry for telemetry sink."""

    default_sink: TelemetrySink | None = None

    @classmethod
    def set(cls, sink: TelemetrySink | None) -> None:
        cls.default_sink = sink

    @classmethod
    def get(cls) -> TelemetrySink | None:
        return cls.default_sink

    @classmethod
    def reset(cls) -> None:
        cls.default_sink = None


def set_telemetry_sink(sink: TelemetrySink | None) -> None:
    """Set the active global telemetry sink."""
    TelemetrySinkRegistry.set(sink)


def get_telemetry_sink() -> TelemetrySink | None:
    """Get the active global telemetry sink, or None."""
    return TelemetrySinkRegistry.get()
