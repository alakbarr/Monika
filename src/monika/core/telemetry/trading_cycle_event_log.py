"""
Monotonic Event-Sourced Trading Cycle Log and Decision Lineage Tracing (Phase 7.1 & 7.2).
Provides append-only, structurally-typed, contiguous-sequence event logging per trading cycle,
enabling exact cycle replay and recursive provenance tracing from orders to signals.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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


def compute_event_hash(
    prev_hash: str,
    seq: int,
    cycle_id: str,
    event_type: str,
    timestamp: str,
    payload: Dict[str, Any],
    source_event_seqs: List[int],
) -> str:
    """Computes deterministic SHA-256 hash chaining previous event with current event payload."""
    try:
        payload_str = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        payload_str = str(sorted(payload.items()))
    sources_str = ",".join(str(s) for s in sorted(source_event_seqs))
    raw = f"{prev_hash}:{seq}:{cycle_id}:{event_type}:{timestamp}:{payload_str}:{sources_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class CycleEvent:
    seq: int
    cycle_id: str
    event_type: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source_event_seqs: List[int] = field(default_factory=list)  # Lineage tracing pointers (Phase 7.2)
    prev_hash: Optional[str] = None
    chain_hash: Optional[str] = None

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
        source_seqs = list(source_event_seqs or [])

        # Determine previous event hash (genesis hash for seq 1, previous chain_hash thereafter)
        prev_hash = ""
        if self._cycle_stores[cid]:
            prev_hash = self._cycle_stores[cid][-1].chain_hash or ""
        if not prev_hash:
            prev_hash = hashlib.sha256(f"genesis:{cid}".encode("utf-8")).hexdigest()

        ts = datetime.now(timezone.utc).isoformat()
        chain_hash = compute_event_hash(
            prev_hash=prev_hash,
            seq=seq,
            cycle_id=cid,
            event_type=event_type,
            timestamp=ts,
            payload=payload,
            source_event_seqs=source_seqs,
        )

        event = CycleEvent(
            seq=seq,
            cycle_id=cid,
            event_type=event_type,
            timestamp=ts,
            payload=payload,
            source_event_seqs=source_seqs,
            prev_hash=prev_hash,
            chain_hash=chain_hash,
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

    def verify_cycle_integrity(self, cycle_id: str) -> Tuple[bool, Optional[str]]:
        """
        Verify cryptographic SHA-256 chain integrity for all events in a cycle.
        Returns (True, None) if unbroken and valid, or (False, error_reason).
        """
        events = self.get_events_for_cycle(cycle_id)
        return verify_chain_integrity(events)


def verify_chain_integrity(events: List[CycleEvent]) -> Tuple[bool, Optional[str]]:
    """
    Verifies that an event stream forms an unbroken, untampered SHA-256 cryptographic hash chain.
    Returns (True, None) if valid, or (False, reason) if tampered/corrupted.
    """
    if not events:
        return True, None

    for i, ev in enumerate(events):
        # 1. Monotonic sequence and parent hash check
        if i == 0:
            expected_genesis = hashlib.sha256(f"genesis:{ev.cycle_id}".encode("utf-8")).hexdigest()
            if ev.prev_hash and ev.prev_hash != expected_genesis:
                return False, f"Genesis hash mismatch at seq {ev.seq}: expected {expected_genesis}, got {ev.prev_hash}"
        else:
            prev_ev = events[i - 1]
            if ev.seq != prev_ev.seq + 1:
                return False, f"Sequence gap: seq {ev.seq} does not follow {prev_ev.seq}"
            if ev.prev_hash and prev_ev.chain_hash and ev.prev_hash != prev_ev.chain_hash:
                return False, f"Broken hash chain at seq {ev.seq}: prev_hash {ev.prev_hash} != {prev_ev.chain_hash}"

        # 2. Re-compute hash and verify payload integrity
        if ev.chain_hash:
            computed = compute_event_hash(
                prev_hash=ev.prev_hash or "",
                seq=ev.seq,
                cycle_id=ev.cycle_id,
                event_type=ev.event_type,
                timestamp=ev.timestamp,
                payload=ev.payload,
                source_event_seqs=ev.source_event_seqs,
            )
            if computed != ev.chain_hash:
                return False, f"Tampered event payload at seq {ev.seq}: computed {computed} != recorded {ev.chain_hash}"

    return True, None


# Global default instance
_default_event_log: Optional[TradingCycleEventLog] = None


def get_cycle_event_log() -> TradingCycleEventLog:
    """Singleton getter for TradingCycleEventLog."""
    global _default_event_log
    if _default_event_log is None:
        _default_event_log = TradingCycleEventLog()
    return _default_event_log

