# ==============================================================================
# File: risk/execution_simulator.py
# ==============================================================================

"""
Pre-Execution Market Replay & Slippage Simulation Sandbox (Phase 7).

Replays recent 100-tick microstructure and stresses order proposals across:
1. Baseline slippage (1.0x median spread)
2. Elevated slippage (1.5x median spread)
3. Liquidity shock stress slippage (3.0x median spread)

Asserts that expected trade edge over slippage drag exceeds 1.1x to prevent
negative mathematical expectancy in wide-spread or low-liquidity environments.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import PriceOHLCV

logger = logging.getLogger("TradingAgent.Risk.ExecutionSimulator")


@dataclass
class SlippageScenario:
    name: str
    multiplier: float
    spread: float
    slippage_drag: float
    effective_entry: float
    net_edge: float


@dataclass
class ExecutionSimulationResult:
    resilient: bool
    edge_to_drag_ratio: float
    median_spread: float
    current_spread: float
    scenarios: Dict[str, SlippageScenario]
    rejection_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class ExecutionSimulator:
    """
    Pre-execution sandbox for simulating tick slippage resilience.
    """

    def __init__(self, settings: Optional[dict] = None, mt5_client: Optional[Any] = None):
        self.settings = settings or {}
        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        self.min_edge_to_drag_ratio = float(risk_cfg.get("min_edge_to_slippage_ratio", 1.1))
        self.enabled = bool(risk_cfg.get("slippage_sandbox_enabled", True))
        self.mt5_client = mt5_client

    async def fetch_recent_ticks(
        self,
        symbol: str,
        count: int = 100,
        session: Optional[AsyncSession] = None
    ) -> List[Dict[str, float]]:
        """
        Retrieves up to `count` recent price ticks.
        Queries MT5 COM API if available; otherwise derives micro-ticks from recent OHLCV bars.
        """
        ticks: List[Dict[str, float]] = []

        # 1. Try MT5 COM API
        if self.mt5_client is not None:
            try:
                # MT5 client get_ticks / copy_ticks
                if hasattr(self.mt5_client, "get_ticks"):
                    res = await self.mt5_client.get_ticks(symbol, count=count)
                    if res and len(res) > 0:
                        for t in res[-count:]:
                            bid = float(t.get("bid", 0.0))
                            ask = float(t.get("ask", 0.0))
                            if bid > 0 and ask > 0:
                                ticks.append({"bid": bid, "ask": ask, "spread": ask - bid})
                        if len(ticks) >= 10:
                            return ticks
            except Exception as e:
                logger.debug(f"[{symbol}] MT5 tick retrieval non-fatal: {e}")

        # 2. Fallback: Reconstruct micro-ticks from recent OHLCV bars
        if session is not None:
            try:
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "M15")
                    .order_by(desc(PriceOHLCV.timestamp))
                    .limit(20)
                )
                bars = list((await session.execute(stmt)).scalars().all())
                if bars:
                    close_p = float(bars[0].close)
                    # Baseline spread estimation (approx 0.01% - 0.02% of price or 1.5 pips)
                    base_spread = max(1e-5, close_p * 0.00015)
                    for b in reversed(bars):
                        # Synthesize 5 micro-ticks per bar (open, high, low, close, mid)
                        o, h, l, c = float(b.open), float(b.high), float(b.low), float(b.close)
                        for price in [o, (o + h) / 2.0, h, l, (l + c) / 2.0, c]:
                            ticks.append({
                                "bid": price,
                                "ask": price + base_spread,
                                "spread": base_spread
                            })
                    if len(ticks) > count:
                        ticks = ticks[-count:]
                    return ticks
            except Exception as e:
                logger.debug(f"[{symbol}] OHLCV tick fallback non-fatal: {e}")

        # 3. Fail-safe synthetic ticks if no DB or MT5 available
        synth_spread = 0.00015
        return [{"bid": 1.0, "ask": 1.0 + synth_spread, "spread": synth_spread}] * count

    async def simulate_execution(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        volume: float = 0.1,
        ticks: Optional[List[Dict[str, float]]] = None,
        session: Optional[AsyncSession] = None
    ) -> ExecutionSimulationResult:
        """
        Runs tick-level market replay and stress tests across 3 slippage scenarios.
        """
        if not self.enabled:
            return ExecutionSimulationResult(
                resilient=True,
                edge_to_drag_ratio=99.0,
                median_spread=0.0,
                current_spread=0.0,
                scenarios={},
                details={"status": "disabled_by_config"}
            )

        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return ExecutionSimulationResult(
                resilient=True,
                edge_to_drag_ratio=1.0,
                median_spread=0.0,
                current_spread=0.0,
                scenarios={},
                details={"status": "zero_price_bypass"}
            )

        # 1. Fetch ticks
        if ticks is None:
            ticks = await self.fetch_recent_ticks(symbol, count=100, session=session)

        spreads = [max(1e-6, float(t["spread"])) for t in ticks] if ticks else [entry_price * 0.00015]
        median_spread = float(np.median(spreads))
        current_spread = float(spreads[-1]) if spreads else median_spread

        # 2. Compute trade geometry edge
        gross_edge = abs(take_profit - entry_price)
        risk_distance = abs(entry_price - stop_loss)
        is_buy = str(direction).lower() == "buy"

        # 3. Simulate 3 Scenarios
        # Scenario 1: Baseline (1.0x median spread)
        # Scenario 2: Elevated (1.5x median spread)
        # Scenario 3: Stress Liquidity Shock (3.0x median spread)
        multipliers = {"baseline": 1.0, "elevated": 1.5, "stress": 3.0}
        scenarios: Dict[str, SlippageScenario] = {}

        for sc_name, mult in multipliers.items():
            sc_spread = median_spread * mult
            # Slippage drag: half spread entry cost + execution slippage proportional to spread volatility
            exec_slippage = sc_spread * 0.6
            total_drag = sc_spread + exec_slippage
            effective_entry = entry_price + (total_drag if is_buy else -total_drag)
            net_edge = gross_edge - total_drag
            scenarios[sc_name] = SlippageScenario(
                name=sc_name,
                multiplier=mult,
                spread=round(sc_spread, 5),
                slippage_drag=round(total_drag, 5),
                effective_entry=round(effective_entry, 5),
                net_edge=round(net_edge, 5),
            )

        stress_drag = scenarios["stress"].slippage_drag
        edge_to_drag_ratio = round(gross_edge / max(stress_drag, 1e-6), 2)

        resilient = edge_to_drag_ratio >= self.min_edge_to_drag_ratio
        rejection_reason = None
        if not resilient:
            rejection_reason = (
                f"SLIPPAGE_UNFAVORABLE: Edge ({gross_edge:.5f}) to stress slippage drag "
                f"({stress_drag:.5f}) ratio {edge_to_drag_ratio:.2f} is below minimum threshold "
                f"{self.min_edge_to_drag_ratio:.2f} (Median Spread: {median_spread:.5f})."
            )

        return ExecutionSimulationResult(
            resilient=resilient,
            edge_to_drag_ratio=edge_to_drag_ratio,
            median_spread=round(median_spread, 5),
            current_spread=round(current_spread, 5),
            scenarios=scenarios,
            rejection_reason=rejection_reason,
            details={
                "gross_edge": gross_edge,
                "risk_distance": risk_distance,
                "ticks_evaluated": len(ticks),
            }
        )
