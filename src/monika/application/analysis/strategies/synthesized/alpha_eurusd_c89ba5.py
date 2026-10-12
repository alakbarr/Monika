from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_c89ba5(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_c89ba5"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define hyperparameters
        self.lookback_period = 20
        self.volume_ma_period = 10
        self.expansion_threshold = 1.5
        self.confidence_base = 0.5
        self.confidence_max = 0.95

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            
            if not candles or len(candles) < self.lookback_period + self.volume_ma_period:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient historical data",
                    tags=["insufficient_data"]
                )

            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'volume': getattr(c, 'volume', 0.0)
                }
                for c in candles
            ])

            # Ensure numeric types
            for col in ['high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            # Handle NaNs
            df = df.ffill().bfill().fillna(0.0)

            # Calculate Donchian Channels
            df['donchian_high'] = df['high'].rolling(window=self.lookback_period, min_periods=1).max()
            df['donchian_low'] = df['low'].rolling(window=self.lookback_period, min_periods=1).min()
            df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2
            df['donchian_width'] = df['donchian_high'] - df['donchian_low']

            # Calculate Volume Moving Average
            df['volume_ma'] = df['volume'].rolling(window=self.volume_ma_period, min_periods=1).mean()

            # Calculate Volume-Weighted Expansion Factor
            # Normalize volume relative to its moving average
            df['volume_ratio'] = df['volume'] / df['volume_ma'].replace(0, np.nan)
            df['volume_ratio'] = df['volume_ratio'].fillna(1.0)

            # Calculate Donchian Expansion Rate
            df['donchian_width_ma'] = df['donchian_width'].rolling(window=self.volume_ma_period, min_periods=1).mean()
            df['expansion_rate'] = df['donchian_width'] / df['donchian_width_ma'].replace(0, np.nan)
            df['expansion_rate'] = df['expansion_rate'].fillna(1.0)

            # Volume-Weighted Dynamic Expansion Score
            df['vw_expansion_score'] = df['expansion_rate'] * df['volume_ratio']

            # Get latest values
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            current_price = latest['close']
            donchian_high = latest['donchian_high']
            donchian_low = latest['donchian_low']
            donchian_mid = latest['donchian_mid']
            vw_score = latest['vw_expansion_score']
            prev_vw_score = prev['vw_expansion_score']

            # Determine signal based on volume-weighted dynamic Donchian expansion
            # Buy if price breaks above Donchian High with expanding volume-weighted score
            # Sell if price breaks below Donchian Low with expanding volume-weighted score
            
            direction = None
            confidence = self.confidence_base
            rationale = "No signal"
            tags = []

            # Check for breakout conditions
            if current_price > donchian_high and vw_score > self.expansion_threshold:
                direction = 'buy'
                # Confidence scales with expansion strength
                confidence = min(self.confidence_max, self.confidence_base + (vw_score - self.expansion_threshold) * 0.1)
                rationale = f"Buy: Price {current_price:.5f} broke above Donchian High {donchian_high:.5f} with VW expansion score {vw_score:.2f}"
                tags = ["breakout", "buy", "volume_expansion"]
            elif current_price < donchian_low and vw_score > self.expansion_threshold:
                direction = 'sell'
                confidence = min(self.confidence_max, self.confidence_base + (vw_score - self.expansion_threshold) * 0.1)
                rationale = f"Sell: Price {current_price:.5f} broke below Donchian Low {donchian_low:.5f} with VW expansion score {vw_score:.2f}"
                tags = ["breakout", "sell", "volume_expansion"]
            else:
                # Check for momentum continuation within channel
                if vw_score > prev_vw_score and vw_score > 1.0:
                    if current_price > donchian_mid:
                        direction = 'buy'
                        confidence = min(self.confidence_max, self.confidence_base + (vw_score - 1.0) * 0.05)
                        rationale = f"Buy: Momentum continuation above mid-channel with increasing VW score {vw_score:.2f}"
                        tags = ["momentum", "buy"]
                    elif current_price < donchian_mid:
                        direction = 'sell'
                        confidence = min(self.confidence_max, self.confidence_base + (vw_score - 1.0) * 0.05)
                        rationale = f"Sell: Momentum continuation below mid-channel with increasing VW score {vw_score:.2f}"
                        tags = ["momentum", "sell"]

            # Validate confidence
            confidence = max(0.0, min(1.0, confidence))

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=direction is not None,
                confidence=confidence,
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
