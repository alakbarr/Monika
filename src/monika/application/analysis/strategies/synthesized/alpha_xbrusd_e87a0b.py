from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_e87a0b(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_e87a0b"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = self.settings.get("atr_period", 14)
        self.ma_period = self.settings.get("ma_period", 20)
        self.atr_multiplier = self.settings.get("atr_multiplier", 2.5)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.logger = logging.getLogger(f"edge_engine.{self.strategy_id}")

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} is not applicable for this strategy.",
                tags=["invalid_symbol"]
            )

        # Fetch historical candles
        limit = max(self.atr_period, self.ma_period, self.rsi_period) + 15
        candles = await self.get_historical_candles(
            session=session, 
            symbol=symbol, 
            timeframe=self.timeframe, 
            limit=limit
        )

        if not candles or len(candles) < limit:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history. Required: {limit}, Got: {len(candles) if candles else 0}",
                tags=["insufficient_data"]
            )

        # Parse candles into a structured format
        data = []
        for c in candles:
            try:
                close_val = float(c.close)
                high_val = float(c.high)
                low_val = float(c.low)
                open_val = float(c.open)
            except (AttributeError, TypeError):
                close_val = float(c['close'])
                high_val = float(c['high'])
                low_val = float(c['low'])
                open_val = float(c['open'])
            
            data.append({
                'open': open_val,
                'high': high_val,
                'low': low_val,
                'close': close_val
            })

        df = pd.DataFrame(data)

        # Calculate ATR (Average True Range)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = (df['high'] - df['prev_close']).abs()
        df['tr3'] = (df['low'] - df['prev_close']).abs()
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()

        # Calculate Baseline (SMA)
        df['ma'] = df['close'].rolling(window=self.ma_period).mean()

        # Calculate Exhaustion Bands
        df['upper_band'] = df['ma'] + (self.atr_multiplier * df['atr'])
        df['lower_band'] = df['ma'] - (self.atr_multiplier * df['atr'])

        # Calculate RSI for confirmation
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # Extract current state
        last_row = df.iloc[-1]
        curr_close = last_row['close']
        curr_high = last_row['high']
        curr_low = last_row['low']
        curr_ma = last_row['ma']
        curr_atr = last_row['atr']
        curr_upper = last_row['upper_band']
        curr_lower = last_row['lower_band']
        curr_rsi = last_row['rsi']

        # Check for NaN values in critical indicators
        if pd.isna(curr_upper) or pd.isna(curr_lower) or pd.isna(curr_rsi) or curr_atr <= 0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Indicators contain NaN or invalid values.",
                tags=["nan_indicators"]
            )

        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["mean_reversion", "atr_exhaustion"]

        # Buy Setup: Price pierced lower band (exhaustion) and shows signs of reversal/oversold
        is_buy_exhaustion = curr_low < curr_lower
        is_buy_rsi = curr_rsi < 32
        is_buy_reversal = curr_close > (curr_low + 0.2 * (curr_high - curr_low))

        # Sell Setup: Price pierced upper band (exhaustion) and shows signs of reversal/overbought
        is_sell_exhaustion = curr_high > curr_upper
        is_sell_rsi = curr_rsi > 68
        is_sell_reversal = curr_close < (curr_high - 0.2 * (curr_high - curr_low))

        if is_buy_exhaustion and (is_buy_rsi or is_buy_reversal):
            direction = "buy"
            # Calculate confidence based on how deep the exhaustion is
            deviation = (curr_lower - curr_low) / curr_atr if curr_atr > 0 else 0
            confidence = min(0.95, 0.50 + (deviation * 0.15))
            rationale = (
                f"XBRUSD ATR exhaustion low detected. Low ({curr_low:.3f}) pierced lower band ({curr_lower:.3f}). "
                f"RSI is {curr_rsi:.1f}. Reversal confirmation: {is_buy_reversal}."
            )
            tags.append("oversold")

        elif is_sell_exhaustion and (is_sell_rsi or is_sell_reversal):
            direction = "sell"
            # Calculate confidence based on how deep the exhaustion is
            deviation = (curr_high - curr_upper) / curr_atr if curr_atr > 0 else 0
            confidence = min(0.95, 0.50 + (deviation * 0.15))
            rationale = (
                f"XBRUSD ATR exhaustion high detected. High ({curr_high:.3f}) pierced upper band ({curr_upper:.3f}). "
                f"RSI is {curr_rsi:.1f}. Reversal confirmation: {is_sell_reversal}."
            )
            tags.append("overbought")

        else:
            rationale = f"No ATR exhaustion detected. Price: {curr_close:.3f}, Upper: {curr_upper:.3f}, Lower: {curr_lower:.3f}."

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=direction is not None,
            confidence=round(confidence, 3),
            rationale=rationale,
            tags=tags
        )