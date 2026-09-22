"""
File: analysis/memory/playbook_lifecycle.py
Autonomous lifecycle management for trading playbooks.
Controls transitions (Candidate -> Active -> Stale -> Archived),
rolling performance tracking, and automated rollback/demotion on degradation.
"""

import os
import json
import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from analysis.memory.playbook_ledger import PlaybookLedger

logger = logging.getLogger("TradingAgent.Memory.PlaybookLifecycle")


class PlaybookStatus(str, Enum):
    CANDIDATE = "candidate"  # Newly generated, undergoing validation
    ACTIVE = "active"        # Proven and approved for production execution
    STALE = "stale"          # Inactive or showing degrading performance
    ARCHIVED = "archived"    # Deprecated or rolled back


@dataclass
class TradeRecord:
    timestamp: str
    won: bool
    pnl: float
    r_multiple: float


@dataclass
class PlaybookMetadata:
    name: str
    status: PlaybookStatus = PlaybookStatus.CANDIDATE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trades: List[Dict[str, Any]] = field(default_factory=list)
    consecutive_losses: int = 0
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    current_win_rate: float = 0.0
    current_avg_rr: float = 0.0


class PlaybookLifecycleManager:
    """
    Manages the lifecycle, performance gating, and auto-rollback of trading playbooks.
    """

    CONSECUTIVE_LOSS_LIMIT = 3
    PROMOTION_MIN_TRADES = 5
    PROMOTION_MIN_WIN_RATE = 0.55
    PROMOTION_MIN_AVG_RR = 1.5
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
                status = PlaybookStatus(data.get("status", PlaybookStatus.CANDIDATE.value))
                loaded[name] = PlaybookMetadata(
                    name=name,
                    status=status,
                    created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
                    trades=data.get("trades", []),
                    consecutive_losses=data.get("consecutive_losses", 0),
                    total_trades=data.get("total_trades", 0),
                    win_count=data.get("win_count", 0),
                    loss_count=data.get("loss_count", 0),
                    current_win_rate=data.get("current_win_rate", 0.0),
                    current_avg_rr=data.get("current_avg_rr", 0.0)
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
                raw[name] = d
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
        except Exception as e:
            logger.error(f"[PlaybookLifecycle] Failed to save state: {e}")

    def register_playbook(self, name: str, status: PlaybookStatus = PlaybookStatus.CANDIDATE) -> PlaybookMetadata:
        """Register a new playbook in the lifecycle system."""
        if name not in self._state:
            now_iso = datetime.now(timezone.utc).isoformat()
            self._state[name] = PlaybookMetadata(
                name=name,
                status=status,
                created_at=now_iso,
                updated_at=now_iso
            )
            self._save_state()
            logger.info(f"[PlaybookLifecycle] Registered '{name}' as {status.value}")
        return self._state[name]

    def get_status(self, name: str) -> Optional[PlaybookStatus]:
        """Get the current lifecycle status of a playbook."""
        meta = self._state.get(name)
        return meta.status if meta else None

    def list_all_playbooks(self) -> Dict[str, PlaybookMetadata]:
        """List all tracked playbooks and their metadata."""
        return dict(self._state)

    def record_trade_outcome(
        self,
        name: str,
        won: bool,
        pnl: float,
        r_multiple: float,
        auto_rollback_on_streak: bool = True
    ) -> Dict[str, Any]:
        """
        Record a trade execution outcome for a playbook and update its lifecycle.
        Triggers auto-rollback or demotion if consecutive losses reach the threshold.
        """
        meta = self._state.get(name)
        if not meta:
            meta = self.register_playbook(name)

        now_iso = datetime.now(timezone.utc).isoformat()
        trade = {
            "timestamp": now_iso,
            "won": won,
            "pnl": pnl,
            "r_multiple": r_multiple
        }
        meta.trades.append(trade)
        # Keep last 50 trades for rolling stats
        if len(meta.trades) > 50:
            meta.trades = meta.trades[-50:]

        meta.total_trades += 1
        meta.updated_at = now_iso

        if won:
            meta.win_count += 1
            meta.consecutive_losses = 0
        else:
            meta.loss_count += 1
            meta.consecutive_losses += 1

        # Calculate metrics over recorded window
        wins = sum(1 for t in meta.trades if t["won"])
        meta.current_win_rate = wins / len(meta.trades) if meta.trades else 0.0
        total_rr = sum(t["r_multiple"] for t in meta.trades)
        meta.current_avg_rr = total_rr / len(meta.trades) if meta.trades else 0.0

        # Safety Guard: Consecutive Loss Demotion & Rollback
        rolled_back = False
        if meta.consecutive_losses >= self.CONSECUTIVE_LOSS_LIMIT:
            logger.warning(
                f"[PlaybookLifecycle] '{name}' triggered {meta.consecutive_losses} consecutive losses! "
                f"Demoting to STALE and evaluating rollback."
            )
            meta.status = PlaybookStatus.STALE
            if auto_rollback_on_streak and self.ledger:
                rolled_back = self.ledger.rollback(
                    playbook_name=name
                )
                if rolled_back:
                    logger.info(f"[PlaybookLifecycle] Successfully auto-rolled back '{name}' via PlaybookLedger.")
                    meta.consecutive_losses = 0

        # Lifecycle Promotion Check
        if meta.status == PlaybookStatus.CANDIDATE:
            if (len(meta.trades) >= self.PROMOTION_MIN_TRADES and
                meta.current_win_rate >= self.PROMOTION_MIN_WIN_RATE and
                meta.current_avg_rr >= self.PROMOTION_MIN_AVG_RR):
                meta.status = PlaybookStatus.ACTIVE
                logger.info(
                    f"[PlaybookLifecycle] '{name}' PROMOTED to ACTIVE! "
                    f"(WinRate: {meta.current_win_rate:.1%}, Avg R:R: {meta.current_avg_rr:.2f})"
                )

        self._save_state()
        return {
            "status": meta.status.value,
            "consecutive_losses": meta.consecutive_losses,
            "win_rate": meta.current_win_rate,
            "avg_rr": meta.current_avg_rr,
            "rolled_back": rolled_back
        }

    def evaluate_staleness(self) -> List[str]:
        """Check for inactive playbooks and transition them to STALE if older than threshold."""
        stale_playbooks = []
        now = datetime.now(timezone.utc)
        for name, meta in self._state.items():
            if meta.status == PlaybookStatus.ACTIVE:
                try:
                    updated = datetime.fromisoformat(meta.updated_at)
                    if (now - updated).days > self.STALE_DAYS_THRESHOLD:
                        meta.status = PlaybookStatus.STALE
                        stale_playbooks.append(name)
                        logger.info(f"[PlaybookLifecycle] Playbook '{name}' marked STALE due to inactivity.")
                except Exception:
                    continue
        if stale_playbooks:
            self._save_state()
        return stale_playbooks
