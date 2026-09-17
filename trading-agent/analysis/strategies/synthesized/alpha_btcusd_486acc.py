from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_486acc(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_486acc"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        cfg = self.settings or {}
        self.timeframe: str = cfg.get("timeframe", "H1")
        self.candle_limit: int = int(cfg.get("candle_limit", 100))
        self.ema_period: int = int(cfg.get("ema_period", 20))
        self.atr_period: int = int(cfg.get("atr_period", 14))
        self.rsi_period: int = int(cfg.get("rsi_period", 14))
        self.exhaustion_mult: float = float(cfg.get("exhaustion_mult", 2.35))
        self.extreme_mult: float = float(cfg.get("extreme_mult", 3.5))
        self.rsi_oversold: float = float(cfg.get("rsi_oversold", 30.0))
        self.rsi_overbought: float = float(cfg.get("rsi_overbought", 70.0))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            timeframe = settings.get("timeframe", self.timeframe)
            limit = int(settings.get("candle_limit", self.candle_limit))
            
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=timeframe,
                limit=limit
            )

            if not candles or len(candles) < max(self.ema_period, self.atr_period, self.rsi_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for ATR exhaustion evaluation.",
                    tags=["insufficient_data"]
                )

            # Build sanitized DataFrame
            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                c_vol = float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0))
                records.append({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close, 'volume': c_vol})

            df = pd.DataFrame(records)
            df = df.ffill().bfill()

            # Technical Indicator Computation
            # 1. EMA
            df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

            # 2. ATR
            prev_close = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_close).abs()
            tr3 = (df['low'] - prev_close).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].ewm(alpha=1.0 / self.atr_period, adjust=False).mean()

            # 3. RSI
            delta = df['close'].diff()
            gain = delta.clip(lower=0.0)
            loss = (-delta).clip(lower=0.0)
            avg_gain = gain.ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / self.rsi_period, adjust=False).mean()
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
