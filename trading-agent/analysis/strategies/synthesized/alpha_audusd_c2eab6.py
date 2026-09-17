from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_audusd_c2eab6(EdgeStrategy):
    strategy_id: str = "alpha_audusd_c2eab6"
    applicable_symbols: set = {"AUDUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.h1_lookback = self.settings.get("h1_lookback", 48)
        self.m5_lookback = self.settings.get("m5_lookback", 100)
        self.sweep_window = self.settings.get("sweep_window", 12)
        self.displacement_multiplier = self.settings.get("displacement_multiplier", 1.5)

    def _parse_candles(self, candles: List[Any]) -> List[Dict[str, float]]:
        parsed = []
        for c in candles:
            try:
                o = float(getattr(c, 'open', None) if hasattr(c, 'open') else c.get('open') if isinstance(c, dict) else 0.0)
                h = float(getattr(c, 'high', None) if hasattr(c, 'high') else c.get('high') if isinstance(c, dict) else 0.0)
                l = float(getattr(c, 'low', None) if hasattr(c, 'low') else c.get('low') if isinstance(c, dict) else 0.0)
                cls = float(getattr(c, 'close', None) if hasattr(c, 'close') else c.get('close') if isinstance(c, dict) else 0.0)
                parsed.append({'open': o, 'high': h, 'low': l, 'close': cls})
            except Exception:
                continue
        return parsed

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not applicable.",
                tags=["invalid_symbol"]
            )

        try:
            # Fetch H1 candles for HTF liquidity levels
            h1_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='H1', limit=self.h1_lookback + 5
            )
            # Fetch M5 candles for LTF execution
            m5_candles = await self.get_historical_candles(
                session=session, symbol=symbol, timeframe='M5', limit=self.m5_lookback
            )

            if not h1_candles or len(h1_candles) < 24 or not m5_candles or len(m5_candles) < 50:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Insufficient candle history for multi-timeframe analysis.",
                    tags=["insufficient_data"]
                )

            # Parse candles safely
            h1_parsed = self._parse_candles(h1_candles)
            m5_parsed = self._parse_candles(m5_candles)

            if len(h1_parsed) < 24 or len(m5_parsed) < 50:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="Failed to parse sufficient candle data.",
                    tags=["parse_error"]
                )

            # Identify HTF Liquidity Pools (Swing High / Swing Low)
            # Exclude the last 2 candles to avoid current active/forming levels
            htf_high = max(c['high'] for c in h1_parsed[-self.h1_lookback:-2])
            htf_low = min(c['low'] for c in h1_parsed[-self.h1_lookback:-2])

            # Calculate LTF average body size for displacement threshold
            m5_bodies = [abs(c['close'] - c['open']) for c in m5_parsed[-50:]]
            avg_body = np.mean(m5_bodies) if m5_bodies else 0.0001
            std_body = np.std(m5_bodies) if m5_bodies else 0.0001
            displacement_threshold = avg_body + (self.displacement_multiplier * std_body)

            # Analyze recent M5 candles for sweeps
            recent_m5 = m5_parsed[-self.sweep_window:]
            
            swept_high = any(c['high'] > htf_high for c in recent_m5)
            swept_low = any(c['low'] < htf_low for c in recent_m5)

            current_m5 = m5_parsed[-1]
            
            # Check for Bearish Sweep & Displacement (Sell)
            bearish_signal = False
            bearish_confidence = 0.5
            bearish_rationale = ""
            
            if swept_high and current_m5['close'] < htf_high:
                # Look for displacement candle in the sweep window
                displacement_found = False
                for c in recent_m5:
                    if (c['open'] - c['close']) > displacement_threshold:
                        displacement_found = True
                        break
                
                # Market Structure Shift: current close is below the minimum close of the pre-sweep window
                pre_sweep_m5 = m5_parsed[-25:-12]
                pre_sweep_low = min(c['close'] for c in pre_sweep_m5) if pre_sweep_m5 else current_m5['close']
                
                if displacement_found and current_m5['close'] < pre_sweep_low:
                    bearish_signal = True
                    bearish_confidence = 0.70
                    # Clean sweep bonus (no M5 candle body closed above HTF high)
                    clean_sweep = all(max(c['open'], c['close']) < htf_high for c in recent_m5)
                    if clean_sweep:
                        bearish_confidence += 0.10
                    # Strong displacement bonus
                    max_bear_body = max((c['open'] - c['close']) for c in recent_m5)
                    if max_bear_body > (displacement_threshold * 1.5):
                        bearish_confidence += 0.10
                    bearish_confidence = min(0.95, bearish_confidence)
                    bearish_rationale = (
                        f"AUDUSD swept HTF High ({htf_high:.5f}) and showed strong bearish displacement "
                        f"({max_bear_body:.5f} vs threshold {displacement_threshold:.5f}) with Market Structure Shift."
                    )

            # Check for Bullish Sweep & Displacement (Buy)
            bullish_signal = False
            bullish_confidence = 0.5
            bullish_rationale = ""

            if swept_low and current_m5['close'] > htf_low:
                # Look for displacement candle in the sweep window
                displacement_found = False
                for c in recent_m5:
                    if (c['close'] - c['open']) > displacement_threshold:
                        displacement_found = True
                        break
                
                # Market Structure Shift: current close is above the maximum close of the pre-sweep window
                pre_sweep_m5 = m5_parsed[-25:-12]
                pre_sweep_high = max(c['close'] for c in pre_sweep_m5) if pre_sweep_m5 else current_m5['close']

                if displacement_found and current_m5['close'] > pre_sweep_high:
                    bullish_signal = True
                    bullish_confidence = 0.70
                    # Clean sweep bonus (no M5 candle body closed below HTF low)
                    clean_sweep = all(min(c['open'], c['close']) > htf_low for c in recent_m5)
                    if clean_sweep:
                        bullish_confidence += 0.10
                    # Strong displacement bonus
                    max_bull_body = max((c['close'] - c['open']) for c in recent_m5)
                    if max_bull_body > (displacement_threshold * 1.5):
                        bullish_confidence += 0.10
                    bullish_confidence = min(0.95, bullish_confidence)
                    bullish_rationale = (
                        f"AUDUSD swept HTF Low ({htf_low:.5f}) and showed strong bullish displacement "
                        f"({max_bull_body:.5f} vs threshold {displacement_threshold:.5f}) with Market Structure Shift."
                    )

            # Resolve conflicting signals
            if bullish_signal and bearish_signal:
                if bullish_confidence > bearish_confidence:
                    bearish_signal = False
                else:
                    bullish_signal = False

            if bullish_signal:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=round(bullish_confidence, 2),
                    rationale=bullish_rationale,
                    tags=["liquidity_sweep", "bullish_displacement", "multi_timeframe"]
                )
            elif bearish_signal:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=round(bearish_confidence, 2),
                    rationale=bearish_rationale,
                    tags=["liquidity_sweep", "bearish_displacement", "multi_timeframe"]
                )
            else:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction=None,
                    valid=False,
                    confidence=0.0,
                    rationale="No liquidity sweep with valid displacement detected on AUDUSD.",
                    tags=["neutral", "no_sweep"]
                )

        except Exception as e:
            logging.error(f"Error in strategy {self.strategy_id} evaluation: {str(e)}")
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Execution error: {str(e)}",
                tags=["error"]
            )