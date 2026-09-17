from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

logger = logging.getLogger(__name__)

class SynthesizedStrategy_alpha_btcusd_bd9200(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_bd9200"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.ema_period: int = int(self.settings.get("ema_period", 20))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.atr_exhaustion_mult: float = float(self.settings.get("atr_exhaustion_mult", 2.75))
        self.rsi_period: int = int(self.settings.get("rsi_period", 14))
        self.rsi_overbought: float = float(self.settings.get("rsi_overbought", 70.0))
        self.rsi_oversold: float = float(self.settings.get("rsi_oversold", 30.0))
        self.timeframe: str = str(self.settings.get("timeframe", "H1"))
        self.candle_limit: int = int(self.settings.get("candle_limit", 100))

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
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe=self.timeframe,
                limit=self.candle_limit
            )
        except Exception as e:
            logger.warning(f"Error fetching historical candles for {symbol}: {e}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Failed to retrieve candle data: {str(e)}",
                tags=["data_fetch_error"]
            )

        min_required = max(self.ema_period, self.atr_period, self.rsi_period) + 15
        if not candles or len(candles) < min_required:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candles ({len(candles) if candles else 0} < {min_required})",
                tags=["insufficient_data"]
            )

        # Extract price series safely
        try:
            highs_list: List[float] = []
            lows_list: List[float] = []
            closes_list: List[float] = []
            opens_list: List[float] = []

            for c in candles:
                if isinstance(c, dict):
                    highs_list.append(float(c.get("high", 0.0)))
                    lows_list.append(float(c.get("low", 0.0)))
                    closes_list.append(float(c.get("close", 0.0)))
                    opens_list.append(float(c.get("open", 0.0)))
                else:
                    highs_list.append(float(c.high))
                    lows_list.append(float(c.low))
                    closes_list.append(float(c.close))
                    opens_list.append(float(c.open))

            highs = pd.Series(highs_list, dtype=np.float64)
            lows = pd.Series(lows_list, dtype=np.float64)
            closes = pd.Series(closes_list, dtype=np.float64)
            opens = pd.Series(opens_list, dtype=np.float64)
        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Error parsing candle data: {str(e)}",
                tags=["parse_error"]
            )

        # Calculate EMA Baseline
        ema = closes.ewm(span=self.ema_period, adjust=False).mean()

        # Calculate True Range and ATR
        prev_close = closes.shift(1)
        tr1 = highs - lows
        tr2 = (highs - prev_close).abs()
        tr3 = (lows - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()

        # Calculate RSI for exhaustion confirmation
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        current_close = float(closes.iloc[-1])
        current_open = float(opens.iloc[-1])
        current_ema = float(ema.iloc[-1])
        current_atr = float(atr.iloc[-1])
        current_rsi = float(rsi.iloc[-1]) if not math.isnan(rsi.iloc[-1]) else 50.0

        if current_atr <= 0 or math.isnan(current_ema) or math.isnan(current_atr):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Invalid indicator computations (zero ATR or NaN values)",
                tags=["indicator_error"]
            )

        # Normalized ATR Deviation Distance
        atr_deviation = (current_close - current_ema) / current_atr

        direction: Optional[str] = None
        confidence: float = 0.0
        rationale: str = ""
        tags: List[str] = ["mean_reversion", "atr_exhaustion", "btcusd"]

        # Mean Reversion Long Condition: Price extended far below EMA + Oversold Exhaustion
        if atr_deviation <= -self.atr_exhaustion_mult and current_rsi <= self.rsi_oversold:
            direction = "buy"
            # Scale confidence with the magnitude of stretch and oversold depth
            stretch_factor = min(abs(atr_deviation) / self.atr_exhaustion_mult, 1.5)
            rsi_factor = min((self.rsi_oversold - current_rsi + 10.0) / 30.0, 1.0)
            candle_rejection_bonus = 0.05 if current_close >= current_open else 0.0

            raw_confidence = 0.60 + (0.20 * (stretch_factor - 1.0)) + (0.10 * max(0.0, rsi_factor)) + candle_rejection_bonus
            confidence = round(float(np.clip(raw_confidence, 0.55, 0.92)), 4)

            rationale = (
                f"BTCUSD oversold exhaustion: Price {current_close:.2f} is {abs(atr_deviation):.2f} ATRs below "
                f"EMA{self.ema_period} ({current_ema:.2f}) with RSI at {current_rsi:.1f}. Mean reversion long triggered."
            )
            tags.extend(["oversold_stretch", "exhaustion_buy"])

        # Mean Reversion Short Condition: Price extended far above EMA + Overbought Exhaustion
        elif atr_deviation >= self.atr_exhaustion_mult and current_rsi >= self.rsi_overbought:
            direction = "sell"
            # Scale confidence with the magnitude of stretch and overbought height
            stretch_factor = min(atr_deviation / self.atr_exhaustion_mult, 1.5)
            rsi_factor = min((current_rsi - self.rsi_overbought + 10.0) / 30.0, 1.0)
            candle_rejection_bonus = 0.05 if current_close <= current_open else 0.0

            raw_confidence = 0.60 + (0.20 * (stretch_factor - 1.0)) + (0.10 * max(0.0, rsi_factor)) + candle_rejection_bonus
            confidence = round(float(np.clip(raw_confidence, 0.55, 0.92)), 4)

            rationale = (
                f"BTCUSD overbought exhaustion: Price {current_close:.2f} is {atr_deviation:.2f} ATRs above "
                f"EMA{self.ema_period} ({current_ema:.2f}) with RSI at {current_rsi:.1f}. Mean reversion short triggered."
            )
            tags.extend(["overbought_stretch", "exhaustion_sell"])

        else:
            direction = None
            confidence = 0.0
            rationale = (
                f"BTCUSD within normal ATR boundaries. Deviation: {atr_deviation:.2f} ATRs "
                f"(Threshold: +/-{self.atr_exhaustion_mult:.2f}), RSI: {current_rsi:.1f}."
            )
            tags.append("neutral")

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=direction is not None,
            confidence=confidence,
            rationale=rationale,
            tags=tags
        )