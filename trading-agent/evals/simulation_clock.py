# ==============================================================================
# File: evals/simulation_clock.py
# Description: Deterministic Simulation Clock & Synchronous Market Step Simulator
# ==============================================================================

"""
Deterministic Virtual Market Clock & Step Simulator.
Allows offline zero-latency simulation of agent decision loops with frozen timestamps,
exact time increments, controlled slippage, and synthetic bar progression.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Union
import asyncio
import logging

logger = logging.getLogger("TradingAgent.SimulationClock")


class SimulationClock:
    """
    Virtual Market Clock supporting frozen time, deterministic time travel,
    and instantaneous asynchronous sleep without real wall-clock delay.
    """

    def __init__(self, start_time: Optional[Union[datetime, str, float]] = None):
        if start_time is None:
            self._current_time = datetime.now(timezone.utc)
        elif isinstance(start_time, (int, float)):
            self._current_time = datetime.fromtimestamp(start_time, tz=timezone.utc)
        elif isinstance(start_time, str):
            try:
                self._current_time = datetime.fromisoformat(start_time)
                if self._current_time.tzinfo is None:
                    self._current_time = self._current_time.replace(tzinfo=timezone.utc)
            except ValueError:
                self._current_time = datetime.now(timezone.utc)
        else:
            self._current_time = (
                start_time
                if start_time.tzinfo is not None
                else start_time.replace(tzinfo=timezone.utc)
            )

        self._frozen: bool = True
        self._step_history: List[datetime] = [self._current_time]

    def now(self) -> datetime:
        """Returns the current simulated time in UTC."""
        return self._current_time

    def timestamp(self) -> float:
        """Returns current simulated unix timestamp."""
        return self._current_time.timestamp()

    def advance(self, seconds: float = 1.0) -> datetime:
        """Advances virtual time forward by a given number of seconds."""
        if seconds < 0:
            raise ValueError("Cannot rewind simulation clock with advance().")
        self._current_time += timedelta(seconds=seconds)
        self._step_history.append(self._current_time)
        return self._current_time

    def advance_to(self, target_time: Union[datetime, str]) -> datetime:
        """Advances virtual time forward to a specific timestamp."""
        if isinstance(target_time, str):
            target_time = datetime.fromisoformat(target_time)
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)

        if target_time < self._current_time:
            raise ValueError("Target time is in the past relative to current simulation clock.")

        self._current_time = target_time
        self._step_history.append(self._current_time)
        return self._current_time

    async def sleep(self, seconds: float) -> None:
        """
        Instantaneous virtual sleep.
        Advances simulation clock without delaying the event loop.
        """
        self.advance(seconds)
        await asyncio.sleep(0)  # Yield control to event loop

    def is_frozen(self) -> bool:
        return self._frozen

    def reset(self, new_start_time: Optional[Union[datetime, str]] = None) -> None:
        """Resets the simulation clock."""
        if new_start_time is not None:
            self.__init__(new_start_time)
        elif self._step_history:
            self._current_time = self._step_history[0]
            self._step_history = [self._current_time]


@dataclass
class MarketStep:
    """A single discrete market tick or bar in the step simulator."""
    timestamp: datetime
    symbol: str
    bid: float
    ask: float
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    volume: float = 100.0
    spread_pips: float = field(init=False)

    def __post_init__(self):
        # Calculate spread in pips (Jpy: 0.01 pip, FX standard: 0.0001 pip)
        pip_unit = 0.01 if "JPY" in self.symbol.upper() else 0.0001
        self.spread_pips = round(abs(self.ask - self.bid) / pip_unit, 2)


class MarketStepSimulator:
    """
    Synchronous / Step-by-Step Market Environment Simulator.
    Feeds synthetic market steps sequentially to test agent evaluation loops.
    """

    def __init__(self, clock: Optional[SimulationClock] = None):
        self.clock = clock or SimulationClock()
        self._steps: List[MarketStep] = []
        self._current_step_index: int = -1
        self._executed_fills: List[Dict[str, Any]] = []

    def load_steps(self, steps: List[MarketStep]) -> None:
        """Load a sequence of chronological market steps."""
        self._steps = sorted(steps, key=lambda s: s.timestamp)
        self._current_step_index = -1

    def step(self) -> Optional[MarketStep]:
        """Advances to the next market step and syncs the simulation clock."""
        if self._current_step_index + 1 >= len(self._steps):
            return None

        self._current_step_index += 1
        current = self._steps[self._current_step_index]
        self.clock.advance_to(current.timestamp)
        return current

    @property
    def current_step(self) -> Optional[MarketStep]:
        if 0 <= self._current_step_index < len(self._steps):
            return self._steps[self._current_step_index]
        return None

    def simulate_order_fill(
        self,
        symbol: str,
        order_type: str,
        lots: float,
        slippage_pips: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calculates execution fill price based on current market step prices and slippage.
        """
        step = self.current_step
        if not step or step.symbol != symbol:
            raise RuntimeError(f"No active market step matching symbol '{symbol}' for order fill.")

        pip_unit = 0.01 if "JPY" in symbol.upper() else 0.0001
        order_type_clean = order_type.upper()

        if order_type_clean == "BUY":
            fill_price = step.ask + (slippage_pips * pip_unit)
        elif order_type_clean == "SELL":
            fill_price = step.bid - (slippage_pips * pip_unit)
        else:
            raise ValueError(f"Unknown order type: {order_type}")

        fill_record = {
            "symbol": symbol,
            "order_type": order_type_clean,
            "lots": float(lots),
            "fill_price": round(fill_price, 5),
            "timestamp": self.clock.now(),
            "spread_pips": step.spread_pips,
            "slippage_pips": slippage_pips,
        }
        self._executed_fills.append(fill_record)
        return fill_record

    def get_fill_history(self) -> List[Dict[str, Any]]:
        return list(self._executed_fills)
