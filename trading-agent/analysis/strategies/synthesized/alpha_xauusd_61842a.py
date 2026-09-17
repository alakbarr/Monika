from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_61842a(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_61842a"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Institutional hyperparameters for XAUUSD (Gold)
        self.lookback = int(self.settings.get("lookback", 24))  # 24-hour lookback for H1
        self.volume_ma_period = int(self.settings.get("volume_ma_period", 20))
        self.expansion_factor = float(self.settings.get("expansion_factor", 0.18))
        self.trend_filter_period = int(self.settings.get("trend_filter_period", 50))
        self.atr_period = int(self.settings.get("atr_period", 14))
        self.timeframe = str(self.settings.get("timeframe", "H1"))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles
            limit = max(self.lookback, self.trend_filter_period, self.atr_period) + 50
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=self.timeframe, 
                limit=limit
            )

            if not candles or len(candles) < max(self.lookback, self.trend_filter_period):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history.",
                    tags=["insufficient_data"]
                )

            # Parse candles into a structured DataFrame
            data = []
            for c in candles:
                try:
                    high = c.high
                    low = c.low
                    close = c.close
                    volume = c.volume
                    open_val = c.open
                except AttributeError:
                    high = c.get('high')
                    low = c.get('low')
                    close = c.get('close')
                    volume = c.get('volume')
                    open_val = c.get('open')

                data.append({
                    'high': float(high) if high is not None else 0.0,
                    'low': float(low) if low is not None else 0.0,
                    'close': float(close) if close is not None else 0.0,
                    'volume': float(volume) if volume is not None else 0.0,
                    'open': float(open_val) if open_val is not None else 0.0,
                })

            df = pd.DataFrame(data)

            # Calculate standard Donchian Channels (shifted by 1 to avoid lookahead bias)
            df['upper_donchian'] = df['high'].shift(1).rolling(window=self.lookback, min_periods=self.lookback).max()
            df['lower_donchian'] = df['low'].shift(1).rolling(window=self.lookback, min_periods=self.lookback).min()
            df['center_donchian'] = (df['upper_donchian'] + df['lower_donchian']) / 2.0
            df['half_width'] = (df['upper_donchian'] - df['lower_donchian']) / 2.0

            # Calculate Volume Moving Average and Volume Ratio
            df['vol_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=self.volume_ma_period).mean()
            # Sanitize volume MA to avoid division by zero
            df['vol_ma'] = df['vol_ma'].replace(0.0, np.nan).ffill().bfill().fillna(1.0)
            df['vol_ratio'] = (df['volume'] / df['vol_ma']).fillna(1.0).clip(lower=0.1, upper=3.0)

            # Dynamic Donchian Expansion based on Volume Ratio
            # High volume expands the channel boundaries to filter out false breakouts; low volume contracts it.
            df['dynamic_half_width'] = df['half_width'] * (1.0 + self.expansion_factor * (df['vol_ratio'] - 1.0))
            df['dynamic_upper'] = df['center_donchian'] + df['dynamic_half_width']
            df['dynamic_lower'] = df['center_donchian'] - df['dynamic_half_width']

            # Trend Filter (EMA)
            df['ema_trend'] = df['close'].ewm(span=self.trend_filter_period, adjust=False).mean()

            # ATR for volatility-based risk control
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    (df['high'] - df['close'].shift(1)).abs(),
                    (df['low'] - df['close'].shift(1)).abs()
                )
            )
            df['atr'] = df['tr'].rolling(window=self.atr_period, min_periods=self.atr_period).mean().ffill().bfill().fillna(1.0)

            # Extract latest values
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            dynamic_upper = latest['dynamic_upper']
            dynamic_lower = latest['dynamic_lower']
            ema_trend = latest['ema_trend']
            vol_ratio = latest['vol_ratio']
            atr = latest['atr']
            center = latest['center_donchian']

            if np.isnan(dynamic_upper) or np.isnan(dynamic_lower) or np.isnan(ema_trend):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="NaN values in calculated indicators.",
                    tags=["nan_indicators"]
                )

            # Signal Logic
            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["volume_weighted_donchian"]

            # Check for overextension (exhaustion filter)
            breakout_dist = abs(close - center)
            is_overextended = breakout_dist > (3.5 * atr)

            # Bullish Breakout: Close crosses above dynamic upper band, confirmed by trend and volume
            if close > dynamic_upper and close > ema_trend and vol_ratio > 1.05:
                if not is_overextended:
                    direction = "buy"
                    confidence = min(0.90, 0.50 + 0.15 * (vol_ratio - 1.0))
                    rationale = (
                        f"Bullish breakout confirmed. Close ({close:.2f}) > Dynamic Upper ({dynamic_upper:.2f}). "
                        f"Volume ratio ({vol_ratio:.2f}x) indicates institutional participation. Trend is bullish."
                    )
                    tags.append("bullish_breakout")
                else:
                    rationale = "Bullish breakout detected but filtered due to ATR overextension."
                    tags.append("overextended_bullish")

            # Bearish Breakout: Close crosses below dynamic lower band, confirmed by trend and volume
            elif close < dynamic_lower and close < ema_trend and vol_ratio > 1.05:
                if not is_overextended:
                    direction = "sell"
                    confidence = min(0.90, 0.50 + 0.15 * (vol_ratio - 1.0))
                    rationale = (
                        f"Bearish breakout confirmed. Close ({close:.2f}) < Dynamic Lower ({dynamic_lower:.2f}). "
                        f"Volume ratio ({vol_ratio:.2f}x) indicates institutional participation. Trend is bearish."
                    )
                    tags.append("bearish_breakout")
                else:
                    rationale = "Bearish breakout detected but filtered due to ATR overextension."
                    tags.append("overextended_bearish")
            else:
                rationale = (
                    f"No breakout detected. Close ({close:.2f}) is within dynamic bands "
                    f"({dynamic_lower:.2f} - {dynamic_upper:.2f}). Vol Ratio: {vol_ratio:.2f}."
                )
                tags.append("mean_reverting_range")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True if direction else False,
                confidence=float(confidence),
                rationale=rationale,
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
                tags=["error"]
            )
