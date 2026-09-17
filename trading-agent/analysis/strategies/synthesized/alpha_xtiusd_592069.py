from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xtiusd_592069(EdgeStrategy):
    strategy_id: str = "alpha_xtiusd_592069"
    applicable_symbols: set = {"XTIUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Hyperparameters for Mean Reversion on ATR Exhaustion
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.ma_period: int = self.settings.get("ma_period", 20)
        self.exhaustion_multiplier: float = self.settings.get("exhaustion_multiplier", 2.5)
        self.rsi_period: int = self.settings.get("rsi_period", 14)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch H1 candles to capture intraday exhaustion cycles
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe='H1', 
                limit=100
            )
            
            required_candles = max(self.atr_period, self.ma_period, self.rsi_period) + 10
            if not candles or len(candles) < required_candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candle history. Got {len(candles) if candles else 0}, need {required_candles}",
                    tags=["insufficient_data"]
                )

            # Parse candles safely supporting both object and dict interfaces
            data = []
            for c in candles:
                if hasattr(c, 'close'):
                    data.append({
                        'open': float(c.open),
                        'high': float(c.high),
                        'low': float(c.low),
                        'close': float(c.close),
                        'volume': float(c.volume) if hasattr(c, 'volume') else 0.0
                    })
                else:
                    data.append({
                        'open': float(c.get('open', 0.0)),
                        'high': float(c.get('high', 0.0)),
                        'low': float(c.get('low', 0.0)),
                        'close': float(c.get('close', 0.0)),
                        'volume': float(c.get('volume', 0.0))
                    })

            df = pd.DataFrame(data)

            # Calculate True Range (TR) and Average True Range (ATR)
            high = df['high']
            low = df['low']
            close_prev = df['close'].shift(1)
            
            tr = pd.concat([
                high - low,
                (high - close_prev).abs(),
                (low - close_prev).abs()
            ], axis=1).max(axis=1)
            
            df['atr'] = tr.rolling(window=self.atr_period, min_periods=1).mean()
            df['ma'] = df['close'].rolling(window=self.ma_period, min_periods=1).mean()

            # Calculate RSI for momentum confirmation
            delta = df['close'].diff()
            gain = delta.clip(lower=0.0)
            loss = -delta.clip(upper=0.0)
            avg_gain = gain.rolling(window=self.rsi_period, min_periods=1).mean()
            avg_loss = loss.rolling(window=self.rsi_period, min_periods=1).mean()
            rs = avg_gain / avg_loss.replace(0.0, 1e-9)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs))

            # Sanitize NaNs and Infs
            df = df.ffill().bfill().fillna(0.0)

            if len(df) < 2:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Dataframe processing resulted in empty set",
                    tags=["empty_dataframe"]
                )

            curr = df.iloc[-1]
            
            # Calculate exhaustion metrics
            atr_val = curr['atr'] if curr['atr'] > 0 else 1e-9
            dist_atr = (curr['close'] - curr['ma']) / atr_val

            # Rejection wick analysis
            candle_range = (curr['high'] - curr['low']) if (curr['high'] - curr['low']) > 0 else 1e-9
            upper_wick = (curr['high'] - max(curr['open'], curr['close'])) / candle_range
            lower_wick = (min(curr['open'], curr['close']) - curr['low']) / candle_range

            # Volume confirmation
            vol_ma = df['volume'].rolling(window=20, min_periods=1).mean().iloc[-1]
            high_volume = curr['volume'] > vol_ma if vol_ma > 0 else False

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands. No exhaustion detected."
            tags = ["mean_reversion", "atr_exhaustion"]

            # Mean Reversion Long (Buy) Trigger
            # Price is stretched significantly below the MA, showing signs of stabilization/reversal
            if dist_atr < -self.exhaustion_multiplier:
                if curr['close'] > curr['open'] or lower_wick > 0.4:
                    direction = 'buy'
                    confidence = 0.65
                    tags.append("oversold_exhaustion")
                    
                    if curr['rsi'] < 30:
                        confidence += 0.15
                        tags.append("rsi_oversold")
                    if lower_wick > 0.5:
                        confidence += 0.10
                        tags.append("bullish_rejection")
                    if high_volume:
                        confidence += 0.05
                        tags.append("volume_climax")
                        
                    confidence = min(0.95, confidence)
                    rationale = (
                        f"XTIUSD Mean Reversion Buy: Price is {abs(dist_atr):.2f} ATRs below MA. "
                        f"RSI: {curr['rsi']:.1f}, Lower Wick: {lower_wick:.2%}"
                    )

            # Mean Reversion Short (Sell) Trigger
            # Price is stretched significantly above the MA, showing signs of exhaustion/reversal
            elif dist_atr > self.exhaustion_multiplier:
                if curr['close'] < curr['open'] or upper_wick > 0.4:
                    direction = 'sell'
                    confidence = 0.65
                    tags.append("overbought_exhaustion")
                    
                    if curr['rsi'] > 70:
                        confidence += 0.15
                        tags.append("rsi_overbought")
                    if upper_wick > 0.5:
                        confidence += 0.10
                        tags.append("bearish_rejection")
                    if high_volume:
                        confidence += 0.05
                        tags.append("volume_climax")
                        
                    confidence = min(0.95, confidence)
                    rationale = (
                        f"XTIUSD Mean Reversion Sell: Price is {dist_atr:.2f} ATRs above MA. "
                        f"RSI: {curr['rsi']:.1f}, Upper Wick: {upper_wick:.2%}"
                    )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence if direction else 0.0,
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