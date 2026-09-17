from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_374fa7(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_374fa7"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_period: int = int(self.settings.get("base_period", 20))
        self.min_period: int = int(self.settings.get("min_period", 10))
        self.max_period: int = int(self.settings.get("max_period", 45))
        self.vol_ma_period: int = int(self.settings.get("vol_ma_period", 20))
        self.vol_threshold: float = float(self.settings.get("vol_threshold", 1.25))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.candle_limit: int = int(self.settings.get("candle_limit", 120))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
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

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit
            )

            if not candles or len(candles) < max(self.max_period, self.vol_ma_period, self.atr_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for dynamic Donchian calculation.",
                    tags=["insufficient_data"]
                )

            records = []
            for c in candles:
                c_open = float(c.open if hasattr(c, 'open') else c['open'])
                c_high = float(c.high if hasattr(c, 'high') else c['high'])
                c_low = float(c.low if hasattr(c, 'low') else c['low'])
                c_close = float(c.close if hasattr(c, 'close') else c['close'])
                c_vol = float(c.volume if hasattr(c, 'volume') else c.get('volume', 1.0))
                records.append({
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close,
                    "volume": max(c_vol, 1e-6)
                })

            df = pd.DataFrame(records)

            # Calculate True Range and ATR
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean().bfill().ffill()

            # Volatility Adaptive Period Factor
            atr_ma = atr.rolling(window=self.vol_ma_period, min_periods=1).mean().bfill().ffill()
            volatility_ratio = (atr / (atr_ma + 1e-9)).clip(lower=0.5, upper=2.5)

            # In high volatility, shorten lookback to react faster to breakouts; in low volatility, lengthen it
            dynamic_lookbacks = (self.base_period / volatility_ratio).round().clip(
                lower=self.min_period,
                upper=self.max_period
            ).ffill().fillna(self.base_period).astype(int)

            current_idx = len(df) - 1
            current_lookback = int(dynamic_lookbacks.iloc[current_idx])

            # Dynamic Donchian Channels computed up to prior candle to prevent lookahead bias
            shifted_high = df["high"].shift(1)
            shifted_low = df["low"].shift(1)
            
            upper_channel = shifted_high.rolling(window=current_lookback, min_periods=1).max()
            lower_channel = shifted_low.rolling(window=current_lookback, min_periods=1).min()
            channel_mid = (upper_channel + lower_channel) / 2.0

            # Volume Expansion Filter
            vol_ma = df["volume"].rolling(window=self.vol_ma_period, min_periods=1).mean().bfill().ffill()
            relative_volume = df["volume"] / (vol_ma + 1e-9)

            curr_close = df["close"].iloc[current_idx]
            curr_upper = upper_channel.iloc[current_idx]
            curr_lower = lower_channel.iloc[current_idx]
            curr_mid = channel_mid.iloc[current_idx]
            curr_rvol = relative_volume.iloc[current_idx]
            curr_atr = atr.iloc[current_idx]
            curr_vol_ratio = volatility_ratio.iloc[current_idx]

            # Signal Evaluation
            bullish_expansion = (curr_close > curr_upper) and (curr_rvol >= self.vol_threshold)
            bearish_expansion = (curr_close < curr_lower) and (curr_rvol >= self.vol_threshold)

            if bullish_expansion:
                breakout_strength = (curr_close - curr_upper) / (curr_atr + 1e-9)
                confidence = float(np.clip(0.60 + (curr_rvol / 5.0) * 0.20 + min(breakout_strength, 1.0) * 0.15, 0.55, 0.95))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=(
                        f"Bullish Donchian expansion on XTIUSD. Price ({curr_close:.2f}) broke above "
                        f"{current_lookback}-bar dynamic upper band ({curr_upper:.2f}) with relative volume {curr_rvol:.2f}x "
                        f"and ATR expansion ratio {curr_vol_ratio:.2f}."
                    ),
                    tags=["volume_expansion", "donchian_breakout", "bullish_momentum"]
                )

            elif bearish_expansion:
                breakout_strength = (curr_lower - curr_close) / (curr_atr + 1e-9)
                confidence = float(np.clip(0.60 + (curr_rvol / 5.0) * 0.20 + min(breakout_strength, 1.0) * 0.15, 0.55, 0.95))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=(
                        f"Bearish Donchian expansion on XTIUSD. Price ({curr_close:.2f}) broke below "
                        f"{current_lookback}-bar dynamic lower band ({curr_lower:.2f}) with relative volume {curr_rvol:.2f}x "
                        f"and ATR expansion ratio {curr_vol_ratio:.2f}."
                    ),
                    tags=["volume_expansion", "donchian_breakout", "bearish_momentum"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=(
                    f"No breakout detected. Close ({curr_close:.2f}) within dynamic bounds "
                    f"[{curr_lower:.2f}, {curr_upper:.2f}], RVOL: {curr_rvol:.2f}x."
                ),
                tags=["consolidation", "no_signal"]
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error"]
            )