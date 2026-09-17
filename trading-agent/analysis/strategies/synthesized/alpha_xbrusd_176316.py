from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_176316(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_176316"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.vol_expansion_threshold: float = float(self.settings.get("vol_expansion_threshold", 1.25))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.atr_ma_period: int = int(self.settings.get("atr_ma_period", 20))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by this strategy.",
                tags=["unsupported_symbol"]
            )

        lookback_limit = max(self.donchian_period, self.volume_ma_period, self.atr_ma_period + self.atr_period) + 15
        candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=lookback_limit)

        if not candles or len(candles) < lookback_limit - 5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for volume-weighted dynamic Donchian evaluation.",
                tags=["insufficient_data"]
            )

        highs = np.array([c.high if hasattr(c, 'high') else c['high'] for c in candles], dtype=float)
        lows = np.array([c.low if hasattr(c, 'low') else c['low'] for c in candles], dtype=float)
        closes = np.array([c.close if hasattr(c, 'close') else c['close'] for c in candles], dtype=float)
        volumes = np.array([c.volume if hasattr(c, 'volume') else c['volume'] for c in candles], dtype=float)

        # Calculate True Range & ATR
        tr_list = [highs[0] - lows[0]]
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_list.append(tr)
        tr_series = pd.Series(tr_list)
        atr_series = tr_series.rolling(window=self.atr_period).mean()
        atr_ma_series = atr_series.rolling(window=self.atr_ma_period).mean()

        # Volume Expansion Analysis
        vol_series = pd.Series(volumes)
        vol_ma = vol_series.rolling(window=self.volume_ma_period).mean()

        # Dynamic Donchian Channels (Prior N bars excluding current forming/trigger candle)
        high_series = pd.Series(highs)
        low_series = pd.Series(lows)
        
        # Donchian Upper & Lower based on shifted window to avoid lookahead bias
        donchian_upper = high_series.shift(1).rolling(window=self.donchian_period).max()
        donchian_lower = low_series.shift(1).rolling(window=self.donchian_period).min()
        donchian_mid = (donchian_upper + donchian_lower) / 2.0

        curr_close = closes[-1]
        curr_vol = volumes[-1]
        curr_atr = atr_series.iloc[-1]
        curr_atr_ma = atr_ma_series.iloc[-1]
        curr_vol_ma = vol_ma.iloc[-1]
        curr_upper = donchian_upper.iloc[-1]
        curr_lower = donchian_lower.iloc[-1]
        curr_mid = donchian_mid.iloc[-1]

        if math.isnan(curr_upper) or math.isnan(curr_lower) or math.isnan(curr_vol_ma) or curr_vol_ma <= 0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="NaN values detected in dynamic channel indicators.",
                tags=["calculation_error"]
            )

        vol_ratio = curr_vol / curr_vol_ma
        atr_expansion = (curr_atr / curr_atr_ma) if (curr_atr_ma and not math.isnan(curr_atr_ma) and curr_atr_ma > 0) else 1.0

        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["xbrusd", "donchian_expansion", "volume_weighted"]

        # Signal Conditions: Breakout + Volume Surge + Volatility Expansion
        is_volume_confirmed = vol_ratio >= self.vol_expansion_threshold
        is_volatility_confirmed = atr_expansion >= 1.05

        if curr_close > curr_upper and is_volume_confirmed and is_volatility_confirmed:
            direction = 'buy'
            breakout_depth = (curr_close - curr_upper) / (curr_atr if curr_atr > 0 else 1.0)
            base_conf = 0.65 + min(0.20, (vol_ratio - self.vol_expansion_threshold) * 0.1) + min(0.10, breakout_depth * 0.05)
            confidence = min(0.95, max(0.50, float(base_conf)))
            rationale = (f"XBRUSD dynamic bullish Donchian expansion detected: Close ({curr_close:.2f}) broke Upper ({curr_upper:.2f}) "
                         f"with volume surge ({vol_ratio:.2f}x MA) and ATR expansion ({atr_expansion:.2f}x).")
            tags.extend(["bullish_breakout", "volume_surge"])

        elif curr_close < curr_lower and is_volume_confirmed and is_volatility_confirmed:
            direction = 'sell'
            breakout_depth = (curr_lower - curr_close) / (curr_atr if curr_atr > 0 else 1.0)
            base_conf = 0.65 + min(0.20, (vol_ratio - self.vol_expansion_threshold) * 0.1) + min(0.10, breakout_depth * 0.05)
            confidence = min(0.95, max(0.50, float(base_conf)))
            rationale = (f"XBRUSD dynamic bearish Donchian expansion detected: Close ({curr_close:.2f}) broke Lower ({curr_lower:.2f}) "
                         f"with volume surge ({vol_ratio:.2f}x MA) and ATR expansion ({atr_expansion:.2f}x).")
            tags.extend(["bearish_breakout", "volume_surge"])
        else:
            rationale = (f"Consolidation / No expansion breakout. Close={curr_close:.2f}, Range=[{curr_lower:.2f}, {curr_upper:.2f}], "
                         f"VolRatio={vol_ratio:.2f}, ATRExpansion={atr_expansion:.2f}.")
            tags.append("consolidation")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=(direction is not None),
            confidence=confidence,
            rationale=rationale,
            tags=tags
        )