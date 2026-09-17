from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xauusd_75d1dc(EdgeStrategy):
    strategy_id: str = "alpha_xauusd_75d1dc"
    applicable_symbols: set = {"XAUUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        # Define default hyperparameters
        self.atr_period = self.settings.get('atr_period', 14)
        self.ma_period = self.settings.get('ma_period', 20)
        self.exhaustion_multiplier = self.settings.get('exhaustion_multiplier', 2.5)
        self.rsi_period = self.settings.get('rsi_period', 14)
        self.rsi_overbought = self.settings.get('rsi_overbought', 70.0)
        self.rsi_oversold = self.settings.get('rsi_oversold', 30.0)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Resolve runtime settings overrides
            atr_p = int(settings.get('atr_period', self.atr_period))
            ma_p = int(settings.get('ma_period', self.ma_period))
            exhaustion_mult = float(settings.get('exhaustion_multiplier', self.exhaustion_multiplier))
            rsi_p = int(settings.get('rsi_period', self.rsi_period))
            rsi_ob = float(settings.get('rsi_overbought', self.rsi_overbought))
            rsi_os = float(settings.get('rsi_oversold', self.rsi_oversold))

            # Fetch historical candles (H1 timeframe is optimal for XAUUSD exhaustion)
            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            if not candles:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No candle history returned",
                    tags=["no_candles"]
                )

            # Parse candles safely into a DataFrame
            data = []
            for c in candles:
                try:
                    if isinstance(c, dict):
                        data.append({
                            'open': float(c.get('open', 0)),
                            'high': float(c.get('high', 0)),
                            'low': float(c.get('low', 0)),
                            'close': float(c.get('close', 0)),
                            'volume': float(c.get('volume', 0))
                        })
                    else:
                        data.append({
                            'open': float(getattr(c, 'open', 0)),
                            'high': float(getattr(c, 'high', 0)),
                            'low': float(getattr(c, 'low', 0)),
                            'close': float(getattr(c, 'close', 0)),
                            'volume': float(getattr(c, 'volume', 0))
                        })
                except Exception:
                    continue

            df = pd.DataFrame(data)
            required_len = max(atr_p, ma_p, rsi_p) + 5
            if len(df) < required_len:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Insufficient candles. Required: {required_len}, Got: {len(df)}",
                    tags=["insufficient_data"]
                )

            # Calculate Average True Range (ATR)
            df['prev_close'] = df['close'].shift(1)
            df['tr1'] = df['high'] - df['low']
            df['tr2'] = (df['high'] - df['prev_close']).abs()
            df['tr3'] = (df['low'] - df['prev_close']).abs()
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(window=atr_p, min_periods=1).mean()

            # Calculate Simple Moving Average (SMA)
            df['sma'] = df['close'].rolling(window=ma_p, min_periods=1).mean()

            # Calculate Relative Strength Index (RSI)
            delta = df['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=rsi_p, min_periods=1).mean()
            avg_loss = loss.rolling(window=rsi_p, min_periods=1).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            df['rsi'] = 100 - (100 / (1 + rs))

            # Sanitize NaNs and Infs
            df = df.ffill().bfill().fillna(0.0)

            # Extract latest metrics
            latest = df.iloc[-1]
            close = float(latest['close'])
            sma = float(latest['sma'])
            atr = float(latest['atr'])
            rsi = float(latest['rsi'])

            upper_exhaustion = sma + (exhaustion_mult * atr)
            lower_exhaustion = sma - (exhaustion_mult * atr)

            direction = None
            confidence = 0.0
            rationale = "Price within normal ATR bands"
            tags = ["mean_reversion", "atr_exhaustion"]

            if atr > 0:
                if close > upper_exhaustion and rsi > rsi_ob:
                    direction = 'sell'
                    excess = close - upper_exhaustion
                    confidence = min(0.95, 0.6 + (excess / atr) * 0.15)
                    rationale = f"XAUUSD exhausted upside. Close ({close:.2f}) > Upper Exhaustion ({upper_exhaustion:.2f}), RSI ({rsi:.1f}) > {rsi_ob}"
                    tags.append("exhaustion_sell")
                elif close < lower_exhaustion and rsi < rsi_os:
                    direction = 'buy'
                    excess = lower_exhaustion - close
                    confidence = min(0.95, 0.6 + (excess / atr) * 0.15)
                    rationale = f"XAUUSD exhausted downside. Close ({close:.2f}) < Lower Exhaustion ({lower_exhaustion:.2f}), RSI ({rsi:.1f}) < {rsi_os}"
                    tags.append("exhaustion_buy")

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