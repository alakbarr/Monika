from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_1230d3(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_1230d3"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.base_lookback: int = int(self.settings.get("base_lookback", 24))
        self.min_lookback: int = int(self.settings.get("min_lookback", 12))
        self.max_lookback: int = int(self.settings.get("max_lookback", 48))
        self.vol_ma_period: int = int(self.settings.get("vol_ma_period", 24))
        self.bandwidth_ma_period: int = int(self.settings.get("bandwidth_ma_period", 20))
        self.volume_z_threshold: float = float(self.settings.get("volume_z_threshold", 1.2))
        self.expansion_threshold: float = float(self.settings.get("expansion_threshold", 1.15))
        self.history_limit: int = int(self.settings.get("history_limit", 120))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.history_limit
            )

            if not candles or len(candles) < self.max_lookback + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history: {len(candles) if candles else 0} received.",
                    tags=["insufficient_data", "donchian_expansion"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Candidate decommissioned: truncated synthesis",
                tags=["decommissioned"]
            )
        except Exception as e:
            return EdgeSignal(strategy_id=getattr(self, 'strategy_id', 'unknown'), symbol=getattr(self, 'symbol', 'unknown'), direction=None, valid=False, confidence=0.0, rationale=f'Calculation error: {e}', tags=['error'])
