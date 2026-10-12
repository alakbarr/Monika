from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_2c4e39(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_2c4e39"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe: str = self.settings.get("timeframe", "H1")
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.volume_threshold: float = float(self.settings.get("volume_threshold", 1.25))
        self.expansion_mult: float = float(self.settings.get("expansion_mult", 0.35))
        self.lookback_limit: int = int(self.settings.get("lookback_limit", 120))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by {self.strategy_id}.",
                tags=["unsupported_symbol"]
            )

        candles = await self.get_historical_candles(
            session=session,
            symbol=symbol,
            timeframe=self.timeframe,
            limit=self.lookback_limit
        )

        min_required = max(self.donchian_period, self.atr_period, self.volume_ma_period) + 5
        if not candles or len(candles) < min_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history. Need at least {min_required} candles.",
                tags=["insufficient_data"]
            )

        # Parse candle sequence into tabular structure
        records = []
        for c in candles:
            records.append({
                "open": float(c.open if hasattr(c, "open") else c["open"]),
                "high": float(c.high if hasattr(c, "high") else c["high"]),
                "low": float(c.low if hasattr(c, "low") else c["low"]),
                "close": float(c.close if hasattr(c, "close") else c["close"]),
                "volume": float(c.volume if hasattr(c, "volume") else c.get("volume", 1.0))
            })

        df = pd.DataFrame(records)

        # True Range and ATR
        prev_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()
        df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = df["tr"].rolling(window=self.atr_period).mean()

        # Donchian Boundaries (calculated over prior period to avoid lookahead bias)
        df["donchian_high"] = df["high"].shift(1).rolling(window=self.donchian_period).max()
        df["donchian_low"] = df["low"].shift(1).rolling(window=self.donchian_period).min()
        df["donchian_mid"] = (df["donchian_high"] + df["donchian_low"]) / 2.0

        # Volume Dynamics & Dynamic Expansion Threshold
        df["vol_sma"] = df["volume"].rolling(window=self.volume_ma_period).mean().replace(0, 1.0)
        df["vol_ratio"] = df["volume"] / df["vol_sma"]

        # Dynamic Volume-Weighted Expansion Offset
        # Higher volume relative to baseline expands dynamic breakout threshold buffer
        df["dynamic_buffer"] = df["atr"] * self.expansion_mult * np.clip(df["vol_ratio"], 0.5, 3.0)
        df["dyn_upper"] = df["donchian_high"] + df["dynamic_buffer"]
        df["dyn_lower"] = df["donchian_low"] - df["dynamic_buffer"]

        # Volatility expansion check: ATR relative to its recent average
        df["atr_baseline"] = df["atr"].rolling(window=self.donchian_period).mean()

        latest = df.iloc[-1]
        prior = df.iloc[-2]

        curr_close = latest["close"]
        don_high = latest["donchian_high"]
        don_low = latest["donchian_low"]
        vol_ratio = latest["vol_ratio"]
        atr_curr = latest["atr"]
        atr_base = latest["atr_baseline"]

        if math.isnan(don_high) or math.isnan(don_low) or math.isnan(atr_curr) or atr_curr <= 0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Indicators contained NaN values.",
                tags=["calculation_error"]
            )

        is_volume_expanded = vol_ratio >= self.volume_threshold
        is_volatility_expanded = atr_curr >= atr_base

        # Signal Logic
        direction = None
        confidence = 0.0
        rationale_parts = []
        tags = ["volume_weighted_donchian", "dynamic_expansion"]

        # Bullish Breakout: Close crosses above standard Donchian High with volume confirmation
        if curr_close > don_high and prior["close"] <= prior["donchian_high"]:
            if is_volume_expanded and is_volatility_expanded:
                direction = "buy"
                # Scale confidence by magnitude of volume surge and clean channel breakout
                vol_boost = min(0.35, (vol_ratio - self.volume_threshold) * 0.2)
                breakout_pct = (curr_close - don_high) / atr_curr
                breakout_boost = min(0.25, max(0.0, breakout_pct * 0.15))
                confidence = float(np.clip(0.65 + vol_boost + breakout_boost, 0.50, 0.95))

                rationale_parts.append(
                    f"Bullish Donchian breakout ({curr_close:.2f} > {don_high:.2f}) "
                    f"with volume surge (VR={vol_ratio:.2f}x, ATR={atr_curr:.2f} vs Base={atr_base:.2f})"
                )
                tags.append("bullish_expansion_breakout")

        # Bearish Breakdown: Close crosses below standard Donchian Low with volume confirmation
        elif curr_close < don_low and prior["close"] >= prior["donchian_low"]:
            if is_volume_expanded and is_volatility_expanded:
                direction = "sell"
                vol_boost = min(0.35, (vol_ratio - self.volume_threshold) * 0.2)
                breakout_pct = (don_low - curr_close) / atr_curr
                breakout_boost = min(0.25, max(0.0, breakout_pct * 0.15))
                confidence = float(np.clip(0.65 + vol_boost + breakout_boost, 0.50, 0.95))

                rationale_parts.append(
                    f"Bearish Donchian breakdown ({curr_close:.2f} < {don_low:.2f}) "
                    f"with volume surge (VR={vol_ratio:.2f}x, ATR={atr_curr:.2f} vs Base={atr_base:.2f})"
                )
                tags.append("bearish_expansion_breakdown")

        if direction is None:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No breakout detected. Price {curr_close:.2f} within range [{don_low:.2f}, {don_high:.2f}]. VR={vol_ratio:.2f}.",
                tags=["neutral"]
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=True,
            confidence=round(confidence, 4),
            rationale="; ".join(rationale_parts),
            tags=tags
        )