from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_a84e8d(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_a84e8d"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.rvol_threshold: float = float(self.settings.get("rvol_threshold", 1.2))
        self.expansion_factor: float = float(self.settings.get("expansion_factor", 0.15))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.min_history_required: int = max(self.donchian_period, self.volume_ma_period, self.atr_period) + 15

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

        donchian_period = int(settings.get("donchian_period", self.donchian_period))
        atr_period = int(settings.get("atr_period", self.atr_period))
        vol_period = int(settings.get("volume_ma_period", self.volume_ma_period))
        rvol_thresh = float(settings.get("rvol_threshold", self.rvol_threshold))
        expansion_factor = float(settings.get("expansion_factor", self.expansion_factor))
        timeframe = str(settings.get("timeframe", self.timeframe))

        limit = max(donchian_period, vol_period, atr_period) + 50
        candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe=timeframe, limit=limit)

        if not candles or len(candles) < self.min_history_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for volume-weighted Donchian expansion analysis.",
                tags=["insufficient_data"]
            )

        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
        volumes: List[float] = []

        for c in candles:
            try:
                h = float(c.high)
                l = float(c.low)
                cl = float(c.close)
                v = float(c.volume)
            except AttributeError:
                h = float(c["high"])
                l = float(c["low"])
                cl = float(c["close"])
                v = float(c["volume"])
            highs.append(h)
            lows.append(l)
            closes.append(cl)
            volumes.append(max(v, 1.0))

        df = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })

        # Calculate True Range and ATR
        df["prev_close"] = df["close"].shift(1)
        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = (df["high"] - df["prev_close"]).abs()
        df["tr3"] = (df["low"] - df["prev_close"]).abs()
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["tr"].rolling(window=atr_period).mean()

        # Volume Moving Average & RVOL
        df["vol_sma"] = df["volume"].rolling(window=vol_period).mean()
        df["rvol"] = df["volume"] / df["vol_sma"].replace(0, np.nan)
        df["rvol"] = df["rvol"].fillna(1.0)

        # Volume-Weighted Average Price (Rolling VWAP approximation)
        df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
        df["vp"] = df["typical_price"] * df["volume"]
        df["vwap"] = df["vp"].rolling(window=donchian_period).sum() / df["volume"].rolling(window=donchian_period).sum()

        # Standard Donchian Channels (Excluding current candle to identify true breakout)
        df["prior_donchian_high"] = df["high"].shift(1).rolling(window=donchian_period).max()
        df["prior_donchian_low"] = df["low"].shift(1).rolling(window=donchian_period).min()

        # Dynamic Volume-Weighted Expansion Offsets
        # When volume surges above average, the threshold expands to capture institutional displacement momentum
        df["vol_weight"] = np.clip(df["rvol"], 0.5, 3.0)
        df["dynamic_upper"] = df["prior_donchian_high"] + (df["atr"] * expansion_factor * (df["vol_weight"] - 1.0).clip(lower=0.0))
        df["dynamic_lower"] = df["prior_donchian_low"] - (df["atr"] * expansion_factor * (df["vol_weight"] - 1.0).clip(lower=0.0))

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        curr_close = float(last_row["close"])
        curr_rvol = float(last_row["rvol"])
        curr_atr = float(last_row["atr"])
        curr_vwap = float(last_row["vwap"]) if not math.isnan(last_row["vwap"]) else curr_close
        dynamic_upper = float(last_row["dynamic_upper"])
        dynamic_lower = float(last_row["dynamic_lower"])
        prior_upper = float(last_row["prior_donchian_high"])
        prior_lower = float(last_row["prior_donchian_low"])

        # Breakout Conditions
        long_expansion = (curr_close > dynamic_upper) and (curr_close > curr_vwap) and (curr_rvol >= rvol_thresh)
        short_expansion = (curr_close < dynamic_lower) and (curr_close < curr_vwap) and (curr_rvol >= rvol_thresh)

        # Volatility expansion confirmation (ATR trend)
        atr_expanding = curr_atr > float(prev_row["atr"])

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = ""
        tags: List[str] = ["donchian", "volume_weighted", "volatility_expansion"]

        if long_expansion:
            direction = "buy"
            excess_move = (curr_close - dynamic_upper) / max(curr_atr, 0.01)
            vol_boost = min((curr_rvol - rvol_thresh) * 0.15, 0.25)
            atr_boost = 0.10 if atr_expanding else 0.0
            base_conf = 0.65
            confidence = min(0.95, base_conf + min(excess_move * 0.1, 0.15) + vol_boost + atr_boost)
            rationale = (
                f"XAUUSD Bullish Dynamic Donchian Expansion: Close {curr_close:.2f} broke above "
                f"Dynamic Upper {dynamic_upper:.2f} (Prior High: {prior_upper:.2f}) with RVOL {curr_rvol:.2f} "
                f"and VWAP alignment ({curr_vwap:.2f})."
            )
            tags.extend(["bullish_breakout", "high_rvol"])

        elif short_expansion:
            direction = "sell"
            excess_move = (dynamic_lower - curr_close) / max(curr_atr, 0.01)
            vol_boost = min((curr_rvol - rvol_thresh) * 0.15, 0.25)
            atr_boost = 0.10 if atr_expanding else 0.0
            base_conf = 0.65
            confidence = min(0.95, base_conf + min(excess_move * 0.1, 0.15) + vol_boost + atr_boost)
            rationale = (
                f"XAUUSD Bearish Dynamic Donchian Expansion: Close {curr_close:.2f} broke below "
                f"Dynamic Lower {dynamic_lower:.2f} (Prior Low: {prior_lower:.2f}) with RVOL {curr_rvol:.2f} "
                f"and VWAP alignment ({curr_vwap:.2f})."
            )
            tags.extend(["bearish_breakdown", "high_rvol"])

        else:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=(
                    f"No volume-weighted Donchian expansion detected on XAUUSD. "
                    f"Close: {curr_close:.2f}, Range: [{dynamic_lower:.2f}, {dynamic_upper:.2f}], "
                    f"RVOL: {curr_rvol:.2f} vs Thresh: {rvol_thresh:.2f}."
                ),
                tags=["neutral_consolidation"]
            )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=True,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )