"""
File: analysis/memory/playbook_lifecycle.py
Autonomous lifecycle management for trading playbooks.
Controls transitions (Candidate -> Active -> Stale -> Archived),
rolling performance tracking, 48-hour cooldowns, and automated rollback/demotion on degradation.
"""

import os
import json
import time
import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from analysis.memory.playbook_ledger import (
    PlaybookLedger,
    PlaybookState,
    PlaybookStatus,
    PlaybookMetadata,
)

logger = logging.getLogger("TradingAgent.Memory.PlaybookLifecycle")


@dataclass
class TradeRecord:
    timestamp: str
    won: bool
    pnl: float
    r_multiple: float


class PlaybookLifecycleFSM:
    """
    Finite State Machine managing the lifecycle, performance gating, and auto-rollback of trading playbooks.
    States: CANDIDATE -> ACTIVE -> STALE -> ARCHIVED
    - Promotion: CANDIDATE -> ACTIVE if trades >= 5, WR >= 55%, avg R:R >= 1.5
    - Demotion: ACTIVE -> STALE if consecutive losses >= 3 (48-hour cooldown + optional auto-rollback)
    - Archival: Any -> ARCHIVED if trades >= 20 and WR < 45%
    - Recovery: STALE -> CANDIDATE if 48h cooldown expired and revalidation passed
    """

    CONSECUTIVE_LOSS_LIMIT = 3
    PROMOTION_MIN_TRADES = 5
    PROMOTION_MIN_WIN_RATE = 0.55
    PROMOTION_MIN_AVG_RR = 1.5
    ARCHIVE_MIN_TRADES = 20
    ARCHIVE_MAX_WIN_RATE = 0.45
    STALE_COOLDOWN_HOURS = 48.0
    STALE_DAYS_THRESHOLD = 30

    def __init__(self, playbooks_dir: Optional[str] = None, ledger: Optional[PlaybookLedger] = None):
        if playbooks_dir:
            self.playbooks_dir = playbooks_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.playbooks_dir = os.path.join(base_dir, "skills", "trading", "playbooks")

        self.state_file = os.path.join(self.playbooks_dir, ".playbook_lifecycle.json")
        self.ledger = ledger or PlaybookLedger(self.playbooks_dir)
        self._state: Dict[str, PlaybookMetadata] = self._load_state()

    def _load_state(self) -> Dict[str, PlaybookMetadata]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            loaded = {}
            for name, data in raw.items():
                st_val = data.get("state") or data.get("status", PlaybookState.CANDIDATE.value)
                try:
                    state = PlaybookState(st_val)
                except ValueError:
                    state = PlaybookState.CANDIDATE

                loaded[name] = PlaybookMetadata(
                    name=name,
                    state=state,
                    created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    trades=data.get("trades", []),
                    consecutive_losses=data.get("consecutive_losses", 0),
                    trades_count=data.get("trades_count", data.get("total_trades", 0)),
                    wins=data.get("wins", data.get("win_count", 0)),
                    losses=data.get("losses", data.get("loss_count", 0)),
                    win_rate=data.get("win_rate", data.get("current_win_rate", 0.0)),
                    avg_rr=data.get("avg_rr", data.get("current_avg_rr", 0.0)),
                    stale_until_ts=data.get("stale_until_ts"),
                    version_hash=data.get("version_hash"),
                )
            return loaded
        except Exception as e:
            logger.error(f"[PlaybookLifecycle] Failed to load state: {e}")
            return {}

    def _save_state(self):
        try:
            raw = {}
            for name, meta in self._state.items():
                d = asdict(meta)
                d["status"] = meta.status.value
                d["state"] = meta.state.value
                d["total_trades"] = meta.trades_count
                d["win_count"] = meta.wins
                d["loss_count"] = meta.losses
                d["current_win_rate"] = meta.win_rate
                d["current_avg_rr"] = meta.avg_rr
                raw[name] = d
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            logger.error(f"[PlaybookLifecycle] Failed to save state: {e}")

    def register_playbook(
        self,
        name: str,
        state: Optional[PlaybookState] = None,
        status: Optional[PlaybookState] = None,
    ) -> PlaybookMetadata:
        """Register a new playbook in the lifecycle system."""
        chosen_state = state or status or PlaybookState.CANDIDATE
        if name not in self._state:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._state[name] = PlaybookMetadata(
                name=name,
                state=chosen_state,
                created_at=now_iso,
                updated_at=now_iso,
            )
            self._save_state()
            logger.info(f"[PlaybookLifecycle] Registered '{name}' as {chosen_state.value}")
        return self._state[name]

    def get_status(self, name: str) -> Optional[PlaybookState]:
        """Get current lifecycle status of a playbook."""
        meta = self._state.get(name)
        return meta.status if meta else None

    def get_state(self, name: str) -> Optional[PlaybookState]:
        """Get current lifecycle state of a playbook."""
        meta = self._state.get(name)
        return meta.state if meta else None

    def get_metadata(self, name: str) -> Optional[PlaybookMetadata]:
        """Retrieve full metadata record for a playbook."""
        return self._state.get(name)

    def list_all_playbooks(self) -> Dict[str, PlaybookMetadata]:
        """List all tracked playbooks and their metadata."""
        return dict(self._state)

    def get_active_playbooks(self) -> List[str]:
        """List all playbooks currently in ACTIVE status and eligible for execution."""
        active = []
        for name, meta in self._state.items():
            if meta.state == PlaybookState.ACTIVE:
                active.append(name)
        return active

    def is_active(self, name: str) -> bool:
        """Check if a specific playbook is in ACTIVE state."""
        meta = self._state.get(name)
        if not meta:
            return False
        return meta.state == PlaybookState.ACTIVE

    def revalidate(self, name: str, force: bool = False) -> bool:
        """
        Transition a STALE playbook back to CANDIDATE for re-evaluation.
        Requires 48-hour cooldown to have expired unless force=True.
        """
        meta = self._state.get(name)
        if not meta or meta.state != PlaybookState.STALE:
            return False

        now_ts = time.time()
        if not force and meta.stale_until_ts and now_ts < meta.stale_until_ts:
            remaining_hours = (meta.stale_until_ts - now_ts) / 3600.0
            logger.info(
                f"[PlaybookLifecycle] Cannot revalidate '{name}': still in cooldown for {remaining_hours:.1f}h"
            )
            return False

        meta.state = PlaybookState.CANDIDATE
        meta.stale_until_ts = None
        meta.consecutive_losses = 0
        meta.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_state()
        logger.info(f"[PlaybookLifecycle] '{name}' transitioned from STALE to CANDIDATE for revalidation.")
        return True

    def record_trade_outcome(
        self,
        name: str,
        won: Optional[bool] = None,
        pnl: float = 0.0,
        r_multiple: Optional[float] = None,
        auto_rollback_on_streak: bool = True,
        is_win: Optional[bool] = None,
        rr: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Record a trade execution outcome for a playbook and update its lifecycle.
        Supports both (won, r_multiple) and (is_win, rr).
        """
        meta = self._state.get(name)
        if not meta:
            meta = self.register_playbook(name)

        if is_win is not None:
            won = is_win
        elif won is None:
            won = True

        if rr is not None:
            r_multiple = rr
        elif r_multiple is None:
            r_multiple = 0.0

        now_iso = datetime.now(timezone.utc).isoformat()
        trade = {
            "timestamp": now_iso,
            "won": bool(won),
            "pnl": float(pnl),
            "r_multiple": float(r_multiple),
        }
        meta.trades.append(trade)
        # Keep last 50 trades for rolling stats
        if len(meta.trades) > 50:
            meta.trades = meta.trades[-50:]

        meta.trades_count += 1
        meta.updated_at = now_iso

        if won:
            meta.wins += 1
            meta.consecutive_losses = 0
        else:
            meta.losses += 1
            meta.consecutive_losses += 1

        # Calculate metrics over recorded window
        wins = sum(1 for t in meta.trades if t["won"])
        meta.win_rate = wins / len(meta.trades) if meta.trades else 0.0
        total_rr = sum(t.get("r_multiple", 0.0) for t in meta.trades)
        meta.avg_rr = total_rr / len(meta.trades) if meta.trades else 0.0

        rolled_back = False

        # Transition 1: Consecutive Loss Demotion to STALE + Cooldown (48h) + Rollback
        if meta.consecutive_losses >= self.CONSECUTIVE_LOSS_LIMIT:
            logger.warning(
                f"[PlaybookLifecycle] '{name}' triggered {meta.consecutive_losses} consecutive losses! "
                f"Demoting to STALE (48h cooldown) and evaluating rollback."
            )
            meta.state = PlaybookState.STALE
            meta.stale_until_ts = time.time() + (self.STALE_COOLDOWN_HOURS * 3600.0)
            if auto_rollback_on_streak and self.ledger:
                rolled_back = self.ledger.rollback(playbook_name=name)
                if rolled_back:
                    logger.info(f"[PlaybookLifecycle] Successfully auto-rolled back '{name}' via PlaybookLedger.")
                    meta.consecutive_losses = 0

        # Transition 2: Archival if long-term degradation (>= 20 trades and WR < 45%)
        elif meta.trades_count >= self.ARCHIVE_MIN_TRADES and meta.win_rate < self.ARCHIVE_MAX_WIN_RATE:
            logger.warning(
                f"[PlaybookLifecycle] '{name}' ARCHIVED due to persistent degradation: "
                f"{meta.trades_count} trades, {meta.win_rate:.1%} WR (< {self.ARCHIVE_MAX_WIN_RATE:.0%})."
            )
            meta.state = PlaybookState.ARCHIVED

        # Transition 3: Promotion from CANDIDATE to ACTIVE
        elif meta.state == PlaybookState.CANDIDATE:
            if (
                len(meta.trades) >= self.PROMOTION_MIN_TRADES
                and meta.win_rate >= self.PROMOTION_MIN_WIN_RATE
                and meta.avg_rr >= self.PROMOTION_MIN_AVG_RR
            ):
                meta.state = PlaybookState.ACTIVE
                logger.info(
                    f"[PlaybookLifecycle] '{name}' PROMOTED to ACTIVE! "
                    f"(WinRate: {meta.win_rate:.1%}, Avg R:R: {meta.avg_rr:.2f})"
                )

        self._save_state()
        return {
            "status": meta.status.value,
            "state": meta.state.value,
            "consecutive_losses": meta.consecutive_losses,
            "win_rate": meta.win_rate,
            "avg_rr": meta.avg_rr,
            "rolled_back": rolled_back,
            "stale_until_ts": meta.stale_until_ts,
        }

    def evaluate_staleness(self) -> List[str]:
        """Check for inactive playbooks and transition them to STALE if older than threshold."""
        changed = []
        now = datetime.now(timezone.utc)
        now_ts = time.time()
        for name, meta in self._state.items():
            if meta.state == PlaybookState.ACTIVE:
                try:
                    updated = datetime.fromisoformat(meta.updated_at)
                    if (now - updated).days > self.STALE_DAYS_THRESHOLD:
                        meta.state = PlaybookState.STALE
                        meta.stale_until_ts = now_ts + (self.STALE_COOLDOWN_HOURS * 3600.0)
                        changed.append(name)
                        logger.info(f"[PlaybookLifecycle] Playbook '{name}' marked STALE due to inactivity.")
                except Exception:
                    continue
            elif meta.state == PlaybookState.STALE:
                # If cooldown expired, can auto-transition back to CANDIDATE
                if meta.stale_until_ts and now_ts >= meta.stale_until_ts:
                    meta.state = PlaybookState.CANDIDATE
                    meta.stale_until_ts = None
                    meta.consecutive_losses = 0
                    changed.append(name)
                    logger.info(f"[PlaybookLifecycle] Playbook '{name}' cooldown expired; returned to CANDIDATE.")
        if changed:
            self._save_state()
        return changed


# Backward-compatible alias
PlaybookLifecycleManager = PlaybookLifecycleFSM

__all__ = [
    "PlaybookState",
    "PlaybookStatus",
    "TradeRecord",
    "PlaybookMetadata",
    "PlaybookLifecycleFSM",
    "PlaybookLifecycleManager",
]
