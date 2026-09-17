from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

logger = logging.getLogger(__name__)


class SynthesizedStrategy_alpha_btcusd_cbd98f(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_cbd98f"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe: str = self.settings.get("htf_timeframe", "H4")
        self.ltf_timeframe: str = self.settings.get("ltf_timeframe", "H1")
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 30))
        self.ltf_limit: int = int(self.settings.get("ltf_limit", 100))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.25))
        self.volume_ma_period: int = int(self.settings.get("volume_ma_period", 20))

    def _convert_candles_to_df(self, candles: List[Any]) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        records = []
        for c in candles:
            try:
                records.append({
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume)
                })
            except AttributeError:
                records.append({
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0.0))
                })
        df = pd.DataFrame(records)
        df = df.replace([np.inf, -np.inf], np.nan).dropna()
        return df

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.fillna(0.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by {self.strategy_id}",
                tags=["unsupported_symbol"]
            )

        try:
            # Fetch multi-timeframe candles: HTF for liquidity zones, LTF for sweep and displacement
            htf_candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.htf_timeframe,
                limit=self.htf_lookback + 10
            )
            ltf_candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.ltf_timeframe,
                limit=self.ltf_limit
            )

            df_htf = self._convert_candles_to_df(htf_candles)
            df_ltf = self._convert_candles_to_df(ltf_candles)

            if len(df_htf) < self.htf_lookback or len(df_ltf) < max(self.atr_period, self.volume_ma_period) + 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data for multi-timeframe analysis",
                    tags=["insufficient_data"]
                )

            # Identify HTF liquidity pools (swing high and swing low excluding the current candle)
            htf_window = df_htf.iloc[-self.htf_lookback - 1:-1]
            htf_liquidity_high = float(htf_window["high"].max())
            htf_liquidity_low = float(htf_window["low"].min())

            # LTF Technical Indicators
            df_ltf["atr"] = self._calculate_atr(df_ltf, period=self.atr_period)
            df_ltf["vol_ma"] = df_ltf["volume"].rolling(window=self.volume_ma_period, min_periods=1).mean().fillna(0.0)

            curr = df_ltf.iloc[-1]
            prev = df_ltf.iloc[-2]

            curr_open = float(curr["open"])
            curr_high = float(curr["high"])
            curr_low = float(curr["low"])
            curr_close = float(curr["close"])
            curr_vol = float(curr["volume"])
            curr_atr = float(curr["atr"])
            curr_vol_ma = float(curr["vol_ma"])

            prev_high = float(prev["high"])
            prev_low = float(prev["low"])
            prev_close = float(prev["close"])

            curr_body = abs(curr_close - curr_open)
            curr_range = max(curr_high - curr_low, 1e-8)

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_details: List[str] = []

            # 1. Bearish Liquidity Sweep & Displacement Logic
            # Condition A: Current or previous bar swept HTF high, and current bar exhibits bearish displacement
            sweep_high_occurred = (curr_high > htf_liquidity_high or prev_high > htf_liquidity_high)
            rejection_below_high = curr_close < htf_liquidity_high
            bearish_displacement = (
                curr_close < curr_open and
                curr_body >= self.displacement_multiplier * curr_atr and
                (curr_close - curr_low) / curr_range <= 0.35  # Closes in lower 35% of its range
            )

            # 2. Bullish Liquidity Sweep & Displacement Logic
            # Condition B: Current or previous bar swept HTF low, and current bar exhibits bullish displacement
            sweep_low_occurred = (curr_low < htf_liquidity_low or prev_low < htf_liquidity_low)
            rejection_above_low = curr_close > htf_liquidity_low
            bullish_displacement = (
                curr_close > curr_open and
                curr_body >= self.displacement_multiplier * curr_atr and
                (curr_high - curr_close) / curr_range <= 0.35  # Closes in upper 35% of its range
            )

            if sweep_high_occurred and rejection_below_high and bearish_displacement:
                direction = "sell"
                base_conf = 0.65
                
                # Confidence boosts
                if curr_vol > curr_vol_ma * 1.25:
                    base_conf += 0.12
                    rationale_details.append(f"Volume surge ({curr_vol:.2f} > {curr_vol_ma:.2f})")
                if curr_body >= 1.8 * curr_atr:
                    base_conf += 0.10
                    rationale_details.append("Strong displacement magnitude")
                if (curr_high - max(curr_open, curr_close)) / curr_range > 0.30:
                    base_conf += 0.08
                    rationale_details.append("Upper liquidity grab rejection wick")
                
                confidence = min(round(base_conf, 4), 0.95)
                rationale_details.append(
                    f"Bearish liquidity sweep above HTF swing high {htf_liquidity_high:.2f} "
                    f"with LTF displacement (Body: {curr_body:.2f} vs ATR: {curr_atr:.2f})"
                )

            elif sweep_low_occurred and rejection_above_low and bullish_displacement:
                direction = "buy"
                base_conf = 0.65
                
                # Confidence boosts
                if curr_vol > curr_vol_ma * 1.25:
                    base_conf += 0.12
                    rationale_details.append(f"Volume surge ({curr_vol:.2f} > {curr_vol_ma:.2f})")
                if curr_body >= 1.8 * curr_atr:
                    base_conf += 0.10
                    rationale_details.append("Strong displacement magnitude")
                if (min(curr_open, curr_close) - curr_low) / curr_range > 0.30:
                    base_conf += 0.08
                    rationale_details.append("Lower liquidity grab rejection wick")

                confidence = min(round(base_conf, 4), 0.95)
                rationale_details.append(
                    f"Bullish liquidity sweep below HTF swing low {htf_liquidity_low:.2f} "
                    f"with LTF displacement (Body: {curr_body:.2f} vs ATR: {curr_atr:.2f})"
                )

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale="; ".join(rationale_details),
                    tags=["liquidity_sweep", "displacement", "mtf", direction]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No MTF liquidity sweep and displacement pattern detected",
                tags=["neutral", "no_sweep"]
            )

        except Exception as e:
            logger.error(f"Error evaluating {self.strategy_id} for {symbol}: {str(e)}", exc_info=True)
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {str(e)}",
                tags=["error", "exception"]
            )