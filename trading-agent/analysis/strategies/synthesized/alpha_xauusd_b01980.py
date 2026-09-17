from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_b01980(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_b01980"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.trend_ema_period: int = int(self.settings.get("trend_ema_period", 50))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.volume_expansion_threshold: float = float(self.settings.get("volume_expansion_threshold", 1.25))
        self.bandwidth_expansion_threshold: float = float(self.settings.get("bandwidth_expansion_threshold", 1.10))
        self.lookback_limit: int = int(self.settings.get("lookback_limit", 120))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not supported by {self.strategy_id}.",
                    tags=["unsupported_symbol"]
                )

            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.lookback_limit
            )

            min_required = max(self.donchian_period, self.trend_ema_period, self.volume_ma_period) + 10
            if not candles or len(candles) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candles fetched ({len(candles) if candles else 0}/{min_required}).",
                    tags=["insufficient_data"]
                )

            records: List[Dict[str, float]] = []
            for c in candles:
                if isinstance(c, dict):
                    records.append({
                        "open": float(c.get("open", 0.0)),
                        "high": float(c.get("high", 0.0)),
                        "low": float(c.get("low", 0.0)),
                        "close": float(c.get("close", 0.0)),
                        "volume": float(c.get("volume", 0.0))
                    })
                else:
                    records.append({
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume)
                    })

            df = pd.DataFrame(records).replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

            # Indicator Calculations
            df["donchian_high"] = df["high"].rolling(window=self.donchian_period, min_periods=1).max().shift(1)
            df["donchian_low"] = df["low"].rolling(window=self.donchian_period, min_periods=1).min().shift(1)
            df["donchian_mid"] = (df["donchian_high"] + df["donchian_low"]) / 2.0

            # Dynamic Bandwidth
            mid_safe = df["donchian_mid"].replace(0.0, np.nan)
            df["bandwidth"] = ((df["donchian_high"] - df["donchian_low"]) / mid_safe).fillna(0.0)
            df["bandwidth_ma"] = df["bandwidth"].rolling(window=10, min_periods=1).mean()

            # Volume & Trend Filters
            df["volume_ma"] = df["volume"].rolling(window=self.volume_ma_period, min_periods=1).mean()
            vol_ma_safe = df["volume_ma"].replace(0.0, np.nan)
            df["volume_ratio"] = (df["volume"] / vol_ma_safe).fillna(1.0)
            df["trend_ema"] = df["close"].ewm(span=self.trend_ema_period, adjust=False).mean()

            # Latest metrics
            last_row = df.iloc[-1]
            close_price = float(last_row["close"])
            donchian_high = float(last_row["donchian_high"])
            donchian_low = float(last_row["donchian_low"])
            trend_ema = float(last_row["trend_ema"])
            volume_ratio = float(last_row["volume_ratio"])
            bandwidth = float(last_row["bandwidth"])
            bandwidth_ma = float(last_row["bandwidth_ma"])

            bandwidth_expansion = (bandwidth > (bandwidth_ma * self.bandwidth_expansion_threshold)) if bandwidth_ma > 0 else False
            volume_expansion = volume_ratio >= self.volume_expansion_threshold

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["xauusd", "donchian_expansion"]

            # Bullish Breakout Evaluation
            if close_price > donchian_high and close_price > trend_ema:
                if volume_expansion and bandwidth_expansion:
                    direction = "buy"
                    vol_boost = min(0.20, (volume_ratio - self.volume_expansion_threshold) * 0.15)
                    bw_boost = min(0.15, (bandwidth / (bandwidth_ma if bandwidth_ma > 0 else 1.0) - 1.0) * 0.2)
                    confidence = float(np.clip(0.65 + vol_boost + bw_boost, 0.50, 0.95))
                    rationale_parts.append(
                        f"Bullish Donchian expansion: Close ({close_price:.2f}) broke above {self.donchian_period}-period High ({donchian_high:.2f}) "
                        f"with Volume Ratio {volume_ratio:.2f}x and expanding channel bandwidth ({bandwidth:.4f} > {bandwidth_ma:.4f})."
                    )
                    tags.extend(["bullish_breakout", "volume_surge"])

            # Bearish Breakdown Evaluation
            elif close_price < donchian_low and close_price < trend_ema:
                if volume_expansion and bandwidth_expansion:
                    direction = "sell"
                    vol_boost = min(0.20, (volume_ratio - self.volume_expansion_threshold) * 0.15)
                    bw_boost = min(0.15, (bandwidth / (bandwidth_ma if bandwidth_ma > 0 else 1.0) - 1.0) * 0.2)
                    confidence = float(np.clip(0.65 + vol_boost + bw_boost, 0.50, 0.95))
                    rationale_parts.append(
                        f"Bearish Donchian expansion: Close ({close_price:.2f}) broke below {self.donchian_period}-period Low ({donchian_low:.2f}) "
                        f"with Volume Ratio {volume_ratio:.2f}x and expanding channel bandwidth ({bandwidth:.4f} > {bandwidth_ma:.4f})."
                    )
                    tags.extend(["bearish_breakdown", "volume_surge"])

            if direction is None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=True,
                    confidence=0.0,
                    rationale=f"No dynamic Donchian expansion detected on {symbol}. VolRatio={volume_ratio:.2f}, Bandwidth={bandwidth:.4f}.",
                    tags=["neutral", "consolidation"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=" | ".join(rationale_parts),
                tags=tags
            )

        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error", "exception"]
            )