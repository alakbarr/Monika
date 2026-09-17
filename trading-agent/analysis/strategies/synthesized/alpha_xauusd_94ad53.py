from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_94ad53(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_94ad53"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H1")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "M15")
        self.htf_swing_window: int = int(self.settings.get("htf_swing_window", 5))
        self.displacement_body_ratio: float = float(self.settings.get("displacement_body_ratio", 0.60))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.atr_multiplier: float = float(self.settings.get("atr_multiplier", 1.25))

    def _parse_candles(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        records = []
        for c in candles:
            if isinstance(c, dict):
                o = float(c.get("open", 0.0))
                h = float(c.get("high", 0.0))
                l = float(c.get("low", 0.0))
                cl = float(c.get("close", 0.0))
                v = float(c.get("volume", 0.0))
            else:
                o = float(c.open)
                h = float(c.high)
                l = float(c.low)
                cl = float(c.close)
                try:
                    v = float(c.volume)
                except Exception:
                    v = 0.0
            records.append({"open": o, "high": h, "low": l, "close": cl, "volume": v})
        df = pd.DataFrame(records)
        return df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        if len(df) < 2:
            return pd.Series(0.0, index=df.index)
        high_low = df["high"] - df["low"]
        high_prev_close = (df["high"] - df["close"].shift(1)).abs()
        low_prev_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean().fillna(0.0)
        return atr

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported. Applicable: {self.applicable_symbols}",
                    tags=["unsupported_symbol"]
                )

            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=80
            )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=60
            )

            df_htf = self._parse_candles(htf_candles)
            df_ltf = self._parse_candles(ltf_candles)

            min_required = max(self.htf_swing_window * 2 + 5, self.atr_period + 5)
            if len(df_htf) < min_required or len(df_ltf) < min_required:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. HTF: {len(df_htf)}, LTF: {len(df_ltf)}",
                    tags=["insufficient_data"]
                )

            # Identify prominent HTF Swing Highs and Lows
            w = self.htf_swing_window
            htf_highs = df_htf["high"].values
            htf_lows = df_htf["low"].values
            
            swing_highs = []
            swing_lows = []
            for i in range(w, len(df_htf) - 1):
                window_high = np.max(htf_highs[i - w : i + w + 1])
                window_low = np.min(htf_lows[i - w : i + w + 1])
                if htf_highs[i] == window_high:
                    swing_highs.append(htf_highs[i])
                if htf_lows[i] == window_low:
                    swing_lows.append(htf_lows[i])

            if not swing_highs or not swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No clear HTF swing liquidity levels identified.",
                    tags=["no_swing_levels"]
                )

            key_swing_high = float(swing_highs[-1])
            key_swing_low = float(swing_lows[-1])

            # Analyze LTF dynamics for sweep and displacement
            ltf_atr = self._calculate_atr(df_ltf, self.atr_period)
            recent_ltf = df_ltf.iloc[-8:].copy().reset_index(drop=True)
            current_bar = df_ltf.iloc[-1]
            prev_bar = df_ltf.iloc[-2]
            current_atr = float(ltf_atr.iloc[-1]) if float(ltf_atr.iloc[-1]) > 0 else 1.0

            bullish_sweep = False
            bearish_sweep = False
            sweep_price = 0.0

            # Scan the last 6 LTF bars for liquidity pool penetration and rejection
            for idx in range(len(recent_ltf) - 1):
                row = recent_ltf.iloc[idx]
                if row["low"] < key_swing_low and row["close"] > key_swing_low:
                    bullish_sweep = True
                    sweep_price = float(row["low"])
                elif row["low"] < key_swing_low and recent_ltf.iloc[idx + 1]["close"] > key_swing_low:
                    bullish_sweep = True
                    sweep_price = float(row["low"])

                if row["high"] > key_swing_high and row["close"] < key_swing_high:
                    bearish_sweep = True
                    sweep_price = float(row["high"])
                elif row["high"] > key_swing_high and recent_ltf.iloc[idx + 1]["close"] < key_swing_high:
                    bearish_sweep = True
                    sweep_price = float(row["high"])

            # Displacement evaluation on recent/current candle
            c_range = max(0.001, float(current_bar["high"] - current_bar["low"]))
            c_body = abs(float(current_bar["close"] - current_bar["open"]))
            c_body_ratio = c_body / c_range

            p_range = max(0.001, float(prev_bar["high"] - prev_bar["low"]))
            p_body = abs(float(prev_bar["close"] - prev_bar["open"]))
            p_body_ratio = p_body / p_range

            is_bullish_displacement = (
                (c_body_ratio >= self.displacement_body_ratio and current_bar["close"] > current_bar["open"] and c_range >= self.atr_multiplier * current_atr) or
                (p_body_ratio >= self.displacement_body_ratio and prev_bar["close"] > prev_bar["open"] and p_range >= self.atr_multiplier * current_atr and current_bar["close"] >= prev_bar["close"])
            )

            is_bearish_displacement = (
                (c_body_ratio >= self.displacement_body_ratio and current_bar["close"] < current_bar["open"] and c_range >= self.atr_multiplier * current_atr) or
                (p_body_ratio >= self.displacement_body_ratio and prev_bar["close"] < prev_bar["open"] and p_range >= self.atr_multiplier * current_atr and current_bar["close"] <= prev_bar["close"])
            )

            # Fair Value Gap (FVG) detection on LTF
            bullish_fvg = len(df_ltf) >= 3 and (df_ltf["low"].iloc[-1] > df_ltf["high"].iloc[-3])
            bearish_fvg = len(df_ltf) >= 3 and (df_ltf["high"].iloc[-1] < df_ltf["low"].iloc[-3])

            direction = None
            confidence = 0.0
            rationale_msg = ""
            tags = ["liquidity_sweep", "displacement", "xauusd"]

            if bullish_sweep and is_bullish_displacement:
                direction = "buy"
                base_conf = 0.70
                if bullish_fvg:
                    base_conf += 0.10
                    tags.append("fvg_created")
                if c_range >= 1.75 * current_atr or p_range >= 1.75 * current_atr:
                    base_conf += 0.08
                    tags.append("strong_expansion")
                confidence = min(0.92, round(base_conf, 2))
                rationale_msg = (
                    f"Bullish Liquidity Sweep at {sweep_price:.2f} below HTF Swing Low ({key_swing_low:.2f}) "
                    f"followed by strong LTF upward displacement (Body Ratio: {c_body_ratio:.2f}, ATR: {current_atr:.2f})."
                )
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=rationale_msg,
                    tags=tags
                )

            elif bearish_sweep and is_bearish_displacement:
                direction = "sell"
                base_conf = 0.70
                if bearish_fvg:
                    base_conf += 0.10
                    tags.append("fvg_created")
                if c_range >= 1.75 * current_atr or p_range >= 1.75 * current_atr:
                    base_conf += 0.08
                    tags.append("strong_expansion")
                confidence = min(0.92, round(base_conf, 2))
                rationale_msg = (
                    f"Bearish Liquidity Sweep at {sweep_price:.2f} above HTF Swing High ({key_swing_high:.2f}) "
                    f"followed by strong LTF downward displacement (Body Ratio: {c_body_ratio:.2f}, ATR: {current_atr:.2f})."
                )
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale=rationale_msg,
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No MTF sweep-displacement confluence. HTF Levels: Low {key_swing_low:.2f}, High {key_swing_high:.2f}.",
                tags=["neutral", "monitoring"]
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