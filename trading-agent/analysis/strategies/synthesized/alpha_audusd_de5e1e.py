from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_de5e1e(EdgeStrategy):
    strategy_id: str = "alpha_audusd_de5e1e"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.lookback = self.settings.get("lookback", 24)
        self.vol_lookback = self.settings.get("vol_lookback", 24)
        self.expansion_factor = self.settings.get("expansion_factor", 0.2)
        self.trend_span = self.settings.get("trend_span", 50)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
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

            # Fetch candle history
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles or len(candles) < max(self.lookback, self.trend_span) + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for calculations.",
                    tags=["insufficient_data"]
                )

            # Convert candles to DataFrame safely
            df_data = []
            for c in candles:
                df_data.append({
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                    'volume': float(c.volume if hasattr(c, 'volume') else c['volume']),
                })
            df = pd.DataFrame(df_data)

            # Calculate Donchian Channel
            df['high_max'] = df['high'].rolling(window=self.lookback, min_periods=1).max()
            df['low_min'] = df['low'].rolling(window=self.lookback, min_periods=1).min()
            df['center'] = (df['high_max'] + df['low_min']) / 2.0
            df['half_width'] = (df['high_max'] - df['low_min']) / 2.0

            # Volume Z-Score
            df['vol_ma'] = df['volume'].rolling(window=self.vol_lookback, min_periods=1).mean()
            df['vol_std'] = df['volume'].rolling(window=self.vol_lookback, min_periods=1).std().fillna(0.0)
            df['vol_z'] = ((df['volume'] - df['vol_ma']) / (df['vol_std'] + 1e-8)).clip(-2.0, 2.0).fillna(0.0)

            # Dynamic Expansion
            df['dynamic_half_width'] = df['half_width'] * (1.0 + self.expansion_factor * df['vol_z'])
            df['upper_band'] = df['center'] + df['dynamic_half_width']
            df['lower_band'] = df['center'] - df['dynamic_half_width']

            # Trend Filter
            df['ema_trend'] = df['close'].ewm(span=self.trend_span, adjust=False).mean()

            # ATR for confidence scaling
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    (df['high'] - df['close'].shift(1)).abs(),
                    (df['low'] - df['close'].shift(1)).abs()
                )
            ).fillna(0.0)
            df['atr'] = df['tr'].rolling(window=14, min_periods=1).mean()

            # Get latest values
            row_curr = df.iloc[-1]
            row_prev = df.iloc[-2]

            close_curr = row_curr['close']
            close_prev = row_prev['close']
            upper_curr = row_curr['upper_band']
            lower_curr = row_curr['lower_band']
            vol_curr = row_curr['volume']
            vol_ma = row_curr['vol_ma']
            ema_trend = row_curr['ema_trend']
            atr = row_curr['atr'] if row_curr['atr'] > 0 else 1e-5

            direction = None
            confidence = 0.0
            rationale = "No breakout detected"
            tags = ["neutral"]

            # Check for Buy Breakout
            if close_curr > upper_curr and close_prev <= row_prev['upper_band'] and vol_curr > vol_ma and close_curr > ema_trend:
                direction = 'buy'
                vol_factor = (row_curr['vol_z'] + 2.0) / 4.0  # Normalize -2 to 2 into 0 to 1
                breakout_factor = min(1.0, (close_curr - upper_curr) / atr)
                confidence = float(np.clip(0.5 + 0.3 * vol_factor + 0.2 * breakout_factor, 0.5, 0.95))
                rationale = f"Bullish dynamic Donchian expansion breakout. Close ({close_curr:.5f}) > Upper Band ({upper_curr:.5f}) with elevated volume."
                tags = ["breakout", "bullish", "volume_expansion"]

            # Check for Sell Breakout
            elif close_curr < lower_curr and close_prev >= row_prev['lower_band'] and vol_curr > vol_ma and close_curr < ema_trend:
                direction = 'sell'
                vol_factor = (row_curr['vol_z'] + 2.0) / 4.0
                breakout_factor = min(1.0, (lower_curr - close_curr) / atr)
                confidence = float(np.clip(0.5 + 0.3 * vol_factor + 0.2 * breakout_factor, 0.5, 0.95))
                rationale = f"Bearish dynamic Donchian expansion breakout. Close ({close_curr:.5f}) < Lower Band ({lower_curr:.5f}) with elevated volume."
                tags = ["breakout", "bearish", "volume_expansion"]

            valid = direction is not None

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=valid,
                confidence=confidence if valid else 0.0,
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
                rationale=f"Calculation error: {e}",
                tags=["error"]
            )
