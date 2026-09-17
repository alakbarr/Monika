from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_8acf60(EdgeStrategy):
    strategy_id: str = "alpha_audusd_8acf60"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 24))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.displacement_mult: float = float(self.settings.get("displacement_mult", 1.1))
        self.sweep_tolerance_pips: float = float(self.settings.get("sweep_tolerance_pips", 0.0003))

    def _to_dataframe(self, candles: List[Any]) -> pd.DataFrame:
        records = []
        for c in candles:
            try:
                records.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume) if c.volume is not None else 0.0
                })
            except (AttributeError, TypeError):
                records.append({
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0.0) or 0.0)
                })
        df = pd.DataFrame(records)
        return df.ffill().bfill().fillna(0.0)

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.ffill().bfill().fillna(0.001)

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

            candles_h1 = await self.get_historical_candles(session=session, symbol=symbol, timeframe="H1", limit=60)
            candles_m15 = await self.get_historical_candles(session=session, symbol=symbol, timeframe="M15", limit=60)

            if not candles_h1 or len(candles_h1) < self.htf_lookback + 2 or not candles_m15 or len(candles_m15) < 20:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical candle depth for HTF liquidity sweep evaluation",
                    tags=["insufficient_data"]
                )

            df_h1 = self._to_dataframe(candles_h1)
            df_m15 = self._to_dataframe(candles_m15)

            # Extract HTF major liquidity pools (excluding current running bar)
            lookback_slice = df_h1.iloc[-(self.htf_lookback + 1):-1]
            htf_pool_high = lookback_slice["high"].max()
            htf_pool_low = lookback_slice["low"].min()

            # M15 ATR for displacement thresholding
            atr_m15 = self._calc_atr(df_m15, period=self.atr_period)
            current_atr = float(atr_m15.iloc[-1])
            displacement_req = current_atr * self.displacement_mult

            # Inspect recent lower-timeframe bars (last 4 bars)
            recent_m15 = df_m15.iloc[-4:]
            curr_bar = df_m15.iloc[-1]
            prev_bar = df_m15.iloc[-2]

            swept_high = float(recent_m15["high"].max()) >= (htf_pool_high - self.sweep_tolerance_pips)
            swept_low = float(recent_m15["low"].min()) <= (htf_pool_low + self.sweep_tolerance_pips)

            curr_body = curr_bar["close"] - curr_bar["open"]
            prev_body = prev_bar["close"] - prev_bar["open"]

            direction: Optional[str] = None
            rationale: str = ""
            confidence: float = 0.0
            tags: List[str] = ["liquidity_sweep", "displacement", "mtf"]

            # Bearish Liquidity Sweep Displacement
            # Condition: Swept HTF high, failed to sustain, current/prev bar exhibits aggressive bearish displacement
            if swept_high and curr_bar["close"] < htf_pool_high:
                bearish_displacement = (-curr_body >= displacement_req) or (-prev_body >= displacement_req and curr_body <= 0)
                market_structure_break = curr_bar["close"] < recent_m15["low"].iloc[:-1].min()

                if bearish_displacement and (market_structure_break or curr_bar["close"] < prev_bar["low"]):
                    direction = "sell"
                    disp_strength = max(-curr_body, -prev_body) / max(current_atr, 0.0001)
                    confidence = min(0.92, 0.65 + min(0.20, (disp_strength - 1.0) * 0.15))
                    rationale = (
                        f"AUDUSD swept H1 buy-side liquidity at {htf_pool_high:.5f} followed by strong "
                        f"M15 bearish displacement (body: {-curr_body:.5f}, ATR: {current_atr:.5f}) and structure break."
                    )
                    tags.extend(["bearish_sweep", "liquidity_reversal"])

            # Bullish Liquidity Sweep Displacement
            # Condition: Swept HTF low, rejected lower prices, current/prev bar exhibits aggressive bullish displacement
            elif swept_low and curr_bar["close"] > htf_pool_low:
                bullish_displacement = (curr_body >= displacement_req) or (prev_body >= displacement_req and curr_body >= 0)
                market_structure_break = curr_bar["close"] > recent_m15["high"].iloc[:-1].max()

                if bullish_displacement and (market_structure_break or curr_bar["close"] > prev_bar["high"]):
                    direction = "buy"
                    disp_strength = max(curr_body, prev_body) / max(current_atr, 0.0001)
                    confidence = min(0.92, 0.65 + min(0.20, (disp_strength - 1.0) * 0.15))
                    rationale = (
                        f"AUDUSD swept H1 sell-side liquidity at {htf_pool_low:.5f} followed by strong "
                        f"M15 bullish displacement (body: {curr_body:.5f}, ATR: {current_atr:.5f}) and structure break."
                    )
                    tags.extend(["bullish_sweep", "liquidity_reversal"])

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=float(np.round(confidence, 4)),
                    rationale=rationale,
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No confirmed liquidity sweep and displacement setup on {symbol}. HTF High: {htf_pool_high:.5f}, Low: {htf_pool_low:.5f}",
                tags=["no_setup"]
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