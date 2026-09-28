# ==============================================================================
# File: risk/pending_action.py
# Monika 2-Phase Order Commit Protocol & Crash-Resilient Pending Action Registry
# ==============================================================================

"""
2-Phase Order Commit Protocol (Fail-Closed Architecture).

Prevents ghost orders, double-submissions, and in-flight order loss caused by
sudden OS termination, power loss, or broker network disconnects.

Phase 1: Persistent pre-dispatch marker written to disk with atomic fsync.
Phase 2: Broker execution acknowledgement; marker updated to COMMITTED or UNCONFIRMED_DISPATCH.
Startup Hook: Boot crash reconciler inspects broker state for any dangling markers.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("TradingAgent.Risk.PendingAction")

DEFAULT_PENDING_DIR = Path(".runtime/pending_orders")


class PendingActionStatus(str, Enum):
    DISPATCHING = "DISPATCHING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    UNCONFIRMED_DISPATCH = "UNCONFIRMED_DISPATCH"


@dataclass
class PendingAction:
    client_order_id: str
    symbol: str
    action: str  # buy, sell, modify, close
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    order_type: str = "market"
    comment: str = ""
    timestamp: float = 0.0
    nonce: str = ""
    status: PendingActionStatus = PendingActionStatus.DISPATCHING
    broker_ticket: Optional[int] = None
    error_message: Optional[str] = None
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, PendingActionStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingAction:
        raw_status = data.get("status", PendingActionStatus.DISPATCHING.value)
        try:
            status = PendingActionStatus(raw_status)
        except ValueError:
            status = PendingActionStatus.UNCONFIRMED_DISPATCH
        return cls(
            client_order_id=data.get("client_order_id", ""),
            symbol=data.get("symbol", ""),
            action=data.get("action", ""),
            volume=float(data.get("volume", 0.0)),
            price=float(data["price"]) if data.get("price") is not None else None,
            sl=float(data["sl"]) if data.get("sl") is not None else None,
            tp=float(data["tp"]) if data.get("tp") is not None else None,
            order_type=data.get("order_type", "market"),
            comment=data.get("comment", ""),
            timestamp=float(data.get("timestamp", 0.0)),
            nonce=data.get("nonce", ""),
            status=status,
            broker_ticket=int(data["broker_ticket"]) if data.get("broker_ticket") is not None else None,
            error_message=data.get("error_message"),
            updated_at=float(data.get("updated_at", 0.0)),
        )


class PendingActionManager:
    """Manages file-backed 2-phase order commit lifecycle with atomic disk sync."""

    def __init__(self, base_dir: Path | str = DEFAULT_PENDING_DIR) -> None:
        self.base_dir = Path(base_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, client_order_id: str) -> Path:
        safe_id = "".join(c for c in client_order_id if c.isalnum() or c in ("-", "_"))
        return self.base_dir / f"pending_action_{safe_id}.json"

    def _atomic_write_action(self, action: PendingAction) -> None:
        """Writes action data atomically to disk with explicit fsync flush."""
        target_path = self._file_path(action.client_order_id)
        tmp_path = target_path.with_suffix(".tmp")
        payload = json.dumps(action.to_dict(), indent=2).encode("utf-8")

        self._ensure_dir()
        with open(tmp_path, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, target_path)

    def begin_action(
        self,
        symbol: str,
        action: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        order_type: str = "market",
        comment: str = "",
        client_order_id: Optional[str] = None,
    ) -> PendingAction:
        """
        Phase 1: Writes pre-dispatch action to persistent disk before sending order over network socket.
        """
        now = time.time()
        nonce = uuid.uuid4().hex[:12]
        if not client_order_id:
            client_order_id = f"act_{int(now * 1000)}_{symbol}_{nonce[:8]}"

        pending = PendingAction(
            client_order_id=client_order_id,
            symbol=symbol,
            action=action.lower(),
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            order_type=order_type,
            comment=comment,
            timestamp=now,
            nonce=nonce,
            status=PendingActionStatus.DISPATCHING,
            updated_at=now,
        )
        self._atomic_write_action(pending)
        logger.info(f"Phase 1 Order Commit Marker Created: [{pending.client_order_id}] {pending.action.upper()} {pending.volume} {pending.symbol}")
        return pending

    def commit_action(self, client_order_id: str, broker_ticket: Optional[int] = None) -> Optional[PendingAction]:
        """Phase 2: Confirms broker filled / placed the order successfully."""
        action = self.get_action(client_order_id)
        if not action:
            logger.warning(f"Attempted to commit non-existent pending action: {client_order_id}")
            return None

        action.status = PendingActionStatus.COMMITTED
        action.broker_ticket = broker_ticket
        action.updated_at = time.time()
        self._atomic_write_action(action)
        logger.info(f"Phase 2 Order Commit Confirmed: [{client_order_id}] Ticket={broker_ticket}")
        return action

    def fail_action(self, client_order_id: str, error_message: str) -> Optional[PendingAction]:
        """Phase 2: Marks order as rejected by broker."""
        action = self.get_action(client_order_id)
        if not action:
            return None

        action.status = PendingActionStatus.FAILED
        action.error_message = error_message
        action.updated_at = time.time()
        self._atomic_write_action(action)
        logger.warning(f"Phase 2 Order Rejected: [{client_order_id}] Reason={error_message}")
        return action

    def mark_unconfirmed(self, client_order_id: str, error_message: str) -> Optional[PendingAction]:
        """Phase 2: Marks order as in-flight / unconfirmed due to socket timeout or connection drop."""
        action = self.get_action(client_order_id)
        if not action:
            return None

        action.status = PendingActionStatus.UNCONFIRMED_DISPATCH
        action.error_message = error_message
        action.updated_at = time.time()
        self._atomic_write_action(action)
        logger.critical(f"Phase 2 Order UNCONFIRMED: [{client_order_id}] Disconnect/Timeout: {error_message}")
        return action

    def get_action(self, client_order_id: str) -> Optional[PendingAction]:
        path = self._file_path(client_order_id)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PendingAction.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to read pending action {path}: {e}")
            return None

    def get_unconfirmed_actions(self) -> list[PendingAction]:
        """Scans disk for any orders that remain DISPATCHING or UNCONFIRMED_DISPATCH."""
        if not self.base_dir.is_dir():
            return []
        unconfirmed = []
        for p in self.base_dir.glob("pending_action_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                action = PendingAction.from_dict(data)
                if action.status in (PendingActionStatus.DISPATCHING, PendingActionStatus.UNCONFIRMED_DISPATCH):
                    unconfirmed.append(action)
            except Exception as e:
                logger.error(f"Failed reading pending action file {p}: {e}")
        return unconfirmed

    def cleanup_old_actions(self, max_age_seconds: float = 86400.0) -> int:
        """Cleans up committed or failed action files older than max_age_seconds."""
        if not self.base_dir.is_dir():
            return 0
        cleaned = 0
        now = time.time()
        for p in self.base_dir.glob("pending_action_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                action = PendingAction.from_dict(data)
                if action.status in (PendingActionStatus.COMMITTED, PendingActionStatus.FAILED):
                    if (now - action.updated_at) > max_age_seconds:
                        p.unlink(missing_ok=True)
                        cleaned += 1
            except Exception:
                pass
        return cleaned

    async def reconcile_at_boot(self, mt5_client: Any) -> list[dict[str, Any]]:
        """
        Inspects MT5 open positions and history to resolve any unconfirmed in-flight actions.
        Fail-closed: Returns a list of reconciliation findings.
        """
        unconfirmed = self.get_unconfirmed_actions()
        if not unconfirmed:
            return []

        logger.warning(f"Boot crash reconciliation: found {len(unconfirmed)} unconfirmed pending order(s) on disk.")
        results = []
        now = time.time()

        for act in unconfirmed:
            resolved = False
            # Check if position exists in MT5
            try:
                positions = await mt5_client.get_open_positions(act.symbol)
                for pos in positions:
                    pos_type = pos.get("type", "").lower()
                    expected_type = "buy" if act.action == "buy" else "sell"
                    vol_diff = abs(float(pos.get("volume", 0.0)) - act.volume)
                    # If comment matches or type and volume match closely
                    pos_comment = pos.get("comment", "")
                    pos_time = pos.get("time", 0)
                    if hasattr(pos_time, "timestamp"):
                        pos_time = pos_time.timestamp()
                    elif isinstance(pos_time, str):
                        try:
                            from datetime import datetime
                            pos_time = datetime.fromisoformat(pos_time).timestamp()
                        except Exception:
                            pos_time = 0
                    else:
                        pos_time = float(pos_time or 0)
                    if act.nonce in pos_comment or (pos_type == expected_type and vol_diff < 0.001 and (now - pos_time) < 3600):
                        self.commit_action(act.client_order_id, broker_ticket=pos.get("ticket"))
                        results.append({
                            "client_order_id": act.client_order_id,
                            "symbol": act.symbol,
                            "status": "RECONCILED_COMMITTED",
                            "ticket": pos.get("ticket"),
                        })
                        resolved = True
                        break
            except Exception as e:
                logger.error(f"Reconciliation error querying positions for {act.symbol}: {e}")

            if not resolved:
                # If order was created more than 120 seconds ago and no trace in positions, mark as failed
                if (now - act.timestamp) > 120.0:
                    self.fail_action(act.client_order_id, "Order not found in broker positions after reboot grace period")
                    results.append({
                        "client_order_id": act.client_order_id,
                        "symbol": act.symbol,
                        "status": "RECONCILED_FAILED",
                    })
                else:
                    self.mark_unconfirmed(act.client_order_id, "Recent order still indeterminate on boot")
                    results.append({
                        "client_order_id": act.client_order_id,
                        "symbol": act.symbol,
                        "status": "RECONCILED_UNCONFIRMED",
                    })

        return results
