"""Session surface maintaining an append-only event log and KV-cache-preserving active nodes.

Provides the core KV-cache-preserving session surface architecture:
- Append-only event log with active node pointers.
- Strictly validated rewrite assertions for system prompts and tool results.
- Efficient incremental derivation of model messages.
- Stable projections for system prompt updates, runtime context reminders, and throttled time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from typing import Any, Literal, TypedDict

SurfaceEventType = Literal[
    "system/message",
    "developer/message",
    "user/message",
    "assistant/message",
    "tool/result",
    "assistant/attempt",
    "tool/call",
    "turn/start",
    "turn/end",
    "step/start",
    "step/end",
    "compaction/prune",
    "compaction/summary",
]

SURFACE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "system/message",
        "developer/message",
        "user/message",
        "assistant/message",
        "tool/result",
    }
)


class ReplaceOp(TypedDict):
    op: Literal["replace"]
    start_seq: int
    end_seq: int


SurfaceOp = Literal["append"] | ReplaceOp


def deep_freeze_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied message dict so caller mutations cannot corrupt stored surface messages."""
    return copy.deepcopy(msg)


@dataclass(frozen=True, slots=True)
class SurfaceEvent:
    seq: int
    event_type: SurfaceEventType
    message: dict[str, Any] | None
    surface_op: str | dict[str, Any] | None
    source_event_seqs: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionSurface:
    """Append-only session surface with KV-cache-preserving active node list."""

    def __init__(self) -> None:
        self._log: list[SurfaceEvent] = []
        self._nodes: list[int] = []
        self._event_by_seq: dict[int, SurfaceEvent] = {}
        self.replace_generation: int = 0
        self.content_generation: int = 0
        self._cached_messages: list[dict[str, Any]] = []
        self._cached_content_generation: int = -1
        self._cached_derived_count: int = 0

    @property
    def log(self) -> list[SurfaceEvent]:
        return list(self._log)

    @property
    def nodes(self) -> list[int]:
        return list(self._nodes)

    def get_event(self, seq: int) -> SurfaceEvent | None:
        return self._event_by_seq.get(seq)

    def append_event(
        self,
        event_type: SurfaceEventType,
        message: dict[str, Any] | None = None,
        surface_op: str | dict[str, Any] | None = "append",
        source_event_seqs: tuple[int, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> SurfaceEvent:
        seq = len(self._log) + 1
        frozen_msg = deep_freeze_message(message) if message is not None else None
        meta = dict(metadata) if metadata is not None else {}

        # Non-surface events never enter active nodes and carry surface_op=None
        if event_type not in SURFACE_EVENT_TYPES:
            event = SurfaceEvent(
                seq=seq,
                event_type=event_type,
                message=frozen_msg,
                surface_op=None,
                source_event_seqs=source_event_seqs,
                metadata=meta,
            )
            self._log.append(event)
            self._event_by_seq[seq] = event
            return event

        if surface_op == "append" or surface_op is None:
            event = SurfaceEvent(
                seq=seq,
                event_type=event_type,
                message=frozen_msg,
                surface_op="append",
                source_event_seqs=source_event_seqs,
                metadata=meta,
            )
            self._log.append(event)
            self._event_by_seq[seq] = event
            self._nodes.append(seq)
            return event

        if isinstance(surface_op, dict) and surface_op.get("op") == "replace":
            start_seq_val = surface_op.get("start_seq")
            end_seq_val = surface_op.get("end_seq")
            if not isinstance(start_seq_val, int) or not isinstance(end_seq_val, int):
                raise ValueError("Replace operation must define integer start_seq and end_seq.")

            if start_seq_val not in self._nodes:
                raise ValueError(f"start_seq {start_seq_val} is not an active surface node.")
            if end_seq_val not in self._nodes:
                raise ValueError(f"end_seq {end_seq_val} is not an active surface node.")

            start_idx = self._nodes.index(start_seq_val)
            end_idx = self._nodes.index(end_seq_val)
            if start_idx > end_idx:
                raise ValueError(
                    f"Invalid replace range: start_seq {start_seq_val} appears after end_seq {end_seq_val}."
                )

            # Enforce assert_system_head_rewrite:
            # if nodes[0] is a system/message, any replace covering nodes[0] MUST be a system/message
            # replacing nodes[0] alone (start_seq == end_seq == nodes[0]).
            if len(self._nodes) > 0:
                node_0_seq = self._nodes[0]
                node_0_event = self._event_by_seq[node_0_seq]
                if node_0_event.event_type == "system/message":
                    if start_idx == 0:
                        if event_type != "system/message":
                            raise ValueError(
                                f"Invalid surface rewrite: node 0 is a system/message and cannot be replaced by '{event_type}'."
                            )
                        if start_seq_val != node_0_seq or end_seq_val != node_0_seq:
                            raise ValueError(
                                "Invalid surface rewrite: system/message head replace must replace node 0 alone (start_seq == end_seq == nodes[0])."
                            )

            # Enforce assert_tool_result_rewrite:
            # if event_type == "tool/result" with op == "replace", it must replace a single tool/result node (start_seq == end_seq).
            if event_type == "tool/result":
                if start_seq_val != end_seq_val:
                    raise ValueError(
                        "Invalid surface rewrite: tool/result replacement must target a single node (start_seq == end_seq)."
                    )
                target_event = self._event_by_seq[start_seq_val]
                if target_event.event_type != "tool/result":
                    raise ValueError(
                        f"Invalid surface rewrite: tool/result cannot replace a node of type '{target_event.event_type}'."
                    )

            event = SurfaceEvent(
                seq=seq,
                event_type=event_type,
                message=frozen_msg,
                surface_op=surface_op,
                source_event_seqs=source_event_seqs,
                metadata=meta,
            )
            self._log.append(event)
            self._event_by_seq[seq] = event
            self._nodes[start_idx : end_idx + 1] = [seq]
            self.replace_generation += 1
            self.content_generation += 1
            return event

        raise ValueError(f"Unsupported surface_op: {surface_op}")

    def derive_messages(self, include_system: bool = False) -> list[dict[str, Any]]:
        """Incrementally derive model-visible messages in O(new nodes) when content_generation hasn't changed."""
        if self.content_generation != self._cached_content_generation:
            self._cached_messages = []
            for node_seq in self._nodes:
                ev = self._event_by_seq[node_seq]
                if ev.message is not None:
                    self._cached_messages.append(ev.message)
            self._cached_content_generation = self.content_generation
            self._cached_derived_count = len(self._nodes)
        else:
            if len(self._nodes) > self._cached_derived_count:
                for node_seq in self._nodes[self._cached_derived_count :]:
                    ev = self._event_by_seq[node_seq]
                    if ev.message is not None:
                        self._cached_messages.append(ev.message)
                self._cached_derived_count = len(self._nodes)

        out: list[dict[str, Any]] = []
        for msg in self._cached_messages:
            if not include_system and msg.get("role") == "system":
                continue
            out.append(copy.deepcopy(msg))
        return out


class SystemPromptProjection:
    """Manages system/message placement on SessionSurface preserving KV cache prefixes."""

    def __init__(
        self,
        surface: SessionSurface,
        starts_series: bool = False,
        in_history: bool = True,
    ) -> None:
        self.surface = surface
        self.starts_series = starts_series
        self.in_history = in_history

    def update_system_prompt(
        self,
        content: str | dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> SurfaceEvent:
        if isinstance(content, str):
            msg = {"role": "system", "content": content}
        else:
            msg = dict(content)

        active_nodes = self.surface.nodes
        has_node_0 = len(active_nodes) > 0
        if has_node_0:
            node_0_seq = active_nodes[0]
            node_0_ev = self.surface.get_event(node_0_seq)
            is_node_0_system = node_0_ev is not None and node_0_ev.event_type == "system/message"
        else:
            node_0_seq = None
            is_node_0_system = False

        if is_node_0_system and self.in_history and not self.starts_series:
            # Mid-session system prompt update: append at tail to preserve KV cache prefix
            return self.surface.append_event(
                event_type="system/message",
                message=msg,
                surface_op="append",
                metadata=metadata,
            )
        elif is_node_0_system and (self.starts_series or not self.in_history) and node_0_seq is not None:
            # Rewrite Node 0
            return self.surface.append_event(
                event_type="system/message",
                message=msg,
                surface_op={"op": "replace", "start_seq": node_0_seq, "end_seq": node_0_seq},
                metadata=metadata,
            )
        else:
            return self.surface.append_event(
                event_type="system/message",
                message=msg,
                surface_op="append",
                metadata=metadata,
            )


class RuntimeContextProjection:
    """Renders dynamic runtime context sections into a tail user message with SHA-1 deduplication."""

    def __init__(self) -> None:
        self.retained_digest: str | None = None
        self.retained_text: str | None = None
        self._last_replace_generation: int = 0

    def project(self, sections: dict[str, str]) -> dict[str, Any] | None:
        non_empty = {k: v.strip() for k, v in sorted(sections.items()) if v and v.strip()}
        if not non_empty:
            return None

        lines = ['<system-reminder type="runtime-context">']
        for k, v in non_empty.items():
            lines.append(f"<{k}>\n{v}\n</{k}>")
        lines.append("</system-reminder>")
        rendered_text = "\n".join(lines)

        digest = hashlib.sha1(rendered_text.encode("utf-8")).hexdigest()
        if digest == self.retained_digest:
            return None

        self.retained_digest = digest
        self.retained_text = rendered_text
        return {"role": "user", "content": rendered_text}

    def reset_on_compaction(self, replace_generation: int) -> None:
        """Clear retained digest when compaction replaces nodes so next step re-emits context if needed."""
        if replace_generation > self._last_replace_generation:
            self.retained_digest = None
            self.retained_text = None
            self._last_replace_generation = replace_generation


class ThrottledTimeContext:
    """Throttles wall-clock time snapshots to avoid unnecessary KV cache invalidations."""

    def __init__(self, refresh_interval_seconds: float = 600.0) -> None:
        self.refresh_interval_seconds = refresh_interval_seconds
        self.last_injection_ts: float | None = None

    def project(
        self,
        now_ts: float | None = None,
        as_of_iso: str | None = None,
    ) -> dict[str, Any] | None:
        current_ts = datetime.now(UTC).timestamp() if now_ts is None else now_ts
        if self.last_injection_ts is not None and (current_ts - self.last_injection_ts) < self.refresh_interval_seconds:
            return None

        self.last_injection_ts = current_ts
        if as_of_iso is None:
            as_of_iso = datetime.fromtimestamp(current_ts, tz=UTC).isoformat()

        return {
            "role": "user",
            "content": f'<system-reminder type="time-context">Current time: {as_of_iso}</system-reminder>',
        }
