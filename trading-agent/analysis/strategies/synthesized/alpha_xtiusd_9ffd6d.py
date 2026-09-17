from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_9ffd6d(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_9ffd6d"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.vol_ma_period: int = int(self.settings.get("vol_ma_period", 20))
        self.trend_filter_period: int = int(self.settings.get("trend_filter_period", 50))
        self.vol_expansion_threshold: float = float(self.settings.get("vol_expansion_threshold", 1.25))
        self.bandwidth_expansion_mult: float = float(self.settings.get("bandwidth_expansion_mult", 1.10))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.candle_limit: int = int(self.settings.get("candle_limit", 100))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit
            )

            if not candles or len(candles) < max(self.trend_filter_period + 5, self.donchian_period + 5):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for volume-weighted dynamic Donchian evaluation",
                    tags=["insufficient_data", "xtiusd", "donchian"]
                )

            records = []
            for c in candles:
                try:
                    records.append({
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume)
                    })
                except AttributeError:
                    records.append({
                        "high": float(c["high"]),
                        "low": float(c["low"]),
                        "close": float(c["close"]),
                        "volume": float(c.get("volume", 1.0))
                    })

            df = pd.DataFrame(records)

            # Prevent zero or negative volume anomalies
            df["volume"] = df["volume"].replace(0.0, np.nan).fillna(1.0)

            # Standard and Volume-Adjusted Donchian Channels (shifted by 1 to prevent lookahead bias)
            df["donchian_high"] = df["high"].shift(1).rolling(self.donchian_period, min_periods=self.donchian_period).max()
            df["donchian_low"] = df["low"].shift(1).rolling(self.donchian_period, min_periods=self.donchian_period).min()
            df["donchian_mid"] = (df["donchian_high"] + df["donchian_low"]) / 2.0

            # Bandwidth expansion calculation
            safe_mid = df["donchian_mid"].replace(0.0, np.nan)
            df["bandwidth"] = (df["donchian_high"] - df["donchian_low"]) / safe_mid
            df["bandwidth"] = df["bandwidth"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            df["bandwidth_ma"] = df["bandwidth"].rolling(self.donchian_period, min_periods=1).mean()

            # Volume Moving Average & Volume Ratio
            df["vol_ma"] = df["volume"].rolling(self.vol_ma_period, min_periods=1).mean()
            safe_vol_ma = df["vol_ma"].replace(0.0, np.nan)
            df["vol_ratio"] = df["volume"] / safe_vol_ma
            df["vol_ratio"] = df["vol_ratio"].replace([np.inf, -np.inf], np.nan).fillna(1.0)

            # Trend Baseline Filter
            df["trend_baseline"] = df["close"].rolling(self.trend_filter_period, min_periods=1).mean()

            # Volatility (ATR 14) for breakout quality assessment
            prev_close = df["close"].shift(1)
            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - prev_close).abs()
            tr3 = (df["low"] - prev_close).abs()
            df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).fillna(0.0)
            df["atr"] = df["tr"].rolling(14, min_periods=1).mean()

            # Extract latest bar metrics
            curr_close = float(df["close"].iloc[-1])
            curr_high = float(df["high"].iloc[-1])
            curr_low = float(df["low"].iloc[-1])
            curr_vol_ratio = float(df["vol_ratio"].iloc[-1])
            curr_bandwidth = float(df["bandwidth"].iloc[-1])
            curr_bandwidth_ma = float(df["bandwidth_ma"].iloc[-1])
            donchian_h = float(df["donchian_high"].iloc[-1])
            donchian_l = float(df["donchian_low"].iloc[-1])
            trend_ma = float(df["trend_baseline"].iloc[-1])
            curr_atr = max(float(df["atr"].iloc[-1]), 0.01)

            if math.isnan(donchian_h) or math.isnan(donchian_l):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Donchian channel values not fully formed",
                    tags=["incomplete_channel", "xtiusd"]
                )

            # Expansion conditions
            is_bandwidth_expanding = curr_bandwidth >= (curr_bandwidth_ma * self.bandwidth_expansion_mult)
            is_volume_expanding = curr_vol_ratio >= self.vol_expansion_threshold

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale: str = "No expansion breakout detected"
            tags: List[str] = ["xtiusd", "donchian_expansion"]

            # Long Breakout Logic
            if curr_close > donchian_h and is_bandwidth_expanding and is_volume_expanding and curr_close > trend_ma:
                direction = "buy"
                breakout_distance = (curr_close - donchian_h) / curr_atr
                vol_boost = min(0.20, (curr_vol_ratio - 1.0) * 0.1)
                dist_boost = min(0.15, breakout_distance * 0.05)
                confidence = float(np.clip(0.65 + vol_boost + dist_boost, 0.50, 0.95))
                rationale = (
                    f"Long Dynamic Donchian Expansion: Close ({curr_close:.2f}) > Band High ({donchian_h:.2f}), "
                    f"Volume Ratio {curr_vol_ratio:.2f}x >= {self.vol_expansion_threshold}x, "
                    f"Bandwidth Expansion {curr_bandwidth:.4f} > MA {curr_bandwidth_ma:.4f}"
                )
                tags.extend(["bullish_breakout", "volume_expansion", "trend_aligned"])

            # Short Breakdown Logic
            elif curr_close < donchian_l and is_bandwidth_expanding and is_volume_expanding and curr_close < trend_ma:
                direction = "sell"
                breakout_distance = (donchian_l - curr_close) / curr_atr
                vol_boost = min(0.20, (curr_vol_ratio - 1.0) * 0.1)
                dist_boost = min(0.15, breakout_distance * 0.05)
                confidence = float(np.clip(0.65 + vol_boost + dist_boost, 0.50, 0.95))
                rationale = (
                    f"Short Dynamic Donchian Expansion: Close ({curr_close:.2f}) < Band Low ({donchian_l:.2f}), "
                    f"Volume Ratio {curr_vol_ratio:.2f}x >= {self.vol_expansion_threshold}x, "
                    f"Bandwidth Expansion {curr_bandwidth:.4f} > MA {curr_bandwidth_ma:.4f}"
                )
                tags.extend(["bearish_breakout", "volume_expansion", "trend_aligned"])

            valid_signal = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid_signal,
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
                rationale=f"Calculation error: {str(e)}",
                tags=["error", "xtiusd"]
            )