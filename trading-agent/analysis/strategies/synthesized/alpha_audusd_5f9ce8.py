from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_5f9ce8(EdgeStrategy):
    strategy_id: str = "alpha_audusd_5f9ce8"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H1")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "M15")
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 100))
        self.ltf_lookback: int = int(self.settings.get("ltf_lookback", 60))
        self.pivot_window: int = int(self.settings.get("pivot_window", 3))
        self.sweep_lookback_ltf: int = int(self.settings.get("sweep_lookback_ltf", 8))
        self.displacement_atr_mult: float = float(self.settings.get("displacement_atr_mult", 1.25))
        self.min_body_ratio: float = float(self.settings.get("min_body_ratio", 0.60))

    def _to_dataframe(self, candles: List[Any]) -> pd.DataFrame:
        data = []
        for c in candles:
            if hasattr(c, "open"):
                o, h, l, cl = float(c.open), float(c.high), float(c.low), float(c.close)
                v = float(c.volume) if hasattr(c, "volume") else 0.0
            else:
                o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
                v = float(c["volume"]) if "volume" in c else 0.0
            data.append({"open": o, "high": h, "low": l, "close": cl, "volume": v})
        return pd.DataFrame(data)

    def _find_htf_pivots(self, df: pd.DataFrame, window: int) -> tuple[List[float], List[float]]:
        highs = df["high"].values
        lows = df["low"].values
        n = len(df)
        pivot_highs = []
        pivot_lows = []

        for i in range(window, n - window):
            current_h = highs[i]
            current_l = lows[i]
            
            if all(current_h > highs[i - k] for k in range(1, window + 1)) and \
               all(current_h >= highs[i + k] for k in range(1, window + 1)):
                pivot_highs.append(float(current_h))

            if all(current_l < lows[i - k] for k in range(1, window + 1)) and \
               all(current_l <= lows[i + k] for k in range(1, window + 1)):
                pivot_lows.append(float(current_l))

        return pivot_highs, pivot_lows

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> np.ndarray:
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.zeros(len(df))
        
        tr[0] = high[0] - low[0]
        for i in range(1, len(df)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        
        atr = pd.Series(tr).rolling(window=period, min_periods=period).mean().bfill().values
        return atr

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Symbol not applicable for AUDUSD liquidity sweep strategy.",
                tags=["ineligible_symbol"]
            )

        htf_candles = await self.get_historical_candles(
            session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=self.htf_lookback
        )
        ltf_candles = await self.get_historical_candles(
            session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=self.ltf_lookback
        )

        if not htf_candles or len(htf_candles) < self.htf_lookback * 0.5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient HTF candle data.",
                tags=["insufficient_htf_data"]
            )

        if not ltf_candles or len(ltf_candles) < self.ltf_lookback * 0.5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient LTF candle data.",
                tags=["insufficient_ltf_data"]
            )

        df_htf = self._to_dataframe(htf_candles)
        df_ltf = self._to_dataframe(ltf_candles)

        pivot_highs, pivot_lows = self._find_htf_pivots(df_htf, self.pivot_window)
        if not pivot_highs or not pivot_lows:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No distinct HTF liquidity pools detected.",
                tags=["no_pivots"]
            )

        # Recent key liquidity targets within 20 HTF bars
        recent_p_highs = pivot_highs[-4:]
        recent_p_lows = pivot_lows[-4:]

        atr_ltf = self._calculate_atr(df_ltf, period=14)
        latest_atr = atr_ltf[-1]

        recent_ltf_slice = df_ltf.iloc[-self.sweep_lookback_ltf:]
        current_candle = df_ltf.iloc[-1]
        prev_candle = df_ltf.iloc[-2]

        current_range = current_candle["high"] - current_candle["low"]
        current_body = abs(current_candle["close"] - current_candle["open"])
        body_ratio = current_body / current_range if current_range > 0 else 0.0

        is_displacement_bullish = (
            current_candle["close"] > current_candle["open"] and
            current_range >= latest_atr * self.displacement_atr_mult and
            body_ratio >= self.min_body_ratio and
            current_candle["close"] > prev_candle["high"]
        )

        is_displacement_bearish = (
            current_candle["close"] < current_candle["open"] and
            current_range >= latest_atr * self.displacement_atr_mult and
            body_ratio >= self.min_body_ratio and
            current_candle["close"] < prev_candle["low"]
        )

        # 1. Bullish Liquidity Sweep & Displacement Check
        # LTF swept below a major HTF low within lookback window, but closed firmly above it with displacement
        for p_low in recent_p_lows:
            min_recent_low = recent_ltf_slice["low"].min()
            swept = min_recent_low < p_low
            reclaimed = current_candle["close"] > p_low

            if swept and reclaimed and is_displacement_bullish:
                sweep_depth = (p_low - min_recent_low) / (latest_atr + 1e-6)
                disp_strength = current_range / (latest_atr + 1e-6)
                confidence = min(0.92, max(0.55, 0.50 + (disp_strength * 0.15) + (min(sweep_depth, 1.5) * 0.10)))

                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=float(round(confidence, 4)),
                    rationale=f"Bullish sell-side liquidity sweep at {p_low:.5f} with impulsive displacement reclamation.",
                    tags=["liquidity_sweep", "ssl_sweep", "bullish_displacement", "audusd"]
                )

        # 2. Bearish Liquidity Sweep & Displacement Check
        # LTF swept above a major HTF high within lookback window, but closed firmly below it with displacement
        for p_high in recent_p_highs:
            max_recent_high = recent_ltf_slice["high"].max()
            swept = max_recent_high > p_high
            rejected = current_candle["close"] < p_high

            if swept and rejected and is_displacement_bearish:
                sweep_depth = (max_recent_high - p_high) / (latest_atr + 1e-6)
                disp_strength = current_range / (latest_atr + 1e-6)
                confidence = min(0.92, max(0.55, 0.50 + (disp_strength * 0.15) + (min(sweep_depth, 1.5) * 0.10)))

                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=float(round(confidence, 4)),
                    rationale=f"Bearish buy-side liquidity sweep at {p_high:.5f} with impulsive displacement rejection.",
                    tags=["liquidity_sweep", "bsl_sweep", "bearish_displacement", "audusd"]
                )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale="No active multi-timeframe liquidity sweep displacement pattern identified.",
            tags=["no_setup"]
        )