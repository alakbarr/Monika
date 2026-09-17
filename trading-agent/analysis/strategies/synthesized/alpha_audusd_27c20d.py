from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_27c20d(EdgeStrategy):
    strategy_id: str = "alpha_audusd_27c20d"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        safe_settings = settings or {}
        self.htf_lookback = int(safe_settings.get("htf_lookback", 24))
        self.ltf_lookback = int(safe_settings.get("ltf_lookback", 5))
        self.displacement_mult = float(safe_settings.get("displacement_mult", 1.2))
        self.rsi_period = int(safe_settings.get("rsi_period", 14))
        self.rsi_ob = float(safe_settings.get("rsi_ob", 65))
        self.rsi_os = float(safe_settings.get("rsi_os", 35))

    def _candles_to_df(self, candles) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()
        data = []
        for c in candles:
            try:
                open_val = float(c.open)
                high_val = float(c.high)
                low_val = float(c.low)
                close_val = float(c.close)
                volume_val = float(getattr(c, 'volume', 0.0))
            except AttributeError:
                open_val = float(c.get('open', 0.0))
                high_val = float(c.get('high', 0.0))
                low_val = float(c.get('low', 0.0))
                close_val = float(c.get('close', 0.0))
                volume_val = float(c.get('volume', 0.0))
            data.append({
                'open': open_val,
                'high': high_val,
                'low': low_val,
                'close': close_val,
                'volume': volume_val
            })
        df = pd.DataFrame(data)
        df = df.ffill().bfill().fillna(0.0)
        return df

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported.",
                    tags=["unsupported_symbol"]
                )

            # Resolve settings
            htf_lookback = int(settings.get("htf_lookback", self.htf_lookback))
            ltf_lookback = int(settings.get("ltf_lookback", self.ltf_lookback))
            displacement_mult = float(settings.get("displacement_mult", self.displacement_mult))
            rsi_period = int(settings.get("rsi_period", self.rsi_period))
            rsi_ob = float(settings.get("rsi_ob", self.rsi_ob))
            rsi_os = float(settings.get("rsi_os", self.rsi_os))

            # Fetch candles
            candles_h1 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)
            candles_m15 = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=100)

            df_h1 = self._candles_to_df(candles_h1)
            df_m15 = self._candles_to_df(candles_m15)

            if len(df_h1) < max(htf_lookback + 5, 30) or len(df_m15) < max(rsi_period + 10, 30):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history.",
                    tags=["insufficient_data"]
                )

            # Calculate HTF levels (excluding current active H1 candle to avoid repainting)
            htf_highs = df_h1['high'].iloc[-htf_lookback-1:-1]
            htf_lows = df_h1['low'].iloc[-htf_lookback-1:-1]
            htf_resistance = float(htf_highs.max())
            htf_support = float(htf_lows.min())

            # Calculate LTF average body size
            df_m15['body'] = (df_m15['close'] - df_m15['open']).abs()
            avg_body = float(df_m15['body'].rolling(20, min_periods=1).mean().iloc[-1])

            # Calculate LTF RSI
            delta = df_m15['close'].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(rsi_period, min_periods=1).mean()
            avg_loss = loss.rolling(rsi_period, min_periods=1).mean()
            rs = avg_gain / (avg_loss + 1e-9)
            df_m15['rsi'] = 100 - (100 / (1 + rs))
            df_m15['rsi'] = df_m15['rsi'].ffill().bfill().fillna(50.0)

            # Analyze recent LTF candles
            recent_m15 = df_m15.iloc[-ltf_lookback:]
            current_m15 = df_m15.iloc[-1]

            # Bullish Sweep Check
            swept_support = bool(recent_m15['low'].min() < htf_support)
            closed_above_support = bool(current_m15['close'] > htf_support)
            
            # Check for bullish displacement in the last 2 candles
            bullish_displacement = False
            for i in range(1, min(3, len(recent_m15) + 1)):
                c_idx = -i
                candle = df_m15.iloc[c_idx]
                body_size = candle['close'] - candle['open']
                if body_size > 0 and body_size > (displacement_mult * avg_body):
                    bullish_displacement = True
                    break

            min_rsi_recent = float(recent_m15['rsi'].min())
            oversold_condition = bool(min_rsi_recent < rsi_os)

            # Bearish Sweep Check
            swept_resistance = bool(recent_m15['high'].max() > htf_resistance)
            closed_below_resistance = bool(current_m15['close'] < htf_resistance)

            # Check for bearish displacement in the last 2 candles
            bearish_displacement = False
            for i in range(1, min(3, len(recent_m15) + 1)):
                c_idx = -i
                candle = df_m15.iloc[c_idx]
                body_size = candle['open'] - candle['close']
                if body_size > 0 and body_size > (displacement_mult * avg_body):
                    bearish_displacement = True
                    break

            max_rsi_recent = float(recent_m15['rsi'].max())
            overbought_condition = bool(max_rsi_recent > rsi_ob)

            # Signal Logic
            if swept_support and closed_above_support and bullish_displacement and oversold_condition:
                sweep_depth = float((htf_support - recent_m15['low'].min()) / (htf_support + 1e-9))
                confidence = float(min(0.6 + (sweep_depth * 500) + ((current_m15['close'] - current_m15['open']) / (avg_body + 1e-9)) * 0.05, 0.95))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='buy',
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=f"AUDUSD H1 support ({htf_support:.5f}) swept. M15 bullish displacement detected with RSI recovery from {min_rsi_recent:.1f}.",
                    tags=["liquidity_sweep", "bullish_displacement", "m15_reversal"]
                )

            elif swept_resistance and closed_below_resistance and bearish_displacement and overbought_condition:
                sweep_depth = float((recent_m15['high'].max() - htf_resistance) / (htf_resistance + 1e-9))
                confidence = float(min(0.6 + (sweep_depth * 500) + ((current_m15['open'] - current_m15['close']) / (avg_body + 1e-9)) * 0.05, 0.95))
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='sell',
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=f"AUDUSD H1 resistance ({htf_resistance:.5f}) swept. M15 bearish displacement detected with RSI recovery from {max_rsi_recent:.1f}.",
                    tags=["liquidity_sweep", "bearish_displacement", "m15_reversal"]
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="No liquidity sweep with displacement detected.",
                tags=["no_signal"]
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
