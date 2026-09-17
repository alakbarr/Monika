from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_50c0eb(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_50c0eb"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H4")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "M15")
        self.htf_pivot_window: int = int(self.settings.get("htf_pivot_window", 5))
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.4))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.sweep_lookback_bars: int = int(self.settings.get("sweep_lookback_bars", 6))

    def _extract_dataframe(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        
        rows = []
        for c in candles:
            if isinstance(c, dict):
                rows.append({
                    "open": float(c.get("open", 0.0)),
                    "high": float(c.get("high", 0.0)),
                    "low": float(c.get("low", 0.0)),
                    "close": float(c.get("close", 0.0)),
                    "volume": float(c.get("volume", 0.0)),
                })
            else:
                rows.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume) if hasattr(c, "volume") else 0.0,
                })
        df = pd.DataFrame(rows)
        df = df.ffill().bfill().fillna(0.0)
        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        if len(df) < 2:
            return pd.Series(np.zeros(len(df)), index=df.index)
        
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1).ffill().bfill()
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.ffill().bfill().fillna(0.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not in applicable symbols: {self.applicable_symbols}",
                    tags=["unsupported_symbol"]
                )

            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=80
            )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=100
            )

            if not htf_candles or len(htf_candles) < 20:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient HTF ({self.htf_timeframe}) candles.",
                    tags=["insufficient_data", "htf_data_missing"]
                )

            if not ltf_candles or len(ltf_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient LTF ({self.ltf_timeframe}) candles.",
                    tags=["insufficient_data", "ltf_data_missing"]
                )

            htf_df = self._extract_dataframe(htf_candles)
            ltf_df = self._extract_dataframe(ltf_candles)

            # Identify HTF liquidity levels (Swing Highs / Swing Lows)
            window = self.htf_pivot_window
            htf_swing_highs = []
            htf_swing_lows = []

            for i in range(window, len(htf_df) - 1):
                center_high = htf_df["high"].iloc[i]
                left_highs = htf_df["high"].iloc[i - window : i]
                right_highs = htf_df["high"].iloc[i + 1 : min(i + window + 1, len(htf_df))]
                if (center_high > left_highs.max()) and (center_high >= right_highs.max()):
                    htf_swing_highs.append(center_high)

                center_low = htf_df["low"].iloc[i]
                left_lows = htf_df["low"].iloc[i - window : i]
                right_lows = htf_df["low"].iloc[i + 1 : min(i + window + 1, len(htf_df))]
                if (center_low < left_lows.min()) and (center_low <= right_lows.min()):
                    htf_swing_lows.append(center_low)

            if not htf_swing_highs or not htf_swing_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No distinct HTF pivot liquidity levels identified.",
                    tags=["no_liquidity_pool"]
                )

            # Calculate LTF ATR and candle properties
            ltf_atr = self._calculate_atr(ltf_df, self.atr_period)
            curr_atr = float(ltf_atr.iloc[-1])
            if curr_atr <= 0:
                curr_atr = 1.0

            recent_ltf = ltf_df.iloc[-self.sweep_lookback_bars:]
            current_bar = ltf_df.iloc[-1]
            prev_bar = ltf_df.iloc[-2]

            current_body = abs(current_bar["close"] - current_bar["open"])
            is_displacement = current_body >= (self.displacement_multiplier * curr_atr)

            # Check Bearish Sweep: LTF swept HTF swing high and displaced downwards
            bearish_signal = False
            swept_high_level = None
            for swing_high in reversed(htf_swing_highs[-5:]):
                # Sweep condition: High exceeded swing high within lookback, but current close is back below
                if (recent_ltf["high"].max() > swing_high) and (current_bar["close"] < swing_high):
                    swept_high_level = swing_high
                    if is_displacement and (current_bar["close"] < current_bar["open"]) and (current_bar["close"] < prev_bar["low"]):
                        bearish_signal = True
                        break

            # Check Bullish Sweep: LTF swept HTF swing low and displaced upwards
            bullish_signal = False
            swept_low_level = None
            for swing_low in reversed(htf_swing_lows[-5:]):
                # Sweep condition: Low penetrated swing low within lookback, but current close is back above
                if (recent_ltf["low"].min() < swing_low) and (current_bar["close"] > swing_low):
                    swept_low_level = swing_low
                    if is_displacement and (current_bar["close"] > current_bar["open"]) and (current_bar["close"] > prev_bar["high"]):
                        bullish_signal = True
                        break

            if bullish_signal and not bearish_signal:
                disp_ratio = current_body / curr_atr
                confidence = min(0.92, max(0.60, 0.60 + (disp_ratio - self.displacement_multiplier) * 0.15))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=float(round(confidence, 4)),
                    rationale=f"Bullish liquidity sweep of HTF swing low ({swept_low_level:.2f}) confirmed by {disp_ratio:.2f}x ATR displacement upward.",
                    tags=["liquidity_sweep", "bullish_displacement", "mtf_structure", "reversal"]
                )

            if bearish_signal and not bullish_signal:
                disp_ratio = current_body / curr_atr
                confidence = min(0.92, max(0.60, 0.60 + (disp_ratio - self.displacement_multiplier) * 0.15))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=float(round(confidence, 4)),
                    rationale=f"Bearish liquidity sweep of HTF swing high ({swept_high_level:.2f}) confirmed by {disp_ratio:.2f}x ATR displacement downward.",
                    tags=["liquidity_sweep", "bearish_displacement", "mtf_structure", "reversal"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=True,
                confidence=0.0,
                rationale="No MTF liquidity sweep and displacement pattern triggered.",
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