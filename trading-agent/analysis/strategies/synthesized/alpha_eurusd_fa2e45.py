from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_fa2e45(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_fa2e45"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_lookback: int = self.settings.get("htf_lookback", 48)
        self.ltf_sweep_window: int = self.settings.get("ltf_sweep_window", 6)
        self.displacement_multiplier: float = float(self.settings.get("displacement_multiplier", 1.2))
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.min_confidence: float = float(self.settings.get("min_confidence", 0.65))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} is not applicable for this strategy.",
                    tags=["unsupported_symbol"]
                )

            # Fetch Multi-Timeframe Candles: H1 for Liquidity Pools, M15 for Sweep & Displacement
            htf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=self.htf_lookback + 20)
            ltf_candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='M15', limit=60)

            if not htf_candles or len(htf_candles) < 30 or not ltf_candles or len(ltf_candles) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient MTF candle history for liquidity sweep analysis.",
                    tags=["insufficient_data"]
                )

            # Parse HTF candles
            htf_highs = [float(c.high if hasattr(c, 'high') else c['high']) for c in htf_candles]
            htf_lows = [float(c.low if hasattr(c, 'low') else c['low']) for c in htf_candles]
            
            # Identify prominent HTF Liquidity Pools (BSL - Buy-Side Liquidity, SSL - Sell-Side Liquidity)
            # Exclude the active/latest 2 HTF candles to avoid repainting swing points
            eval_htf_highs = htf_highs[-self.htf_lookback:-2]
            eval_htf_lows = htf_lows[-self.htf_lookback:-2]
            
            if not eval_htf_highs or not eval_htf_lows:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to compute HTF liquidity boundaries.",
                    tags=["insufficient_htf_depth"]
                )

            htf_bsl = max(eval_htf_highs)
            htf_ssl = min(eval_htf_lows)

            # Parse LTF candles into DataFrame for indicator calculations
            ltf_records = []
            for c in ltf_candles:
                ltf_records.append({
                    'open': float(c.open if hasattr(c, 'open') else c['open']),
                    'high': float(c.high if hasattr(c, 'high') else c['high']),
                    'low': float(c.low if hasattr(c, 'low') else c['low']),
                    'close': float(c.close if hasattr(c, 'close') else c['close']),
                    'volume': float(c.volume if hasattr(c, 'volume') else c.get('volume', 1.0))
                })
            df_ltf = pd.DataFrame(ltf_records)

            # Calculate LTF ATR
            tr1 = df_ltf['high'] - df_ltf['low']
            tr2 = (df_ltf['high'] - df_ltf['close'].shift(1)).abs()
            tr3 = (df_ltf['low'] - df_ltf['close'].shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            tr = tr.bfill().fillna(0.0)
            atr_series = tr.rolling(window=self.atr_period, min_periods=1).mean().bfill().fillna(0.0)
            
            current_atr = float(atr_series.iloc[-1])
            if current_atr <= 1e-6:
                current_atr = 0.0005  # Fallback for EURUSD 5 pips

            # Inspect recent LTF window for sweep events
            recent_ltf = df_ltf.iloc[-self.ltf_sweep_window:].copy()
            latest_bar = df_ltf.iloc[-1]
            prev_bar = df_ltf.iloc[-2]

            curr_close = float(latest_bar['close'])
            curr_open = float(latest_bar['open'])
            curr_high = float(latest_bar['high'])
            curr_low = float(latest_bar['low'])
            curr_body = abs(curr_close - curr_open)

            # Check Bullish Setup: SSL Swept -> LTF penetrated HTF Low and rejected -> Bullish Displacement
            ssl_penetrated = (recent_ltf['low'] < htf_ssl).any()
            bullish_sweep_active = ssl_penetrated and (curr_close > htf_ssl)
            
            # Displacement verification: Strong bullish body expanding upwards
            is_bullish_displacement = (
                curr_close > curr_open and
                curr_body >= (self.displacement_multiplier * current_atr) and
                curr_close > float(prev_bar['high'])
            )

            # Check Bearish Setup: BSL Swept -> LTF penetrated HTF High and rejected -> Bearish Displacement
            bsl_penetrated = (recent_ltf['high'] > htf_bsl).any()
            bearish_sweep_active = bsl_penetrated and (curr_close < htf_bsl)
            
            # Displacement verification: Strong bearish body expanding downwards
            is_bearish_displacement = (
                curr_close < curr_open and
                curr_body >= (self.displacement_multiplier * current_atr) and
                curr_close < float(prev_bar['low'])
            )

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["liquidity_sweep", "displacement"]

            # Volume context
            vol_mean = df_ltf['volume'].rolling(window=20, min_periods=1).mean().iloc[-1]
            vol_ratio = float(latest_bar['volume'] / (vol_mean if vol_mean > 0 else 1.0))

            if bullish_sweep_active and is_bullish_displacement:
                direction = "buy"
                tags.extend(["ssl_swept", "bullish_expansion"])
                disp_ratio = curr_body / current_atr
                base_conf = 0.70 + min(0.15, (disp_ratio - self.displacement_multiplier) * 0.1)
                if vol_ratio > 1.2:
                    base_conf += 0.05
                    tags.append("volume_surge")
                confidence = float(min(0.92, max(self.min_confidence, base_conf)))
                rationale_parts.append(
                    f"Bullish liquidity sweep of HTF SSL ({htf_ssl:.5f}). "
                    f"M15 displacement body of {curr_body:.5f} ({disp_ratio:.2f}x ATR) closed back above structure."
                )

            elif bearish_sweep_active and is_bearish_displacement:
                direction = "sell"
                tags.extend(["bsl_swept", "bearish_expansion"])
                disp_ratio = curr_body / current_atr
                base_conf = 0.70 + min(0.15, (disp_ratio - self.displacement_multiplier) * 0.1)
                if vol_ratio > 1.2:
                    base_conf += 0.05
                    tags.append("volume_surge")
                confidence = float(min(0.92, max(self.min_confidence, base_conf)))
                rationale_parts.append(
                    f"Bearish liquidity sweep of HTF BSL ({htf_bsl:.5f}). "
                    f"M15 displacement body of {curr_body:.5f} ({disp_ratio:.2f}x ATR) closed back below structure."
                )

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=confidence,
                    rationale="; ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No liquidity sweep displacement detected. HTF BSL: {htf_bsl:.5f}, HTF SSL: {htf_ssl:.5f}.",
                tags=["no_setup"]
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
