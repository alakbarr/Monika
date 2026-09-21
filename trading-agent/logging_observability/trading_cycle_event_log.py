"""
Monotonic Event-Sourced Trading Cycle Log and Decision Lineage Tracing (Phase 7.1 & 7.2).
Provides append-only, structurally-typed, contiguous-sequence event logging per trading cycle,
enabling exact cycle replay and recursive provenance tracing from orders to signals.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("TradingAgent.TradingCycleEventLog")


class CycleEventType:
    CYCLE_START = "cycle/start"
    STAGE_FUNDAMENTAL = "stage/fundamental"
    STAGE_PER_ASSET = "stage/per_asset"
    STAGE_DEBATE = "stage/debate"
    RISK_GATE_CHECK = "risk/gate_check"
    ORDER_DISPATCH = "order/dispatch"
    ORDER_FILL = "order/fill"
    OPERATOR_FEEDBACK = "operator/feedback"
    CYCLE_END = "cycle/end"


@dataclass
class CycleEvent:
    seq: int
    cycle_id: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source_event_seqs: List[int] = field(default_factory=list)  # Lineage tracing pointers (Phase 7.2)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradingCycleEventLog:
    """Append-only monotonic event-sourced store for trading cycles."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/cycle_events")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # In-memory index: cycle_id -> list of CycleEvent
        self._cycle_stores: Dict[str, List[CycleEvent]] = {}
        self._cycle_counters: Dict[str, int] = {}

    def record_event(
        self,
        cycle_id: str,
        event_type: str,
        payload: Dict[str, Any],
        source_event_seqs: Optional[List[int]] = None,
    ) -> CycleEvent:
        """Record an event with contiguous monotonic sequence numbering for the cycle."""
        cid = str(cycle_id or "default_cycle")
        if cid not in self._cycle_counters:
            self._cycle_counters[cid] = 0
            self._cycle_stores[cid] = []

        self._cycle_counters[cid] += 1
        seq = self._cycle_counters[cid]

        event = CycleEvent(
            seq=seq,
            cycle_id=cid,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=payload,
            source_event_seqs=list(source_event_seqs or []),
        )
        self._cycle_stores[cid].append(event)

        # Persist append-only to disk JSONL
        try:
            log_file = self.storage_dir / f"{cid}.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"[EventLog] Failed to persist event {seq} for cycle {cid}: {e}")

        return event

    def get_events_for_cycle(self, cycle_id: str) -> List[CycleEvent]:
        """Return all contiguous events for a given cycle."""
        cid = str(cycle_id)
        if cid in self._cycle_stores:
            return list(self._cycle_stores[cid])

        # Load from disk if available
        log_file = self.storage_dir / f"{cid}.jsonl"
        events = []
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            events.append(CycleEvent(**data))
            except Exception as e:
                logger.error(f"[EventLog] Failed loading cycle log {cid}: {e}")
            self._cycle_stores[cid] = events
            self._cycle_counters[cid] = len(events)
        return events

    def trace_decision_lineage(self, cycle_id: str, target_seq: int) -> List[CycleEvent]:
        """
        Recursively trace ancestor events that influenced target_seq (Phase 7.2 Provenance).
        Answers: 'Which signal or debate argument triggered this order?'
        """
        events = self.get_events_for_cycle(cycle_id)
        seq_map = {e.seq: e for e in events}

        if target_seq not in seq_map:
            return []

        lineage: List[CycleEvent] = []
        visited: Set[int] = set()

        def _traverse(seq: int):
            if seq in visited or seq not in seq_map:
                return
            visited.add(seq)
            ev = seq_map[seq]
            lineage.append(ev)
            for parent_seq in ev.source_event_seqs:
                _traverse(parent_seq)

        _traverse(target_seq)
        lineage.sort(key=lambda x: x.seq)
        return lineage

    def reconstruct_cycle(self, cycle_id: str) -> Dict[str, Any]:
        """Replay full cycle state from origin sequence."""
        events = self.get_events_for_cycle(cycle_id)
        return {
            "cycle_id": cycle_id,
            "total_events": len(events),
            "events": [e.to_dict() for e in events],
            "start_time": events[0].timestamp if events else None,
            "end_time": events[-1].timestamp if events else None,
        }


# Global default instance
_default_event_log: Optional[TradingCycleEventLog] = None


def get_cycle_event_log() -> TradingCycleEventLog:
    """Singleton getter for TradingCycleEventLog."""
    global _default_event_log
    if _default_event_log is None:
        _default_event_log = TradingCycleEventLog()
    return _default_event_log
