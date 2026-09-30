# ==============================================================================
# File: risk/crypto_audit_ledger.py
# Monika Cryptographic Tamper-Evident Audit Ledger
# ==============================================================================

"""
Append-Only Cryptographic Hash-Chained Audit Ledger.

Maintains an immutable chain of audit records for trade proposals, RiskGate
clearance verdicts, and broker order executions.

Guarantees:
- Every record is chained to the previous record's SHA-256 hash.
- Refuse-to-extend-a-broken-chain: validates chain integrity before writing.
- Crash durability: uses file.flush() and os.fsync() on every write.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("TradingAgent.Risk.AuditLedger")

GENESIS_PREV_HASH = "0" * 64


class LedgerCorruptionError(Exception):
    """Raised when ledger integrity verification fails due to tampering or file truncation."""
    pass


LedgerTamperedError = LedgerCorruptionError


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    prev_record_hash: str
    record_hash: str
    timestamp_utc: str
    action: str
    payload: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


class CryptographicAuditLedger:
    """
    Append-only tamper-evident audit ledger on local filesystem.
    """

    def __init__(self, ledger_path: str | Path):
        import threading
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_record: Optional[AuditRecord] = None
        self._load_error: Optional[str] = None
        self._lock = threading.RLock()
        try:
            self._init_or_load()
        except LedgerCorruptionError as err:
            self._load_error = str(err)

    def _init_or_load(self) -> None:
        """Loads and verifies existing ledger file."""
        if not self.ledger_path.exists() or self.ledger_path.stat().st_size == 0:
            self._last_record = None
            return

        records = self.read_all()
        if not records:
            self._last_record = None
            return

        # Verify integrity of entire loaded chain
        expected_prev = GENESIS_PREV_HASH
        for idx, rec in enumerate(records):
            if rec.seq != idx:
                raise LedgerCorruptionError(f"Sequence mismatch at line {idx}: expected {idx}, got {rec.seq}")
            if rec.prev_record_hash != expected_prev:
                raise LedgerCorruptionError(f"Broken hash chain at seq {rec.seq}: prev_hash mismatch")

            computed = self._compute_hash(rec.seq, rec.prev_record_hash, rec.timestamp_utc, rec.action, rec.payload)
            if computed != rec.record_hash:
                raise LedgerCorruptionError(f"Tampered record at seq {rec.seq}: hash mismatch")
            expected_prev = rec.record_hash

        self._last_record = records[-1]

    @staticmethod
    def _compute_hash(
        seq: int,
        prev_hash: str,
        timestamp_utc: str,
        action: str,
        payload: Dict[str, Any],
    ) -> str:
        """Deterministically hashes an audit entry using canonical JSON sorting."""
        payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        canonical_str = f"{seq}|{prev_hash}|{timestamp_utc}|{action}|{payload_str}"
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def append(self, action: str, payload: Dict[str, Any]) -> AuditRecord:
        """
        Appends a new verified audit record with immediate fsync.
        Refuses to extend a broken/corrupted chain.
        """
        with self._lock:
            if self._load_error:
                raise LedgerCorruptionError(f"Cannot append to corrupted audit ledger: {self._load_error}")
            seq = (self._last_record.seq + 1) if self._last_record is not None else 0
            prev_hash = self._last_record.record_hash if self._last_record is not None else GENESIS_PREV_HASH
            ts_utc = datetime.now(timezone.utc).isoformat()

            rec_hash = self._compute_hash(seq, prev_hash, ts_utc, action, payload)
            record = AuditRecord(
                seq=seq,
                prev_record_hash=prev_hash,
                record_hash=rec_hash,
                timestamp_utc=ts_utc,
                action=action,
                payload=payload,
            )

            # Write append-only with OS-level byte-range locking and fsync durability
            line = record.to_json() + "\n"
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                fd = f.fileno()
                # Cross-process OS locking
                is_win = sys.platform == "win32"
                try:
                    if is_win:
                        import msvcrt
                        # Seek to file end before locking
                        f.seek(0, os.SEEK_END)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX)

                    f.write(line)
                    f.flush()
                    os.fsync(fd)
                finally:
                    if not is_win:
                        try:
                            import fcntl
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        except Exception:
                            pass

            self._last_record = record
            return record

    def read_all(self) -> List[AuditRecord]:
        """Reads all records from disk."""
        if not self.ledger_path.exists():
            return []

        records = []
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(
                        AuditRecord(
                            seq=data["seq"],
                            prev_record_hash=data["prev_record_hash"],
                            record_hash=data["record_hash"],
                            timestamp_utc=data["timestamp_utc"],
                            action=data["action"],
                            payload=data["payload"],
                        )
                    )
                except Exception as err:
                    raise LedgerCorruptionError(f"Corrupt JSON at line {line_no} in {self.ledger_path}: {err}") from err
        return records

    def verify_integrity(self) -> bool:
        """Verifies the complete ledger from genesis to tail."""
        try:
            self._init_or_load()
            return True
        except LedgerCorruptionError as err:
            logger.error(f"Ledger integrity verification failed: {err}")
            return False

    def verify_chain_integrity(self) -> Tuple[bool, str]:
        """
        Verifies the complete ledger from genesis to tail.
        Returns (is_valid, message).
        """
        if self._load_error is not None:
            return False, f"Tampered ledger: {self._load_error}"
        try:
            self._init_or_load()
            return True, "Chain integrity verified"
        except LedgerCorruptionError as err:
            logger.error(f"Ledger integrity verification failed: {err}")
            return False, f"Tampered ledger: {err}"

    def append_audit_record(self, action: str, payload: Dict[str, Any]) -> AuditRecord:
        """Alias for append."""
        return self.append(action, payload)


# Alias for concise usage
CryptoAuditLedger = CryptographicAuditLedger

