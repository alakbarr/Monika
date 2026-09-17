from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_a6d004(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_a6d004"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.ema_trend_period: int = int(self.settings.get("ema_trend_period", 50))
        self.min_rvol: float = float(self.settings.get("min_rvol", 1.25))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not applicable for this strategy.",
                    tags=["inapplicable_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe='H1',
                limit=100
            )

            if not candles or len(candles) < max(self.donchian_period, self.ema_trend_period) + 10:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data.",
                    tags=["insufficient_data"]
                )

            # Extract OHLCV arrays safely without getattr/eval
            closes = pd.Series([float(c.close if hasattr(c, 'close') else c['close']) for c in candles], dtype=float)
            highs = pd.Series([float(c.high if hasattr(c, 'high') else c['high']) for c in candles], dtype=float)
            lows = pd.Series([float(c.low if hasattr(c, 'low') else c['low']) for c in candles], dtype=float)
            volumes = pd.Series([float(c.volume if hasattr(c, 'volume') else c.get('volume', 1.0)) for c in candles], dtype=float)

            # Handle zero or flat volumes gracefully
            volumes = volumes.replace(0.0, 1.0).ffill().bfill()

            # 1. Standard ATR calculation for volatility baseline
            tr1 = highs - lows
            tr2 = (highs - closes.shift(1)).abs()
            tr3 = (lows - closes.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill()

            # 2. Dynamic Donchian Channels based on prior bars (excluding current candle to prevent lookahead)
            upper_donchian = highs.shift(1).rolling(window=self.donchian_period, min_periods=1).max().ffill().bfill()
            lower_donchian = lows.shift(1).rolling(window=self.donchian_period, min_periods=1).min().ffill().bfill()
            donchian_width = upper_donchian - lower_donchian
            donchian_width_ma = donchian_width.rolling(window=self.donchian_period, min_periods=1).mean().ffill().bfill()

            # 3. Relative Volume (RVOL) calculation
            volume_ma = volumes.rolling(window=self.volume_ma_period, min_periods=1).mean().ffill().bfill()
            rvol = (volumes / (volume_ma + 1e-9)).ffill().bfill()

            # 4. Trend Baseline Filter
            ema_trend = closes.ewm(span=self.ema_trend_period, adjust=False).mean().ffill().bfill()

            curr_close = float(closes.iloc[-1])
            curr_upper = float(upper_donchian.iloc[-1])
            curr_lower = float(lower_donchian.iloc[-1])
            curr_width = float(donchian_width.iloc[-1])
            curr_width_ma = float(donchian_width_ma.iloc[-1])
            curr_rvol = float(rvol.iloc[-1])
            curr_ema = float(ema_trend.iloc[-1])
            curr_atr = float(atr.iloc[-1])

            # Validation metrics
            is_expansion = curr_width >= curr_width_ma
            is_high_volume = curr_rvol >= self.min_rvol

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale: str = ""
            tags: List[str] = ["vw_donchian_expansion", "xauusd"]

            # Long breakout: close above upper Donchian, high RVOL, channel expanding, above EMA trend
            if curr_close > curr_upper and is_high_volume and is_expansion and curr_close > curr_ema:
                direction = "buy"
                vol_boost = min(0.20, (curr_rvol - 1.0) * 0.1)
                width_boost = min(0.15, max(0.0, (curr_width / (curr_width_ma + 1e-9) - 1.0) * 0.2))
                confidence = float(np.clip(0.60 + vol_boost + width_boost, 0.50, 0.92))
                rationale = (
                    f"Bullish Donchian expansion breakout on XAUUSD: Close ({curr_close:.2f}) > Upper ({curr_upper:.2f}), "
                    f"RVOL={curr_rvol:.2f}x, Donchian Width={curr_width:.2f} (MA={curr_width_ma:.2f}), ATR={curr_atr:.2f}."
                )
                tags.extend(["breakout_long", "high_rvol", "expansion"])

            # Short breakout: close below lower Donchian, high RVOL, channel expanding, below EMA trend
            elif curr_close < curr_lower and is_high_volume and is_expansion and curr_close < curr_ema:
                direction = "sell"
                vol_boost = min(0.20, (curr_rvol - 1.0) * 0.1)
                width_boost = min(0.15, max(0.0, (curr_width / (curr_width_ma + 1e-9) - 1.0) * 0.2))
                confidence = float(np.clip(0.60 + vol_boost + width_boost, 0.50, 0.92))
                rationale = (
                    f"Bearish Donchian expansion breakout on XAUUSD: Close ({curr_close:.2f}) < Lower ({curr_lower:.2f}), "
                    f"RVOL={curr_rvol:.2f}x, Donchian Width={curr_width:.2f} (MA={curr_width_ma:.2f}), ATR={curr_atr:.2f}."
                )
                tags.extend(["breakout_short", "high_rvol", "expansion"])
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=(
                        f"No breakout condition met. Close={curr_close:.2f}, Upper={curr_upper:.2f}, "
                        f"Lower={curr_lower:.2f}, RVOL={curr_rvol:.2f}, Width={curr_width:.2f}."
                    ),
                    tags=["no_signal", "ranging"]
                )

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
