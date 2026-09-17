from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_6e46d9(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_6e46d9"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback = self.settings.get("htf_lookback", 48)
        self.ltf_sweep_lookback = self.settings.get("ltf_sweep_lookback", 6)
        self.displacement_multiplier = self.settings.get("displacement_multiplier", 1.2)
        self.atr_period = self.settings.get("atr_period", 14)
        self.logger = logging.getLogger(f"trading.strategy.{self.strategy_id}")

    def _to_df(self, candles) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        data = []
        for c in candles:
            try:
                o = c.open
                h = c.high
                l = c.low
                cls = c.close
                v = c.volume
                t = c.timestamp
            except (AttributeError, TypeError, KeyError):
                o = c.get('open')
                h = c.get('high')
                l = c.get('low')
                cls = c.get('close')
                v = c.get('volume', 0)
                t = c.get('timestamp')
            
            data.append({
                'open': float(o),
                'high': float(h),
                'low': float(l),
                'close': float(cls),
                'volume': float(v),
                'timestamp': t
            })
        return pd.DataFrame(data)

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        if len(df) < period + 1:
            return 0.0
        high = df['high']
        low = df['low']
        close = df['close']
        tr = np.maximum(
            high - low, 
            np.maximum(
                np.abs(high - close.shift(1)), 
                np.abs(low - close.shift(1))
            )
        )
        atr = tr.rolling(window=period).mean()
        return float(atr.iloc[-1])

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported.",
                tags=[]
            )

        try:
            # Fetch HTF (H1) and LTF (M15) candles
            candles_h1 = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=100
            )
            candles_m15 = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M15', limit=100
            )

            df_h1 = self._to_df(candles_h1)
            df_m15 = self._to_df(candles_m15)

            if len(df_h1) < 50 or len(df_m15) < 20:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for HTF/LTF analysis.",
                    tags=["insufficient_data"]
                )

            # 1. Identify HTF Key Liquidity Pools (Swing Highs / Lows)
            # Exclude the most recent 2 candles to avoid active repainting levels
            htf_high = float(df_h1['high'].iloc[-self.htf_lookback:-2].max())
            htf_low = float(df_h1['low'].iloc[-self.htf_lookback:-2].min())

            # 2. Calculate LTF ATR for displacement threshold
            atr_m15 = self._calc_atr(df_m15, self.atr_period)
            if atr_m15 <= 0:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Invalid ATR calculation.",
                    tags=["error_atr"]
                )

            # 3. Analyze LTF Sweep and Displacement
            recent_m15 = df_m15.iloc[-self.ltf_sweep_lookback:]
            current_m15 = df_m15.iloc[-1]
            prev_m15 = df_m15.iloc[-2]

            # Check for Bullish Sweep (Swept HTF Low, then reclaimed)
            swept_low = recent_m15['low'].min() < htf_low
            reclaimed_low = current_m15['close'] > htf_low

            # Check for Bearish Sweep (Swept HTF High, then reclaimed)
            swept_high = recent_m15['high'].max() > htf_high
            reclaimed_high = current_m15['close'] < htf_high

            # Displacement check (Strong momentum candle in opposite direction of sweep)
            bullish_displacement = (
                (current_m15['close'] - current_m15['open'] > self.displacement_multiplier * atr_m15) or
                (prev_m15['close'] - prev_m15['open'] > self.displacement_multiplier * atr_m15)
            ) and (current_m15['close'] > current_m15['open'])

            bearish_displacement = (
                (current_m15['open'] - current_m15['close'] > self.displacement_multiplier * atr_m15) or
                (prev_m15['open'] - prev_m15['close'] > self.displacement_multiplier * atr_m15)
            ) and (current_m15['close'] < current_m15['open'])

            direction = None
            confidence = 0.0
            rationale = "No liquidity sweep with displacement detected."
            tags = ["liquidity_sweep", "xauusd"]

            # Bullish Setup
            if swept_low and reclaimed_low and bullish_displacement:
                direction = "buy"
                # Calculate confidence based on displacement strength and sweep depth
                sweep_depth = htf_low - recent_m15['low'].min()
                depth_factor = min(sweep_depth / (atr_m15 + 1e-8), 2.0) / 2.0  # normalized up to 2 ATR
                disp_factor = min((current_m15['close'] - current_m15['open']) / (atr_m15 + 1e-8), 3.0) / 3.0
                
                confidence = 0.6 + (0.2 * depth_factor) + (0.15 * disp_factor)
                confidence = min(max(confidence, 0.5), 0.95)
                
                rationale = (
                    f"Bullish Liquidity Sweep: HTF Low ({htf_low:.2f}) swept by "
                    f"LTF Low ({recent_m15['low'].min():.2f}) and reclaimed with strong displacement."
                )
                tags.append("bullish_sweep")

            # Bearish Setup
            elif swept_high and reclaimed_high and bearish_displacement:
                direction = "sell"
                # Calculate confidence based on displacement strength and sweep depth
                sweep_depth = recent_m15['high'].max() - htf_high
                depth_factor = min(sweep_depth / (atr_m15 + 1e-8), 2.0) / 2.0
                disp_factor = min((current_m15['open'] - current_m15['close']) / (atr_m15 + 1e-8), 3.0) / 3.0
                
                confidence = 0.6 + (0.2 * depth_factor) + (0.15 * disp_factor)
                confidence = min(max(confidence, 0.5), 0.95)
                
                rationale = (
                    f"Bearish Liquidity Sweep: HTF High ({htf_high:.2f}) swept by "
                    f"LTF High ({recent_m15['high'].max():.2f}) and reclaimed with strong displacement."
                )
                tags.append("bearish_sweep")

            valid = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=round(confidence, 2),
                rationale=rationale,
                tags=tags
            )

        except Exception as e:
            self.logger.error(f"Error evaluating strategy {self.strategy_id}: {str(e)}", exc_info=True)
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Execution error: {str(e)}",
                tags=["error"]
            )