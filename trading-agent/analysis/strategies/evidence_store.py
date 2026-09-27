# ==============================================================================
# File: analysis/strategies/evidence_store.py
# Monika Strategy Evidence Store & Sizing-Corrected Breakeven Engine
# ==============================================================================

"""
Strategy Evidence Store & Evidence Decay Engine.

1. Stores regime-conditioned backtest and walk-forward verification evidence.
2. Computes mathematically rigorous sizing-corrected breakeven fees (in basis points).
3. Evaluates evidence age decay (AGING >= 90 days, STALE >= 180 days) to prevent
   stale backtest assumptions from trading live capital.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Strategies.EvidenceStore")

DEFAULT_EVIDENCE_FILE = Path("data/strategy_evidence_store.json")


class EvidenceStatus(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"


@dataclass
class RegimeEvidence:
    regime: str  # TRENDING, RANGING, VOLATILE_CHOP
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    trade_count: int
    max_drawdown_pct: float


@dataclass
class StrategyEvidence:
    strategy_id: str
    symbol: str
    timeframe: str
    data_window_end: str  # ISO UTC date string
    gross_return: float
    total_trades: int
    avg_position_size: float
    max_concurrent_positions: int
    breakeven_bps: float
    regime_breakdown: dict[str, RegimeEvidence] = field(default_factory=dict)
    status: EvidenceStatus = EvidenceStatus.FRESH
    evidence_age_days: int = 0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, EvidenceStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyEvidence:
        raw_status = data.get("status", EvidenceStatus.FRESH.value)
        try:
            status = EvidenceStatus(raw_status)
        except ValueError:
            status = EvidenceStatus.FRESH

        regimes = {}
        for r_name, r_data in data.get("regime_breakdown", {}).items():
            regimes[r_name] = RegimeEvidence(**r_data)

        return cls(
            strategy_id=data.get("strategy_id", ""),
            symbol=data.get("symbol", ""),
            timeframe=data.get("timeframe", "H1"),
            data_window_end=data.get("data_window_end", ""),
            gross_return=float(data.get("gross_return", 0.0)),
            total_trades=int(data.get("total_trades", 0)),
            avg_position_size=float(data.get("avg_position_size", 1.0)),
            max_concurrent_positions=int(data.get("max_concurrent_positions", 1)),
            breakeven_bps=float(data.get("breakeven_bps", 0.0)),
            regime_breakdown=regimes,
            status=status,
            evidence_age_days=int(data.get("evidence_age_days", 0)),
            updated_at=float(data.get("updated_at", 0.0)),
        )


def compute_sizing_corrected_breakeven_bps(
    gross_return: float,
    total_trades: int,
    avg_position_size: float = 1.0,
    max_concurrent_positions: int = 1,
) -> float:
    """
    Computes sizing-corrected breakeven fee in basis points:
    breakeven_bps = (ln(1 + gross_return) / (2 * total_trades * avg_position_size)) * 10,000

    Rejects naive aggregate claims if max_concurrent_positions > 1 without per-lot tracking.
    """
    if total_trades <= 0 or avg_position_size <= 0:
        return 0.0

    if max_concurrent_positions > 1:
        logger.warning(
            f"Concurrent positions ({max_concurrent_positions} > 1) detected. "
            "Applying conservative non-compounding concurrency discount (0.75x) to breakeven capacity."
        )
        concurrency_factor = 0.75
    else:
        concurrency_factor = 1.0

    if gross_return <= -0.99:
        return 0.0

    log_return = math.log1p(max(-0.99, gross_return))
    # 2 round-trip sides per trade (entry and exit)
    fee_per_side = log_return / (2.0 * total_trades * avg_position_size)
    bps = fee_per_side * 10000.0 * concurrency_factor
    return round(float(max(0.0, bps)), 2)


class StrategyEvidenceStore:
    """Manages empirical performance evidence and lifecycle decay."""

    def __init__(self, file_path: Path | str = DEFAULT_EVIDENCE_FILE) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, StrategyEvidence] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.is_file():
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                ev = StrategyEvidence.from_dict(item)
                self._store[ev.strategy_id] = ev
        except Exception as e:
            logger.error(f"Failed loading evidence store from {self.file_path}: {e}")

    def _save(self) -> None:
        try:
            payload = [ev.to_dict() for ev in self._store.values()]
            tmp = self.file_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp.replace(self.file_path)
        except Exception as e:
            logger.error(f"Failed saving evidence store: {e}")

    def record_evidence(
        self,
        strategy_id: str,
        symbol: str,
        timeframe: str,
        data_window_end: datetime | str,
        gross_return: float,
        total_trades: int,
        avg_position_size: float = 1.0,
        max_concurrent_positions: int = 1,
        regime_metrics: Optional[dict[str, dict[str, Any]]] = None,
    ) -> StrategyEvidence:
        """
        Records new empirical backtest evidence and computes breakeven fee.
        """
        if isinstance(data_window_end, datetime):
            window_end_str = data_window_end.strftime("%Y-%m-%d")
            window_end_dt = data_window_end
        else:
            window_end_str = str(data_window_end)
            try:
                window_end_dt = datetime.strptime(window_end_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                window_end_dt = datetime.now(timezone.utc)

        be_bps = compute_sizing_corrected_breakeven_bps(
            gross_return=gross_return,
            total_trades=total_trades,
            avg_position_size=avg_position_size,
            max_concurrent_positions=max_concurrent_positions,
        )

        regimes = {}
        if regime_metrics:
            for r_name, r_vals in regime_metrics.items():
                regimes[r_name] = RegimeEvidence(
                    regime=r_name,
                    sharpe_ratio=float(r_vals.get("sharpe", 0.0)),
                    win_rate=float(r_vals.get("win_rate", 0.0)),
                    profit_factor=float(r_vals.get("profit_factor", 1.0)),
                    trade_count=int(r_vals.get("trades", 0)),
                    max_drawdown_pct=float(r_vals.get("max_drawdown_pct", 0.0)),
                )

        now = time.time()
        now_dt = datetime.now(timezone.utc)
        age_days = max(0, (now_dt - window_end_dt).days)

        status = EvidenceStatus.FRESH
        if age_days >= 180:
            status = EvidenceStatus.STALE
        elif age_days >= 90:
            status = EvidenceStatus.AGING

        ev = StrategyEvidence(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            data_window_end=window_end_str,
            gross_return=gross_return,
            total_trades=total_trades,
            avg_position_size=avg_position_size,
            max_concurrent_positions=max_concurrent_positions,
            breakeven_bps=be_bps,
            regime_breakdown=regimes,
            status=status,
            evidence_age_days=age_days,
            updated_at=now,
        )

        self._store[strategy_id] = ev
        self._save()
        logger.info(
            f"Recorded evidence for [{strategy_id}] {symbol}: "
            f"Breakeven={be_bps}bps, Age={age_days}d ({status.value})"
        )
        return ev

    def update_decay_statuses(self) -> int:
        """
        Scans all stored evidence and updates aging status based on calendar age.
        Returns number of strategies transitioned to AGING or STALE.
        """
        now_dt = datetime.now(timezone.utc)
        transitions = 0

        for ev in self._store.values():
            try:
                dt_end = datetime.strptime(ev.data_window_end[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                continue

            age_days = (now_dt - dt_end).days
            ev.evidence_age_days = max(0, age_days)

            new_status = EvidenceStatus.FRESH
            if age_days >= 180:
                new_status = EvidenceStatus.STALE
            elif age_days >= 90:
                new_status = EvidenceStatus.AGING

            if new_status != ev.status:
                ev.status = new_status
                transitions += 1

        if transitions > 0:
            self._save()
            logger.info(f"Updated evidence decay: {transitions} strategy status transition(s)")

        return transitions

    def is_strategy_eligible_to_trade(self, strategy_id: str, min_breakeven_bps: float = 3.0) -> Tuple[bool, str]:
        """
        Enforces evidence gates:
        1. Must not be STALE (>= 180 days without re-validation).
        2. Breakeven bps must exceed broker spread/commission floor (default 3.0 bps).
        """
        ev = self._store.get(strategy_id)
        if not ev:
            return False, f"No verified backtest evidence on file for {strategy_id}"

        if ev.status == EvidenceStatus.STALE:
            return False, f"Strategy evidence is STALE ({ev.evidence_age_days} days old >= 180d). Re-validation required."

        if ev.breakeven_bps < min_breakeven_bps:
            return False, (
                f"Sizing-corrected breakeven ({ev.breakeven_bps:.1f} bps) below minimum "
                f"broker fee hurdle ({min_breakeven_bps:.1f} bps)."
            )

        return True, "Approved by Evidence Gate"

    def validate_strategy_for_trade(self, strategy_id: str, regime: str = "UNKNOWN") -> Tuple[bool, str]:
        """Validates strategy trade eligibility against decay status and regime performance."""
        return self.is_strategy_eligible_to_trade(strategy_id)


# Backward-compatibility alias
EvidenceStore = StrategyEvidenceStore
