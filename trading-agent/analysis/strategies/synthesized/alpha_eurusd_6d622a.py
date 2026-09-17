from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_eurusd_6d622a(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_6d622a"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.timeframe = self.settings.get("timeframe", "H1")
        self.limit = self.settings.get("limit", 150)
        self.base_window = self.settings.get("base_window", 24)
        self.k = self.settings.get("k", 0.5)
        self.vol_threshold = self.settings.get("vol_threshold", 1.2)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        current_settings = {**self.settings, **settings}
        timeframe = current_settings.get("timeframe", self.timeframe)
        limit = current_settings.get("limit", self.limit)
        
        try:
            candles = await self.get_historical_candles(
                session=session, 
                symbol=symbol, 
                timeframe=timeframe, 
                limit=limit
            )
        except Exception as e:
            logging.error(f"Error fetching candles for {symbol}: {e}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Failed to fetch candles: {str(e)}",
                tags=["error"]
            )

        if not candles or len(candles) < 60:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history. Got {len(candles) if candles else 0}, need 60.",
                tags=["insufficient_data"]
            )

        try:
            # Convert candles to DataFrame safely
            data = []
            for c in candles:
                try:
                    high = float(c.high) if hasattr(c, 'high') else float(c['high'])
                    low = float(c.low) if hasattr(c, 'low') else float(c['low'])
                    close = float(c.close) if hasattr(c, 'close') else float(c['close'])
                    open_val = float(c.open) if hasattr(c, 'open') else float(c['open'])
                    volume = float(c.volume) if hasattr(c, 'volume') else float(c['volume'])
                except Exception:
                    continue
                data.append({
                    'high': high,
                    'low': low,
                    'close': close,
                    'open': open_val,
                    'volume': volume
                })

            if len(data) < 60:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient valid candles after parsing.",
                    tags=["insufficient_data"]
                )

            df = pd.DataFrame(data)

            # Calculate volume-weighted dynamic parameters safely
            df['vol_ma'] = df['volume'].rolling(window=20, min_periods=1).mean().replace(0, 1e-9).fillna(1.0)
            df['vol_ratio'] = (df['volume'] / df['vol_ma']).replace([np.inf, -np.inf], 1.0).fillna(1.0)
            df['vol_ratio'] = df['vol_ratio'].apply(lambda x: x if (pd.notna(x) and not np.isinf(x) and x > 1e-6) else 1.0)
            
            # Dynamic lookback window N_t based on volume ratio (guaranteed clean integer 10 to 50)
            raw_n = (self.base_window / df['vol_ratio']).clip(10, 50).round().fillna(self.base_window)
            df['dynamic_n'] = raw_n.astype(int)

            # Precompute rolling max/min for all possible dynamic windows (10 to 50)
            for w in range(10, 51):
                df[f'max_{w}'] = df['high'].shift(1).rolling(window=w, min_periods=1).max()
                df[f'min_{w}'] = df['low'].shift(1).rolling(window=w, min_periods=1).min()

            # Map dynamic window to bands
            def get_dynamic_upper(row):
                try:
                    val = row.get('dynamic_n')
                    n = int(val) if pd.notna(val) and not np.isinf(val) else self.base_window
                except Exception:
                    n = self.base_window
                col = f'max_{n}'
                return row.get(col, row.get(f'max_{self.base_window}'))

            def get_dynamic_lower(row):
                try:
                    val = row.get('dynamic_n')
                    n = int(val) if pd.notna(val) and not np.isinf(val) else self.base_window
                except Exception:
                    n = self.base_window
                col = f'min_{n}'
                return row.get(col, row.get(f'min_{self.base_window}'))

            df['upper_band'] = df.apply(get_dynamic_upper, axis=1)
            df['lower_band'] = df.apply(get_dynamic_lower, axis=1)

            # Volume-Weighted ATR (VWATR) for dynamic expansion
            df['prev_close'] = df['close'].shift(1)
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    (df['high'] - df['prev_close']).abs(),
                    (df['low'] - df['prev_close']).abs()
                )
            )
            df['vwtr'] = df['tr'] * df['vol_ratio']
            df['vwatr'] = df['vwtr'].ewm(span=14, adjust=False).mean()

            # Expansion Bands
            df['u_exp'] = df['upper_band'] + self.k * df['vwatr']
            df['l_exp'] = df['lower_band'] - self.k * df['vwatr']

            # Trend Filter (EMA 20 vs EMA 50)
            df['ema_fast'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=50, adjust=False).mean()

            # Extract latest values
            latest = df.iloc[-1]
            close = latest['close']
            u_exp = latest['u_exp']
            l_exp = latest['l_exp']
            vol_ratio = latest['vol_ratio']
            ema_fast = latest['ema_fast']
            ema_slow = latest['ema_slow']

            if pd.isna(u_exp) or pd.isna(l_exp) or pd.isna(vol_ratio):
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="NaN values in calculated indicators.",
                    tags=["nan_values"]
                )

            direction = None
            confidence = 0.0
            rationale = ""
            tags = ["donchian_expansion"]

            # Signal Logic
            is_bullish_breakout = (close > u_exp) and (vol_ratio > self.vol_threshold) and (ema_fast > ema_slow)
            is_bearish_breakout = (close < l_exp) and (vol_ratio > self.vol_threshold) and (ema_fast < ema_slow)

            if is_bullish_breakout:
                direction = "buy"
                confidence = float(np.clip(0.5 + (vol_ratio - self.vol_threshold) * 0.25, 0.5, 0.95))
                rationale = (
                    f"Bullish dynamic Donchian expansion breakout. Close ({close:.5f}) > Upper Exp Band ({u_exp:.5f}) "
                    f"with Volume Ratio ({vol_ratio:.2f}x) and supportive EMA trend."
                )
                tags.extend(["bullish_breakout", "volume_surge"])
            elif is_bearish_breakout:
                direction = "sell"
                confidence = float(np.clip(0.5 + (vol_ratio - self.vol_threshold) * 0.25, 0.5, 0.95))
                rationale = (
                    f"Bearish dynamic Donchian expansion breakout. Close ({close:.5f}) < Lower Exp Band ({l_exp:.5f}) "
                    f"with Volume Ratio ({vol_ratio:.2f}x) and supportive EMA trend."
                )
                tags.extend(["bearish_breakout", "volume_surge"])
            else:
                direction = None
                confidence = 0.0
                rationale = (
                    f"No breakout detected. Close ({close:.5f}) is within dynamic Donchian expansion bands "
                    f"[{l_exp:.5f}, {u_exp:.5f}] with Volume Ratio {vol_ratio:.2f}x."
                )
                tags.append("no_signal")

            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=direction,
                valid=True,
                confidence=confidence,
                rationale=rationale,
                tags=tags
            )
        except Exception as calc_err:
            logging.warning(f"[{self.strategy_id}] Calculation error on {symbol}: {calc_err}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Calculation error: {calc_err}",
                tags=["error"]
            )