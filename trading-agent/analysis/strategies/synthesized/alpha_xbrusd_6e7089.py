from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_6e7089(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_6e7089"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.atr_period = self.settings.get("atr_period", 14)
        self.ema_period = self.settings.get("ema_period", 20)
        self.rsi_period = self.settings.get("rsi_period", 14)
        self.exhaustion_threshold = self.settings.get("exhaustion_threshold", 2.4)
        self.rsi_overbought = self.settings.get("rsi_overbought", 68.0)
        self.rsi_oversold = self.settings.get("rsi_oversold", 32.0)
        self.volume_climax_threshold = self.settings.get("volume_climax_threshold", 1.2)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not supported by this strategy.",
                tags=["unsupported_symbol"]
            )

        try:
            # Fetch H1 candles for robust medium-term mean reversion
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
        except Exception as e:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Failed to fetch historical candles: {str(e)}",
                tags=["error_fetching_data"]
            )

        min_required_candles = max(self.ema_period, self.atr_period, self.rsi_period) + 10
        if not candles or len(candles) < min_required_candles:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history. Required: {min_required_candles}, Got: {len(candles) if candles else 0}",
                tags=["insufficient_data"]
            )

        # Convert candles to DataFrame safely
        data = []
        for c in candles:
            data.append({
                'open': float(c.open),
                'high': float(c.high),
                'low': float(c.low),
                'close': float(c.close),
                'volume': float(getattr(c, 'volume', 0.0))
            })
        df = pd.DataFrame(data)

        # Calculate Average True Range (ATR)
        df['high_low'] = df['high'] - df['low']
        df['high_prev_close'] = (df['high'] - df['close'].shift(1)).abs()
        df['low_prev_close'] = (df['low'] - df['close'].shift(1)).abs()
        df['tr'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()

        # Calculate Exponential Moving Average (EMA)
        df['ema'] = df['close'].ewm(span=self.ema_period, adjust=False).mean()

        # Calculate Relative Strength Index (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

        # Calculate Volume Z-Score to detect capitulation/exhaustion volume climax
        df['vol_ma'] = df['volume'].rolling(window=20).mean()
        df['vol_std'] = df['volume'].rolling(window=20).std()
        df['vol_z'] = (df['volume'] - df['vol_ma']) / (df['vol_std'] + 1e-9)

        # Extract latest values
        latest = df.iloc[-1]
        close = latest['close']
        ema = latest['ema']
        atr = latest['atr']
        rsi = latest['rsi']
        vol_z = latest['vol_z']

        if math.isnan(atr) or math.isnan(ema) or math.isnan(rsi) or atr <= 0:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Calculated indicators contain NaN values.",
                tags=["nan_indicators"]
            )

        # Deviation from EMA in terms of ATR units
        deviation = (close - ema) / atr

        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["mean_reversion", "atr_exhaustion"]

        # Check for Overextended Upside (Short/Sell Reversion)
        if deviation >= self.exhaustion_threshold and rsi >= self.rsi_overbought:
            direction = 'sell'
            confidence_base = 0.5 + min(0.4, (deviation - self.exhaustion_threshold) * 0.15)
            if vol_z > self.volume_climax_threshold:
                confidence_base += 0.08
                tags.append("volume_climax")
            confidence = min(0.95, confidence_base)
            rationale = f"XBRUSD overextended upside. Dev: {deviation:.2f} ATRs, RSI: {rsi:.1f}, Vol Z-Score: {vol_z:.2f}."

        # Check for Overextended Downside (Long/Buy Reversion)
        elif deviation <= -self.exhaustion_threshold and rsi <= self.rsi_oversold:
            direction = 'buy'
            confidence_base = 0.5 + min(0.4, (abs(deviation) - self.exhaustion_threshold) * 0.15)
            if vol_z > self.volume_climax_threshold:
                confidence_base += 0.08
                tags.append("volume_climax")
            confidence = min(0.95, confidence_base)
            rationale = f"XBRUSD overextended downside. Dev: {deviation:.2f} ATRs, RSI: {rsi:.1f}, Vol Z-Score: {vol_z:.2f}."

        else:
            rationale = f"No exhaustion detected. Dev: {deviation:.2f} ATRs, RSI: {rsi:.1f}."

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=direction is not None,
            confidence=round(confidence, 2),
            rationale=rationale,
            tags=tags
        )