from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_467904(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_467904"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.htf_timeframe = self.settings.get('htf_timeframe', 'H1')
        self.ltf_timeframe = self.settings.get('ltf_timeframe', 'M15')
        self.swing_window = int(self.settings.get('swing_window', 5))
        self.sweep_lookback = int(self.settings.get('sweep_lookback', 12))
        self.displacement_multiplier = float(self.settings.get('displacement_multiplier', 1.5))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            # Fetch historical candles for HTF and LTF
            candles_htf = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.htf_timeframe, limit=100
            )
            candles_ltf = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe=self.ltf_timeframe, limit=100
            )

            if not candles_htf or not candles_ltf:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle data fetched.",
                    tags=["no_data"]
                )

            # Helper to convert candles to DataFrame safely
            def candles_to_df(candles) -> pd.DataFrame:
                data = []
                for c in candles:
                    try:
                        high = c.high
                        low = c.low
                        close = c.close
                        open_val = c.open
                        volume = getattr(c, 'volume', 0.0)
                    except AttributeError:
                        high = c.get('high')
                        low = c.get('low')
                        close = c.get('close')
                        open_val = c.get('open')
                        volume = c.get('volume', 0.0)
                    
                    data.append({
                        'high': float(high),
                        'low': float(low),
                        'close': float(close),
                        'open': float(open_val),
                        'volume': float(volume) if volume is not None else 0.0
                    })
                df = pd.DataFrame(data)
                return df.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)

            df_htf = candles_to_df(candles_htf)
            df_ltf = candles_to_df(candles_ltf)

            if len(df_htf) < (2 * self.swing_window + 1) or len(df_ltf) < 30:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Dataframe length too short for indicator calculation.",
                    tags=["insufficient_length"]
                )

            # HTF Swing High / Low Detection (Strictly Historical)
            df_htf['is_swing_high'] = df_htf['high'].shift(self.swing_window) == df_htf['high'].rolling(2 * self.swing_window + 1).max()
            df_htf['is_swing_low'] = df_htf['low'].shift(self.swing_window) == df_htf['low'].rolling(2 * self.swing_window + 1).min()

            swing_highs = df_htf[df_htf['is_swing_high']]['high'].values
            swing_lows = df_htf[df_htf['is_swing_low']]['low'].values

            fallback_limit = min(len(df_htf) - 1, 50)
            latest_swing_high = float(swing_highs[-1]) if len(swing_highs) > 0 else float(df_htf['high'].iloc[-fallback_limit:-2].max())
            latest_swing_low = float(swing_lows[-1]) if len(swing_lows) > 0 else float(df_htf['low'].iloc[-fallback_limit:-2].min())

            # LTF Analysis
            df_ltf['body'] = (df_ltf['close'] - df_ltf['open']).abs()
            df_ltf['avg_body'] = df_ltf['body'].rolling(20, min_periods=1).mean()

            bullish_sweep_detected = False
            bullish_displacement_detected = False
            sweep_candle_high = 0.0

            bearish_sweep_detected = False
            bearish_displacement_detected = False
            sweep_candle_low = 0.0

            # Scan the last sweep_lookback candles on LTF
            start_idx = max(0, len(df_ltf) - self.sweep_lookback)
            
            # Bullish Sweep Check
            for i in range(start_idx, len(df_ltf)):
                row = df_ltf.iloc[i]
                if row['low'] < latest_swing_low:
                    # Found a candidate sweep candle
                    reclaimed = False
                    for j in range(i, len(df_ltf)):
                        if df_ltf.iloc[j]['close'] > latest_swing_low:
                            reclaimed = True
                            break
                    if reclaimed:
                        bullish_sweep_detected = True
                        sweep_candle_high = float(row['high'])
                        # Check for displacement after or at the sweep candle
                        for k in range(i, len(df_ltf)):
                            disp_row = df_ltf.iloc[k]
                            body_size = disp_row['close'] - disp_row['open']
                            avg_b = disp_row['avg_body']
                            if body_size > self.displacement_multiplier * avg_b:
                                # Strong bullish displacement and Market Structure Shift (MSS)
                                if float(df_ltf.iloc[-1]['close']) > sweep_candle_high:
                                    bullish_displacement_detected = True
                                    break
                        if bullish_displacement_detected:
                            break

            # Bearish Sweep Check
            for i in range(start_idx, len(df_ltf)):
                row = df_ltf.iloc[i]
                if row['high'] > latest_swing_high:
                    # Found a candidate sweep candle
                    reclaimed = False
                    for j in range(i, len(df_ltf)):
                        if df_ltf.iloc[j]['close'] < latest_swing_high:
                            reclaimed = True
                            break
                    if reclaimed:
                        bearish_sweep_detected = True
                        sweep_candle_low = float(row['low'])
                        # Check for displacement after or at the sweep candle
                        for k in range(i, len(df_ltf)):
                            disp_row = df_ltf.iloc[k]
                            body_size = disp_row['open'] - disp_row['close']
                            avg_b = disp_row['avg_body']
                            if body_size > self.displacement_multiplier * avg_b:
                                # Strong bearish displacement and Market Structure Shift (MSS)
                                if float(df_ltf.iloc[-1]['close']) < sweep_candle_low:
                                    bearish_displacement_detected = True
                                    break
                        if bearish_displacement_detected:
                            break

            # Determine final signal
            if bullish_displacement_detected and not bearish_displacement_detected:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='buy',
                    valid=True,
                    confidence=0.82,
                    rationale=f"HTF Swing Low ({latest_swing_low:.2f}) swept on LTF. Bullish displacement confirmed with MSS above {sweep_candle_high:.2f}.",
                    tags=["liquidity_sweep", "bullish_displacement", "mss"]
                )
            elif bearish_displacement_detected and not bullish_displacement_detected:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction='sell',
                    valid=True,
                    confidence=0.82,
                    rationale=f"HTF Swing High ({latest_swing_high:.2f}) swept on LTF. Bearish displacement confirmed with MSS below {sweep_candle_low:.2f}.",
                    tags=["liquidity_sweep", "bearish_displacement", "mss"]
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=True,
                    confidence=0.0,
                    rationale="No multi-timeframe liquidity sweep with displacement detected.",
                    tags=["neutral"]
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