from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_880297(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_880297"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.rvol_threshold: float = float(self.settings.get("rvol_threshold", 1.25))
        self.expansion_threshold: float = float(self.settings.get("expansion_threshold", 1.15))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=100
            )

            if not candles or len(candles) < max(self.donchian_period, self.volume_ma_period, self.atr_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for dynamic Donchian calculation.",
                    tags=["insufficient_data"]
                )

            # Build sanitized DataFrame
            records = []
            for c in candles:
                c_open = getattr(c, 'open', None) if hasattr(c, 'open') else c.get('open')
                c_high = getattr(c, 'high', None) if hasattr(c, 'high') else c.get('high')
                c_low = getattr(c, 'low', None) if hasattr(c, 'low') else c.get('low')
                c_close = getattr(c, 'close', None) if hasattr(c, 'close') else c.get('close')
                c_vol = getattr(c, 'volume', None) if hasattr(c, 'volume') else c.get('volume', 1.0)
                records.append({
                    'open': float(c_open),
                    'high': float(c_high),
                    'low': float(c_low),
                    'close': float(c_close),
                    'volume': max(float(c_vol), 1.0)
                })

            df = pd.DataFrame(records)
            df = df.ffill().bfill().fillna(0.0)

            # 1. Average True Range (ATR)
            high_low = df['high'] - df['low']
            high_close_prev = (df['high'] - df['close'].shift(1)).abs()
            low_close_prev = (df['low'] - df['close'].shift(1)).abs()
            true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
            atr = true_range.rolling(window=self.atr_period, min_periods=1).mean()

            # 2. Rolling Relative Volume (RVOL)
            vol_ma = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean().replace(0.0, 1.0)
            rvol = df['volume'] / vol_ma

            # 3. Dynamic Donchian Bands
            upper_donchian = df['high'].shift(1).rolling(window=self.donchian_period, min_periods=1).max()
            lower_donchian = df['low'].shift(1).rolling(window=self.donchian_period, min_periods=1).min()
            mid_donchian = (upper_donchian + lower_donchian) / 2.0
            
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
