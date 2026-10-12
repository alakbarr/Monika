import math
import numpy as np
import pandas as pd
import datetime
import logging
import decimal
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal


class SynthesizedStrategy_alpha_xbrusd_0d2342(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_0d2342"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Hyperparameters
        self.h1_lookback = 20
        self.m15_lookback = 5
        self.breakout_threshold = 0.001  # 0.1% beyond level
        self.confidence_factor = 0.8

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # --- Fetch H1 candles -------------------------------------------------
            h1_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=200
            )
            if not h1_candles or len(h1_candles) < self.h1_lookback + 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient H1 candles",
                    tags=["insufficient_data"]
                )

            h1_df = pd.DataFrame(h1_candles)
            # Use the last h1_lookback candles (excluding the most recent one)
            recent_high = h1_df['high'].iloc[-self.h1_lookback - 1:-1].max()
            recent_low = h1_df['low'].iloc[-self.h1_lookback - 1:-1].min()
            last_h1 = h1_df.iloc[-1]

            # Determine breakout direction
            direction = None
            breakout_level = None
            if last_h1['close'] > recent_high * (1 + self.breakout_threshold):
                direction = 'sell'   # breakout above → expect reversal down
                breakout_level = recent_high
            elif last_h1['close'] < recent_low * (1 - self.breakout_threshold):
                direction = 'buy'    # breakout below → expect reversal up
                breakout_level = recent_low
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No breakout detected",
                    tags=["no_breakout"]
                )

            # --- Fetch M15 candles for displacement confirmation -----------------
            m15_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M15', limit=50
            )
            if not m15_candles or len(m15_candles) < self.m15_lookback + 1:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient M15 candles",
                    tags=["insufficient_data"]
                )

            m15_df = pd.DataFrame(m15_candles)
            recent_m15 = m15_df.iloc[-self.m15_lookback:]

            # Compute displacement candles
            if direction == 'sell':
                # Look for bearish candles (close < open)
                disp_candles = recent_m15[recent_m15['close'] < recent_m15['open']]
                if disp_candles.empty:
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction=None,
                        valid=False,
                        confidence=0.0,
                        rationale="No bearish displacement on M15",
                        tags=["no_displacement"]
                    )
                displacement = (disp_candles['open'] - disp_candles['close']).mean()
                volatility = m15_df['high'].sub(m15_df['low']).mean()
                if volatility == 0:
                    confidence = 0.0
                else:
                    confidence = min(1.0, displacement / volatility)
                confidence *= self.confidence_factor
                rationale = f"H1 breakout above {breakout_level:.2f}, M15 bearish displacement detected"
                tags = ["multi_timeframe", "liquidity_sweep", "sell"]
            else:  # direction == 'buy'
                disp_candles = recent_m15[recent_m15['close'] > recent_m15['open']]
                if disp_candles.empty:
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction=None,
                        valid=False,
                        confidence=0.0,
                        rationale="No bullish displacement on M15",
                        tags=["no_displacement"]
                    )
                displacement = (disp_candles['close'] - disp_candles['open']).mean()
                volatility = m15_df['high'].sub(m15_df['low']).mean()
                if volatility == 0:
                    confidence = 0.0
                else:
                    confidence = min(1.0, displacement / volatility)
                confidence *= self.confidence_factor
                rationale = f"H1 breakout below {breakout_level:.2f}, M15 bullish displacement detected"
                tags = ["multi_timeframe", "liquidity_sweep", "buy"]

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
