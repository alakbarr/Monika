from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_xbrusd_5af3d8(EdgeStrategy):
    strategy_id: str = "alpha_xbrusd_5af3d8"
    applicable_symbols: set = {"XBRUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf: str = str(self.settings.get("htf", "H1"))
        self.ltf: str = str(self.settings.get("ltf", "M15"))
        self.htf_lookback: int = int(self.settings.get("htf_lookback", 30))
        self.atr_period: int = int(self.settings.get("atr_period", 14))
        self.displacement_mult: float = float(self.settings.get("displacement_mult", 1.25))
        self.volume_mult: float = float(self.settings.get("volume_mult", 1.15))
        self.sweep_tolerance_bars: int = int(self.settings.get("sweep_tolerance_bars", 4))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            if symbol not in self.applicable_symbols:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale=f"Symbol {symbol} not supported by strategy.",
                    tags=["invalid_symbol"]
                )

            # Fetch multi-timeframe candles
            htf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf, limit=max(self.htf_lookback + 20, 60)
            )
            ltf_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf, limit=100
            )

            if not htf_candles or len(htf_candles) < self.htf_lookback + 5:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient HTF candle data.",
                    tags=["insufficient_data", "htf"]
                )

            if not ltf_candles or len(ltf_candles) < max(self.atr_period + 10, 30):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient LTF candle data.",
                    tags=["insufficient_data", "ltf"]
                )

            # Parse HTF Candles
            htf_records: List[Dict[str, float]] = []
            for c in htf_candles:
                try:
                    htf_records.append({
                        'open': float(c.open), 'high': float(c.high),
                        'low': float(c.low), 'close': float(c.close),
                        'volume': float(c.volume) if c.volume is not None else 1.0
                    })
                except AttributeError:
                    htf_records.append({
                        'open': float(c.get('open', 0.0)), 'high': float(c.get('high', 0.0)),
                        'low': float(c.get('low', 0.0)), 'close': float(c.get('close', 0.0)),
                        'volume': float(c.get('volume', 1.0))
                    })

            # Parse LTF Candles
            ltf_records: List[Dict[str, float]] = []
            for c in ltf_candles:
                try:
                    ltf_records.append({
                        'open': float(c.open), 'high': float(c.high),
                        'low': float(c.low), 'close': float(c.close),
                        'volume': float(c.volume) if c.volume is not None else 1.0
                    })
                except AttributeError:
                    ltf_records.append({
                        'open': float(c.get('open', 0.0)), 'high': float(c.get('high', 0.0)),
                        'low': float(c.get('low', 0.0)), 'close': float(c.get('close', 0.0)),
                        'volume': float(c.get('volume', 1.0))
                    })

            df_htf = pd.DataFrame(htf_records).replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
            df_ltf = pd.DataFrame(ltf_records).replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

            # Extract HTF Liquidity Levels (Excluding current unfinished / active HTF candle)
            pool_window = df_htf.iloc[-(self.htf_lookback + 1):-1]
            htf_bsl = float(pool_window['high'].max())  # Buy-side liquidity pool (swing high)
            htf_ssl = float(pool_window['low'].min())   # Sell-side liquidity pool (swing low)

            # LTF ATR & Volume metrics
            prev_close = df_ltf['close'].shift(1)
            tr = np.maximum(
                df_ltf['high'] - df_ltf['low'],
                np.maximum(
                    np.abs(df_ltf['high'] - prev_close),
                    np.abs(df_ltf['low'] - prev_close)
                )
            ).fillna(0.0)
            atr_series = tr.rolling(window=self.atr_period, min_periods=1).mean().fillna(0.0)
            vol_ma_series = df_ltf['volume'].rolling(window=self.atr_period, min_periods=1).mean().fillna(1.0)

            current_atr = float(atr_series.iloc[-1])
            avg_vol = float(vol_ma_series.iloc[-1])

            if current_atr <= 0:
                current_atr = 1e-4

            # Analysis of the latest trigger candle and recent sweep window
            curr = df_ltf.iloc[-1]
            c_open, c_high, c_low, c_close, c_vol = float(curr['open']), float(curr['high']), float(curr['low']), float(curr['close']), float(curr['volume'])
            body_size = abs(c_close - c_open)

            recent_ltf = df_ltf.iloc[-self.sweep_tolerance_bars:]
            recent_lowest = float(recent_ltf['low'].min())
            recent_highest = float(recent_ltf['high'].max())

            # Evaluate Bullish Displacement after Sell-Side Liquidity (SSL) Sweep
            # Price breached HTF SSL recently, and current bar shows strong upward displacement closing back above SSL
            swept_ssl = recent_lowest < htf_ssl
            bullish_displacement = (
                (c_close > c_open) and
                (c_close > htf_ssl) and
                (body_size >= self.displacement_mult * current_atr) and
                ((c_close - c_low) >= 0.70 * (c_high - c_low) if (c_high > c_low) else True)
            )

            # Evaluate Bearish Displacement after Buy-Side Liquidity (BSL) Sweep
            # Price breached HTF BSL recently, and current bar shows strong downward displacement closing back below BSL
            swept_bsl = recent_highest > htf_bsl
            bearish_displacement = (
                (c_close < c_open) and
                (c_close < htf_bsl) and
                (body_size >= self.displacement_mult * current_atr) and
                ((c_high - c_close) >= 0.70 * (c_high - c_low) if (c_high > c_low) else True)
            )

            direction: Optional[str] = None
            confidence: float = 0.0
            rationale_parts: List[str] = []
            tags: List[str] = ["liquidity_sweep", "displacement", "xbrusd"]

            if swept_ssl and bullish_displacement:
                direction = "buy"
                sweep_depth = (htf_ssl - recent_lowest) / current_atr
                vol_ratio = (c_vol / avg_vol) if avg_vol > 0 else 1.0
                body_ratio = body_size / current_atr

                # Multi-factor confidence score calculation
                base_conf = 0.70
                vol_bonus = min(0.12, max(0.0, (vol_ratio - 1.0) * 0.1))
                disp_bonus = min(0.10, max(0.0, (body_ratio - self.displacement_mult) * 0.08))
                depth_bonus = min(0.08, max(0.0, sweep_depth * 0.05))

                confidence = float(np.clip(base_conf + vol_bonus + disp_bonus + depth_bonus, 0.50, 0.95))
                rationale_parts.append(
                    f"Bullish SSL sweep on XBRUSD below {htf_ssl:.3f} (Lowest: {recent_lowest:.3f}). "
                    f"Displacement body ({body_size:.3f}) >= {self.displacement_mult:.2f}x ATR ({current_atr:.3f}). "
                    f"Volume Ratio: {vol_ratio:.2f}x."
                )
                tags.extend(["bullish_sweep", "ssl_liquidity_captured"])

            elif swept_bsl and bearish_displacement:
                direction = "sell"
                sweep_depth = (recent_highest - htf_bsl) / current_atr
                vol_ratio = (c_vol / avg_vol) if avg_vol > 0 else 1.0
                body_ratio = body_size / current_atr

                # Multi-factor confidence score calculation
                base_conf = 0.70
                vol_bonus = min(0.12, max(0.0, (vol_ratio - 1.0) * 0.1))
                disp_bonus = min(0.10, max(0.0, (body_ratio - self.displacement_mult) * 0.08))
                depth_bonus = min(0.08, max(0.0, sweep_depth * 0.05))

                confidence = float(np.clip(base_conf + vol_bonus + disp_bonus + depth_bonus, 0.50, 0.95))
                rationale_parts.append(
                    f"Bearish BSL sweep on XBRUSD above {htf_bsl:.3f} (Highest: {recent_highest:.3f}). "
                    f"Displacement body ({body_size:.3f}) >= {self.displacement_mult:.2f}x ATR ({current_atr:.3f}). "
                    f"Volume Ratio: {vol_ratio:.2f}x."
                )
                tags.extend(["bearish_sweep", "bsl_liquidity_captured"])

            if direction is not None:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=direction,
                    valid=True,
                    confidence=round(confidence, 4),
                    rationale=" | ".join(rationale_parts),
                    tags=tags
                )

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"No HTF sweep displacement setup detected on {symbol}. HTF BSL: {htf_bsl:.3f}, HTF SSL: {htf_ssl:.3f}.",
                tags=["neutral", "no_sweep"]
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