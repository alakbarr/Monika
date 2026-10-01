import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal, CandleDict
from analysis.strategies.registry import StrategyRegistry
from analysis.calculators.volume_profile import compute_volume_profile


@StrategyRegistry.register
class BBVolumeProfileMeanReversion(EdgeStrategy):
    """
    Bollinger Bands + Volume Profile Mean Reversion Strategy.
    Identifies mean-reversion opportunities where price reaches Bollinger Band extremes
    confluent with Volume Profile Value Area edges (VAH / VAL) and targets the Point of Control (POC).
    """
    strategy_id = "bb_volume_profile"
    applicable_symbols = {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", 
        "USDCHF", "NZDUSD", "USDCAD", "US30"
    }
    compatible_regimes = {"RANGING", "CHOP", "MEAN_REVERTING", "COMPRESSED", "ALL"}
    factor_family = "mean_reversion"

    async def evaluate(self, session: AsyncSession, symbol: str, settings: dict) -> EdgeSignal:
        timeframe = self.cfg.get("timeframe", "H1")
        bb_period = int(self.cfg.get("bb_period", 20))
        bb_std = float(self.cfg.get("bb_std", 2.0))
        lookback = int(self.cfg.get("lookback", 60))

        candles = await self.get_historical_candles(session, symbol, timeframe=timeframe, limit=lookback)
        if len(candles) < bb_period + 5:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history ({len(candles)}/{bb_period}) on {timeframe}",
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]

        # Compute Bollinger Bands
        recent_closes = closes[-bb_period:]
        sma = float(np.mean(recent_closes))
        std = float(np.std(recent_closes))
        upper_bb = sma + (bb_std * std)
        lower_bb = sma - (bb_std * std)

        # Compute ATR (14)
        trs = []
        for i in range(1, len(candles)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)
        atr = float(np.mean(trs[-14:])) if trs else (std or 0.001)

        # Build DataFrame for Volume Profile
        df_candles = pd.DataFrame({
            "high": highs[-40:],
            "low": lows[-40:],
            "close": closes[-40:],
            "volume": volumes[-40:],
        })

        try:
            vp = compute_volume_profile(df_candles, num_bins=30)
            vah = vp.get("vah", upper_bb)
            val = vp.get("val", lower_bb)
            poc = vp.get("poc", sma)
        except Exception:
            vah, val, poc = upper_bb, lower_bb, sma

        current_price = closes[-1]

        # BUY: Price <= lower BB & Price <= VAL (Oversold at Value Area Low)
        if current_price <= lower_bb and current_price <= val:
            sl = current_price - (1.5 * atr)
            tp = poc if poc > current_price else sma
            risk = current_price - sl
            reward = tp - current_price
            if risk > 0 and reward > 0:
                confidence = 0.82 if reward >= risk * 1.5 else 0.70
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=confidence,
                    entry_price=current_price,
                    stop_loss=round(sl, 5),
                    take_profit=round(tp, 5),
                    factor_family="mean_reversion",
                    exit_style="intraday_adr",
                    ttl_minutes=120,
                    rationale=f"Mean Reversion Buy: Price ({current_price:.5f}) <= Lower BB ({lower_bb:.5f}) & VAL ({val:.5f}), targeting POC ({poc:.5f})",
                    tags=["mean_reversion", "bollinger_bands", "volume_profile"],
                    meta={"bb_lower": lower_bb, "bb_upper": upper_bb, "val": val, "vah": vah, "poc": poc},
                )

        # SELL: Price >= upper BB & Price >= VAH (Overbought at Value Area High)
        if current_price >= upper_bb and current_price >= vah:
            sl = current_price + (1.5 * atr)
            tp = poc if poc < current_price else sma
            risk = sl - current_price
            reward = current_price - tp
            if risk > 0 and reward > 0:
                confidence = 0.82 if reward >= risk * 1.5 else 0.70
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="sell",
                    valid=True,
                    confidence=confidence,
                    entry_price=current_price,
                    stop_loss=round(sl, 5),
                    take_profit=round(tp, 5),
                    factor_family="mean_reversion",
                    exit_style="intraday_adr",
                    ttl_minutes=120,
                    rationale=f"Mean Reversion Sell: Price ({current_price:.5f}) >= Upper BB ({upper_bb:.5f}) & VAH ({vah:.5f}), targeting POC ({poc:.5f})",
                    tags=["mean_reversion", "bollinger_bands", "volume_profile"],
                    meta={"bb_lower": lower_bb, "bb_upper": upper_bb, "val": val, "vah": vah, "poc": poc},
                )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale="Price within normal Bollinger / Value Area bounds",
        )
