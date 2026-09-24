"""
Strategy Decay Monitor: Automated strategy degradation detection & state machine.
Prevents compounding drawdowns from decaying quantitative alphas.

State transitions:
ACTIVE -> (3 warnings) -> MONITORING -> (2 warnings) -> DECAYED -> (3 warnings) -> DISABLED

Source: Vibe-Trading src/strategy_store/decay.py
"""
import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.StrategyDecayMonitor")


class DecayState(str, Enum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    DECAYED = "decayed"
    DISABLED = "disabled"


_TRANSITIONS = {
    DecayState.ACTIVE: (3, DecayState.MONITORING),
    DecayState.MONITORING: (2, DecayState.DECAYED),
    DecayState.DECAYED: (3, DecayState.DISABLED),
}


@dataclass
class StrategyHealth:
    strategy_id: str
    state: DecayState = DecayState.ACTIVE
    warning_count: int = 0
    consecutive_losses: int = 0
    rolling_win_rate: float = 0.55
    last_evaluated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "state": self.state.value if isinstance(self.state, DecayState) else str(self.state),
            "warning_count": self.warning_count,
            "consecutive_losses": self.consecutive_losses,
            "rolling_win_rate": self.rolling_win_rate,
            "last_evaluated": self.last_evaluated.isoformat() if self.last_evaluated else None,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyHealth":
        raw_state = data.get("state", "active")
        try:
            state = DecayState(raw_state)
        except Exception:
            state = DecayState.ACTIVE

        raw_dt = data.get("last_evaluated")
        if raw_dt:
            try:
                dt = datetime.fromisoformat(raw_dt)
            except Exception:
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        return cls(
            strategy_id=data.get("strategy_id", "unknown"),
            state=state,
            warning_count=int(data.get("warning_count", 0)),
            consecutive_losses=int(data.get("consecutive_losses", 0)),
            rolling_win_rate=float(data.get("rolling_win_rate", 0.55)),
            last_evaluated=dt,
            reason=str(data.get("reason", "")),
        )


class StrategyDecayMonitor:
    """
    In-memory and stateful monitor for tracking per-strategy degradation.
    Throttles or disables strategies showing statistical breakdown in live/paper trading.
    """

    def __init__(self):
        self._health_map: Dict[str, StrategyHealth] = {}

    def get_health(self, strategy_id: str) -> StrategyHealth:
        if strategy_id not in self._health_map:
            self._health_map[strategy_id] = StrategyHealth(strategy_id=strategy_id)
        return self._health_map[strategy_id]

    def is_tradeable(self, strategy_id: str) -> bool:
        """
        ACTIVE and MONITORING states are allowed to emit signals.
        DECAYED and DISABLED states are suppressed from execution.
        """
        health = self.get_health(strategy_id)
        return health.state in (DecayState.ACTIVE, DecayState.MONITORING)

    def record_trade_outcome(self, strategy_id: str, win: bool) -> StrategyHealth:
        """Update state upon individual trade completion."""
        health = self.get_health(strategy_id)
        if not win:
            health.consecutive_losses += 1
            if health.consecutive_losses >= 4:
                health.warning_count += 1
                health.reason = f"Consecutive losses reached {health.consecutive_losses}"
                self._check_transition(health)
        else:
            health.consecutive_losses = 0
            if health.warning_count > 0:
                health.warning_count = max(0, health.warning_count - 1)

        health.last_evaluated = datetime.now(timezone.utc)
        return health

    def evaluate(
        self,
        strategy_id: str,
        recent_trades: List[Any],
        baseline_win_rate: float = 0.55,
    ) -> StrategyHealth:
        """
        Evaluate strategy against a window of recent trades.
        Triggers warning if win rate drops >= 30% below baseline or below 35% absolute floor.
        """
        health = self.get_health(strategy_id)
        if not recent_trades or len(recent_trades) < 5:
            return health

        wins = 0
        for t in recent_trades:
            pnl = getattr(t, "pnl_pct", None)
            if pnl is None and hasattr(t, "pnl"):
                pnl = getattr(t, "pnl", None)
            if pnl is None and isinstance(t, dict):
                pnl = t.get("pnl_pct", t.get("pnl", 0.0))
            if float(pnl or 0.0) > 0.0:
                wins += 1

        win_rate = round(wins / len(recent_trades), 3)
        health.rolling_win_rate = win_rate

        is_warning = bool(win_rate < (baseline_win_rate * 0.70) or win_rate < 0.35)

        if is_warning:
            health.warning_count += 1
            health.reason = f"Rolling win rate {win_rate:.1%} fell below threshold ({baseline_win_rate:.1%})"
            self._check_transition(health)
        else:
            # Recovery
            health.warning_count = max(0, health.warning_count - 1)
            if health.state == DecayState.MONITORING and health.warning_count == 0:
                health.state = DecayState.ACTIVE
                health.reason = "Recovered to ACTIVE via healthy performance"

        health.last_evaluated = datetime.now(timezone.utc)
        return health

    def _check_transition(self, health: StrategyHealth) -> None:
        threshold, next_state = _TRANSITIONS.get(health.state, (999, health.state))
        if health.warning_count >= threshold:
            prev_state = health.state
            health.state = next_state
            health.warning_count = 0
            logger.warning(
                f"[StrategyDecay] Strategy {health.strategy_id} transitioned: "
                f"{prev_state.value} -> {next_state.value}. Reason: {health.reason}"
            )

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {k: v.to_dict() for k, v in self._health_map.items()}

    def from_dict(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            if isinstance(v, dict):
                self._health_map[k] = StrategyHealth.from_dict(v)

    async def save_to_db(self, session: Any) -> None:
        """Persist decay health state to PostgreSQL SystemConfig."""
        if not session:
            return
        try:
            from database.models import SystemConfig

            payload = json.dumps(self.to_dict())
            if hasattr(SystemConfig, "upsert"):
                res = SystemConfig.upsert(
                    session=session,
                    key="strategy_decay_health",
                    value=payload,
                    description="Strategy decay monitor persisted health state",
                )
                if inspect.isawaitable(res):
                    await res
            if hasattr(session, "commit"):
                c = session.commit()
                if inspect.isawaitable(c):
                    await c
        except Exception as e:
            logger.debug(f"[StrategyDecay] Failed to persist decay state to DB: {e}")

    async def load_from_db(self, session: Any) -> None:
        """Load decay health state from PostgreSQL SystemConfig."""
        if not session:
            return
        try:
            from database.models import SystemConfig
            from sqlalchemy import select

            stmt = select(SystemConfig).where(SystemConfig.key == "strategy_decay_health")
            res = session.execute(stmt)
            if inspect.isawaitable(res):
                res = await res
            row = res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None
            if inspect.isawaitable(row):
                row = await row
            if row and getattr(row, "value", None):
                data = json.loads(row.value)
                self.from_dict(data)
                logger.info(f"[StrategyDecay] Loaded decay state for {len(self._health_map)} strategies from DB.")
        except Exception as e:
            logger.debug(f"[StrategyDecay] Failed to load decay state from DB: {e}")


_GLOBAL_DECAY_MONITOR: Optional[StrategyDecayMonitor] = None


def get_strategy_decay_monitor() -> StrategyDecayMonitor:
    global _GLOBAL_DECAY_MONITOR
    if _GLOBAL_DECAY_MONITOR is None:
        _GLOBAL_DECAY_MONITOR = StrategyDecayMonitor()
    return _GLOBAL_DECAY_MONITOR
