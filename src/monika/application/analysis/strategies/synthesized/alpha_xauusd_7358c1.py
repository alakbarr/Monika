from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_7358c1(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_7358c1"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.donchian_period: int = int(self.settings.get("donchian_period", 20))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.volume_expansion_threshold: float = float(self.settings.get("volume_expansion_threshold", 1.25))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.history_limit: int = int(self.settings.get("history_limit", 100))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} is not supported by {self.strategy_id}",
                tags=["unsupported_symbol"]
            )

        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.history_limit
            )

            if not candles or len(candles) < max(self.donchian_period, self.atr_period, self.volume_ma_period) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle data for evaluation",
                    tags=["insufficient_data"]
                )

            data: List[Dict[str, float]] = []
            for c in candles:
                if isinstance(c, dict):
                    data.append({
                        "open": float(c.get("open", 0.0)),
                        "high": float(c.get("high", 0.0)),
                        "low": float(c.get("low", 0.0)),
                        "close": float(c.get("close", 0.0)),
                        "volume": float(c.get("volume", 1.0))
                    })
                else:
                    vol = float(c.volume) if hasattr(c, "volume") else 1.0
                    data.append({
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": vol
                    })

            df = pd.DataFrame(data)

            # Sanitize inputs
            df = df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            # ATR Calculation
            df["prev_close"] = df["close"].shift(1).ffill()
            df["tr1"] = df["high"] - df["low"]
            df["tr2"] = (df["high"] - df["prev_close"]).abs()
            df["tr3"] = (df["low"] - df["prev_close"]).abs()
            df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
            df["atr"] = df["tr"].rolling(window=self.atr_period, min_periods=1).mean().ffill().bfill()

            # Volume Moving Average & Relative Volume
            df["vol_ma"] = df["volume"].rolling(window=self.volume_ma_period, min_periods=1).mean().ffill().bfill()
            df["vol_ratio"] = (df["volume"] / df["vol_ma"].replace(0.0, np.nan)).fillna(1.0)

            # Volume-Weighted Dynamic Donchian Channels
            # Shifted by 1 bar to strictly detect the fresh expansion breakout on the latest bar
            df["donchian_high"] = df["high"].shift(1).rolling(window=self.donchian_period, min_periods=1).max().ffill().bfill()
            df["donchian_low"] = df["low"].shift(1).rolling(window=self.donchian_period, min_periods=1).min().ffill().bfill()
            df["donchian_mid"] = (df["donchian_high"] + df["donchian_low"]) / 2.0

            # Dynamic Donchian Width and Expansion
            df["channel_width"] = (df["donchian_high"] - df["donchian_low"]).replace(0.0, 0.0001)
            df["width_ma"] = df["channel_width"].rolling(window=self.donchian_period, min_periods=1).mean().ffill().bfill()
            df["width_expansion"] = df["channel_width"] / df["width_ma"].replace(0.0, np.nan).fillna(1.0)

            # VWAP proxy over Donchian window
            df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
            df["tp_vol"] = df["typical_price"] * df["volume"]
            df["vwap"] = (
                df["tp_vol"].rolling(window=self.donchian_period, min_periods=1).sum() /
                df["volume"].rolling(window=self.donchian_period, min_periods=1).sum().replace(0.0, np.nan)
            ).ffill().bfill()

            last_idx = len(df) - 1
            curr_close = float(df["close"].iloc[last_idx])
            curr_high = float(df["high"].iloc[last_idx])
            curr_low = float(df["low"].iloc[last_idx])
            curr_vol_ratio = float(df["vol_ratio"].iloc[last_idx])
            curr_atr = float(df["atr"].iloc[last_idx])
            curr_donchian_high = float(df["donchian_high"].iloc[last_idx])
            curr_donchian_low = float(df["donchian_low"].iloc[last_idx])
            curr_vwap = float(df["vwap"].iloc[last_idx])
            curr_expansion = float(df["width_expansion"].iloc[last_idx])

            bullish_breakout = (curr_close > curr_donchian_high) and (curr_close > curr_vwap)
            bearish_breakout = (curr_close < curr_donchian_low) and (curr_close < curr_vwap)
            volume_confirmed = curr_vol_ratio >= self.volume_expansion_threshold

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["xauusd", "donchian_expansion", "volume_weighted"]

            if bullish_breakout and volume_confirmed:
                direction = "buy"
                breakout_extent = (curr_close - curr_donchian_high) / max(curr_atr, 0.01)
                vol_boost = min((curr_vol_ratio - self.volume_expansion_threshold) * 0.15, 0.25)
                conf_val = 0.65 + min(breakout_extent * 0.1, 0.15) + max(vol_boost, 0.0)
                confidence = float(np.clip(conf_val, 0.0, 0.95))
                tags.extend(["bullish_breakout", "volume_surge"])
                rationale_parts.append(
                    f"Bullish dynamic Donchian expansion: Close ({curr_close:.2f}) broke above {self.donchian_period}-period high ({curr_donchian_high:.2f})."
                )
                rationale_parts.append(f"Volume Ratio: {curr_vol_ratio:.2f}x MA. VWAP: {curr_vwap:.2f}.")

            elif bearish_breakout and volume_confirmed:
                direction = "sell"
                breakout_extent = (curr_donchian_low - curr_close) / max(curr_atr, 0.01)
                vol_boost = min((curr_vol_ratio - self.volume_expansion_threshold) * 0.15, 0.25)
                conf_val = 0.65 + min(breakout_extent * 0.1, 0.15) + max(vol_boost, 0.0)
                confidence = float(np.clip(conf_val, 0.0, 0.95))
                tags.extend(["bearish_breakout", "volume_surge"])
                rationale_parts.append(
                    f"Bearish dynamic Donchian expansion: Close ({curr_close:.2f}) broke below {self.donchian_period}-period low ({curr_donchian_low:.2f})."
                )
                rationale_parts.append(f"Volume Ratio: {curr_vol_ratio:.2f}x MA. VWAP: {curr_vwap:.2f}.")

            else:
                direction = None
                confidence = 0.0
                tags.append("neutral")
                rationale_parts.append(
                    f"No expansion trigger. Close: {curr_close:.2f}, High Band: {curr_donchian_high:.2f}, Low Band: {curr_donchian_low:.2f}, Vol Ratio: {curr_vol_ratio:.2f}x."
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=direction is not None,
                confidence=round(confidence, 4),
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