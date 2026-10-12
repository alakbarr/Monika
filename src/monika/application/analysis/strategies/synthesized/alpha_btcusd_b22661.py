from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List
import math, numpy as np, pandas as pd, datetime, logging, decimal

class SynthesizedStrategy_alpha_btcusd_b22661(EdgeStrategy):
    strategy_id: str = "alpha_btcusd_b22661"
    applicable_symbols: set = {"BTCUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.base_lookback: int = self.settings.get("base_lookback", 24)
        self.min_lookback: int = self.settings.get("min_lookback", 12)
        self.max_lookback: int = self.settings.get("max_lookback", 48)
        self.atr_period: int = self.settings.get("atr_period", 14)
        self.volume_ma_period: int = self.settings.get("volume_ma_period", 20)
        self.rvol_threshold: float = self.settings.get("rvol_threshold", 1.35)
        self.expansion_threshold: float = self.settings.get("expansion_threshold", 1.15)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if symbol not in self.applicable_symbols:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Symbol {symbol} not applicable for this strategy.",
                tags=["inapplicable_symbol"]
            )

        lookback_fetch = max(self.max_lookback + self.volume_ma_period + 10, 100)
        candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=lookback_fetch)

        if not candles or len(candles) < lookback_fetch * 0.8:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient historical candle data for volume-weighted dynamic Donchian evaluation.",
                tags=["insufficient_data"]
            )

        highs = []
        lows = []
        closes = []
        volumes = []

        for c in candles:
            h = float(c.high if hasattr(c, 'high') else c['high'])
            l = float(c.low if hasattr(c, 'low') else c['low'])
            cl = float(c.close if hasattr(c, 'close') else c['close'])
            v = float(c.volume if hasattr(c, 'volume') else c.get('volume', 0.0) if isinstance(c, dict) else 0.0)
            highs.append(h)
            lows.append(l)
            closes.append(cl)
            volumes.append(v)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        # Calculate True Range and ATR
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = (df['high'] - df['prev_close']).abs()
        df['tr3'] = (df['low'] - df['prev_close']).abs()
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=self.atr_period).mean()
        df['atr_baseline'] = df['atr'].rolling(window=self.atr_period * 2).mean()

        # Volatility ratio to dynamically scale Donchian lookback window
        df['vol_ratio'] = df['atr'] / (df['atr_baseline'] + 1e-9)
        latest_vol_ratio = df['vol_ratio'].iloc[-1]
        
        if np.isnan(latest_vol_ratio) or latest_vol_ratio <= 0:
            dynamic_lookback = self.base_lookback
        else:
            # High volatility -> shorter lookback (faster breakout tracking); Low volatility -> wider lookback
            adjusted = int(round(self.base_lookback / latest_vol_ratio))
            dynamic_lookback = max(self.min_lookback, min(self.max_lookback, adjusted))

        # Volume MA and RVOL
        df['vol_ma'] = df['volume'].rolling(window=self.volume_ma_period).mean()
        df['rvol'] = df['volume'] / (df['vol_ma'] + 1e-9)

        # Dynamic Donchian Channels (shifted by 1 to prevent lookahead bias)
        df['donchian_high'] = df['high'].shift(1).rolling(window=dynamic_lookback).max()
        df['donchian_low'] = df['low'].shift(1).rolling(window=dynamic_lookback).min()
        df['donchian_mid'] = (df['donchian_high'] + df['donchian_low']) / 2.0
        df['donchian_width'] = (df['donchian_high'] - df['donchian_low']) / (df['donchian_mid'] + 1e-9)
        df['width_ma'] = df['donchian_width'].rolling(window=self.volume_ma_period).mean()

        # Volume-Weighted Price Anchor (VWAP of the dynamic channel lookback)
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['pv'] = df['typical_price'] * df['volume']
        rolling_pv = df['pv'].rolling(window=dynamic_lookback).sum()
        rolling_v = df['volume'].rolling(window=dynamic_lookback).sum()
        df['vwap_window'] = rolling_pv / (rolling_v + 1e-9)

        curr_close = df['close'].iloc[-1]
        curr_high = df['high'].iloc[-1]
        curr_low = df['low'].iloc[-1]
        curr_rvol = df['rvol'].iloc[-1]
        curr_vwap = df['vwap_window'].iloc[-1]
        curr_d_high = df['donchian_high'].iloc[-1]
        curr_d_low = df['donchian_low'].iloc[-1]
        curr_width = df['donchian_width'].iloc[-1]
        mean_width = df['width_ma'].iloc[-1]

        if np.isnan(curr_d_high) or np.isnan(curr_d_low) or np.isnan(curr_rvol):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale="Insufficient calculated indicator values.",
                tags=["indicator_na"]
            )

        channel_expansion = curr_width / (mean_width + 1e-9) if mean_width > 0 else 1.0
        direction = None
        confidence = 0.0
        rationale = ""
        tags = ["donchian_expansion", f"lookback_{dynamic_lookback}"]

        # Long Trigger: Breakout above dynamic Donchian high with volume confirmation and price above dynamic VWAP
        if curr_close > curr_d_high and curr_rvol >= self.rvol_threshold and curr_close > curr_vwap:
            direction = 'buy'
            tags.append("bullish_expansion_breakout")
            vol_factor = min((curr_rvol - 1.0) / 2.0, 0.4)
            expansion_factor = min(max((channel_expansion - 1.0), 0.0) * 0.3, 0.3)
            vwap_premium = min(max((curr_close - curr_vwap) / (curr_close * 0.02 + 1e-9), 0.0) * 0.15, 0.15)
            confidence = min(0.55 + vol_factor + expansion_factor + vwap_premium, 0.95)
            rationale = (
                f"Bullish volume-weighted dynamic Donchian expansion: Close ({curr_close:.2f}) > "
                f"Upper Bound ({curr_d_high:.2f}), RVOL={curr_rvol:.2f}x, Dynamic Window={dynamic_lookback}, "
                f"VWAP Anchor={curr_vwap:.2f}, Channel Expansion={channel_expansion:.2f}x"
            )

        # Short Trigger: Breakdown below dynamic Donchian low with volume confirmation and price below dynamic VWAP
        elif curr_close < curr_d_low and curr_rvol >= self.rvol_threshold and curr_close < curr_vwap:
            direction = 'sell'
            tags.append("bearish_expansion_breakdown")
            vol_factor = min((curr_rvol - 1.0) / 2.0, 0.4)
            expansion_factor = min(max((channel_expansion - 1.0), 0.0) * 0.3, 0.3)
            vwap_discount = min(max((curr_vwap - curr_close) / (curr_close * 0.02 + 1e-9), 0.0) * 0.15, 0.15)
            confidence = min(0.55 + vol_factor + expansion_factor + vwap_discount, 0.95)
            rationale = (
                f"Bearish volume-weighted dynamic Donchian expansion: Close ({curr_close:.2f}) < "
                f"Lower Bound ({curr_d_low:.2f}), RVOL={curr_rvol:.2f}x, Dynamic Window={dynamic_lookback}, "
                f"VWAP Anchor={curr_vwap:.2f}, Channel Expansion={channel_expansion:.2f}x"
            )
        else:
            rationale = (
                f"No breakout detected. Price ({curr_close:.2f}) within dynamic bounds "
                f"[{curr_d_low:.2f}, {curr_d_high:.2f}], RVOL={curr_rvol:.2f}x (threshold {self.rvol_threshold})."
            )

        is_valid = direction is not None and confidence >= 0.60

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=is_valid,
            confidence=round(confidence, 4),
            rationale=rationale,
            tags=tags
        )