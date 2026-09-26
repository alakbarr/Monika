# ==============================================================================
# File: gateway/delivery_ledger.py
# ==============================================================================

"""
Omnichannel Message Delivery Ledger & At-Least-Once Reliability Engine.
Guarantees idempotent outbound message dispatch across all platform adapters
(Telegram, Discord, Slack, Webhooks), prevents duplicate delivery, and
tracks retry attempts and dead-letter queues.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Gateway.DeliveryLedger")

DEFAULT_LEDGER_DB = "data/gateway_delivery_ledger.db"

_FLOOD_REGEX = re.compile(
    r"(?:retry in|retry after|flood wait:?|wait\s+|too many requests.*?wait\s*)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)



class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass
class DeliveryRecord:
    idempotency_key: str
    platform: str
    recipient_id: str
    payload_hash: str
    status: DeliveryStatus
    attempts: int
    max_attempts: int
    created_at: float
    updated_at: float
    delivered_at: Optional[float] = None
    error_message: Optional[str] = None
    payload_json: Optional[str] = None
    flood_not_before: float = 0.0


class DeliveryLedger:
    """
    Transactional SQLite WAL-backed ledger for idempotent omnichannel message delivery
    with precision 429 Flood Control and at-least-once reliability guarantees.
    """

    def __init__(self, db_path: str = DEFAULT_LEDGER_DB):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_records (
                    idempotency_key TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    delivered_at REAL,
                    error_message TEXT,
                    payload_json TEXT,
                    flood_not_before REAL DEFAULT 0.0
                )
                """
            )
            # Add column flood_not_before if existing table lacks it
            try:
                conn.execute("ALTER TABLE delivery_records ADD COLUMN flood_not_before REAL DEFAULT 0.0")
            except sqlite3.OperationalError:
                pass

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delivery_status ON delivery_records(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_delivery_flood ON delivery_records(flood_not_before)"
            )

    @staticmethod
    def extract_flood_wait(error_str: str, default: float = 30.0) -> Optional[float]:
        """Extracts seconds from 429 / flood control error messages."""
        if not error_str:
            return None
        m = _FLOOD_REGEX.search(error_str)
        if m:
            try:
                wait_sec = float(m.group(1))
                return min(max(wait_sec, 1.0), 600.0)
            except Exception:
                return default
        if "429" in error_str or "too many requests" in error_str.lower() or "flood" in error_str.lower():
            return default
        return None

    @staticmethod
    def generate_idempotency_key(platform: str, recipient_id: str, content: str) -> str:
        """Generates a deterministic SHA-256 idempotency key."""
        raw = f"{platform.lower()}:{recipient_id}:{content.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def register_intent(
        self,
        idempotency_key: str,
        platform: str,
        recipient_id: str,
        payload: Any,
        max_attempts: int = 3,
    ) -> Tuple[bool, Optional[DeliveryRecord]]:
        """
        Registers intent to deliver a message.
        Returns (is_new, record). If the message is already DELIVERED, returns (False, record).
        """
        payload_str = json.dumps(payload, sort_keys=True) if not isinstance(payload, str) else payload
        p_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        now = time.time()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT idempotency_key, platform, recipient_id, payload_hash, status, attempts, max_attempts, created_at, updated_at, delivered_at, error_message, payload_json FROM delivery_records WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if row:
                existing = DeliveryRecord(
                    idempotency_key=row[0],
                    platform=row[1],
                    recipient_id=row[2],
                    payload_hash=row[3],
                    status=DeliveryStatus(row[4]),
                    attempts=row[5],
                    max_attempts=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                    delivered_at=row[9],
                    error_message=row[10],
                    payload_json=row[11],
                )
                # If already delivered or pending, do not duplicate
                if existing.status == DeliveryStatus.DELIVERED:
                    return False, existing
                return True, existing

            conn.execute(
                """
                INSERT INTO delivery_records (
                    idempotency_key, platform, recipient_id, payload_hash, status,
                    attempts, max_attempts, created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    platform,
                    recipient_id,
                    p_hash,
                    DeliveryStatus.PENDING.value,
                    0,
                    max_attempts,
                    now,
                    now,
                    payload_str[:4000],
                ),
            )
            record = DeliveryRecord(
                idempotency_key=idempotency_key,
                platform=platform,
                recipient_id=recipient_id,
                payload_hash=p_hash,
                status=DeliveryStatus.PENDING,
                attempts=0,
                max_attempts=max_attempts,
                created_at=now,
                updated_at=now,
                payload_json=payload_str[:4000],
            )
            return True, record

    def mark_delivered(self, idempotency_key: str) -> None:
        """Marks message as successfully delivered."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE delivery_records
                SET status = ?, delivered_at = ?, updated_at = ?, attempts = attempts + 1
                WHERE idempotency_key = ?
                """,
                (DeliveryStatus.DELIVERED.value, now, now, idempotency_key),
            )
        logger.debug(f"[DeliveryLedger] Marked '{idempotency_key[:12]}' as DELIVERED.")

    def mark_flood_delayed(self, idempotency_key: str, wait_seconds: float) -> None:
        """Postpones delivery attempt due to 429 Flood Control without consuming attempt budget."""
        now = time.time()
        not_before = now + max(wait_seconds, 1.0) + 0.5
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE delivery_records
                SET flood_not_before = ?, updated_at = ?, error_message = ?
                WHERE idempotency_key = ?
                """,
                (not_before, now, f"Flood control wait: {wait_seconds:.1f}s", idempotency_key),
            )
        logger.info(
            f"[DeliveryLedger] '{idempotency_key[:12]}' postponed for {wait_seconds:.1f}s until {not_before:.1f} (429 Flood Control)."
        )

    def mark_failed(self, idempotency_key: str, error: str) -> DeliveryStatus:
        """
        Increments attempt counter and sets status to FAILED or DEAD_LETTER.
        If the error is recognized as a 429 flood control, automatically defers without consuming attempt quota.
        """
        now = time.time()
        flood_wait = self.extract_flood_wait(error)
        if flood_wait is not None:
            self.mark_flood_delayed(idempotency_key, flood_wait)
            return DeliveryStatus.FAILED

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT attempts, max_attempts FROM delivery_records WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return DeliveryStatus.FAILED

            attempts = row[0] + 1
            max_attempts = row[1]
            new_status = DeliveryStatus.DEAD_LETTER if attempts >= max_attempts else DeliveryStatus.FAILED

            conn.execute(
                """
                UPDATE delivery_records
                SET status = ?, attempts = ?, updated_at = ?, error_message = ?
                WHERE idempotency_key = ?
                """,
                (new_status.value, attempts, now, str(error)[:500], idempotency_key),
            )
            logger.warning(
                f"[DeliveryLedger] '{idempotency_key[:12]}' attempt {attempts}/{max_attempts} failed: {error}. New status: {new_status.value}"
            )
            return new_status

    def get_pending_deliveries(self, limit: int = 50) -> List[DeliveryRecord]:
        """Fetches pending or retryable failed deliveries whose flood delay has elapsed."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT idempotency_key, platform, recipient_id, payload_hash, status,
                       attempts, max_attempts, created_at, updated_at, delivered_at, error_message, payload_json, flood_not_before
                FROM delivery_records
                WHERE status IN (?, ?) AND attempts < max_attempts AND (flood_not_before IS NULL OR flood_not_before <= ?)
                ORDER BY created_at ASC LIMIT ?
                """,
                (DeliveryStatus.PENDING.value, DeliveryStatus.FAILED.value, now, limit),
            )
            records = []
            for r in cursor.fetchall():
                records.append(
                    DeliveryRecord(
                        idempotency_key=r[0],
                        platform=r[1],
                        recipient_id=r[2],
                        payload_hash=r[3],
                        status=DeliveryStatus(r[4]),
                        attempts=r[5],
                        max_attempts=r[6],
                        created_at=r[7],
                        updated_at=r[8],
                        delivered_at=r[9],
                        error_message=r[10],
                        payload_json=r[11],
                        flood_not_before=r[12] if len(r) > 12 and r[12] is not None else 0.0,
                    )
                )
            return records

    def get_record(self, idempotency_key: str) -> Optional[DeliveryRecord]:
        """Fetches a specific delivery record by its idempotency key."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT idempotency_key, platform, recipient_id, payload_hash, status,
                       attempts, max_attempts, created_at, updated_at, delivered_at, error_message, payload_json, flood_not_before
                FROM delivery_records
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            )
            r = cursor.fetchone()
            if not r:
                return None
            return DeliveryRecord(
                idempotency_key=r[0],
                platform=r[1],
                recipient_id=r[2],
                payload_hash=r[3],
                status=DeliveryStatus(r[4]),
                attempts=r[5],
                max_attempts=r[6],
                created_at=r[7],
                updated_at=r[8],
                delivered_at=r[9],
                error_message=r[10],
                payload_json=r[11],
                flood_not_before=r[12] if len(r) > 12 and r[12] is not None else 0.0,
            )

    def list_dead_letters(self, limit: int = 50) -> List[DeliveryRecord]:
        """Fetches records that have exceeded max_attempts and entered DEAD_LETTER state."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT idempotency_key, platform, recipient_id, payload_hash, status,
                       attempts, max_attempts, created_at, updated_at, delivered_at, error_message, payload_json, flood_not_before
                FROM delivery_records
                WHERE status = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (DeliveryStatus.DEAD_LETTER.value, limit),
            )
            records = []
            for r in cursor.fetchall():
                records.append(
                    DeliveryRecord(
                        idempotency_key=r[0],
                        platform=r[1],
                        recipient_id=r[2],
                        payload_hash=r[3],
                        status=DeliveryStatus(r[4]),
                        attempts=r[5],
                        max_attempts=r[6],
                        created_at=r[7],
                        updated_at=r[8],
                        delivered_at=r[9],
                        error_message=r[10],
                        payload_json=r[11],
                        flood_not_before=r[12] if len(r) > 12 and r[12] is not None else 0.0,
                    )
                )
            return records

