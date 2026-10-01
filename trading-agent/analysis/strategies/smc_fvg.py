from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal, CandleDict
from analysis.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class SMCFairValueGapStrategy(EdgeStrategy):
    """
    SMC Fair Value Gap (FVG) Strategy.
    Identifies 3-candle price imbalances on H1/H4 timeframes and trades pullbacks
    into unmitigated FVG zones with targeted Risk-Reward ratios.
    """
    strategy_id = "smc_fvg"
    applicable_symbols = {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", 
        "USDCHF", "NZDUSD", "USDCAD", "BTCUSD", "ETHUSD", "US30"
    }
    compatible_regimes = {"TREND", "STRONG_TREND", "RANGING", "EXPANDING_FAST", "ALL"}
    factor_family = "trend"

    async def evaluate(self, session: AsyncSession, symbol: str, settings: dict) -> EdgeSignal:
        timeframe = self.cfg.get("timeframe", "H1")
        min_rr = float(self.cfg.get("min_rr", 2.0))
        lookback = int(self.cfg.get("lookback", 60))

        candles = await self.get_historical_candles(session, symbol, timeframe=timeframe, limit=lookback)
        if len(candles) < 15:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction=None,
                valid=False,
                confidence=0.0,
                rationale=f"Insufficient candle history ({len(candles)}/{lookback}) on {timeframe}",
            )

        current = candles[-1]
        current_price = current.close

        # Detect FVGs from history
        # 3-candle imbalance:
        # Bullish FVG: candle[i+2].low > candle[i].high -> gap between candle[i].high and candle[i+2].low
        # Bearish FVG: candle[i+2].high < candle[i].low -> gap between candle[i+2].high and candle[i].low
        bullish_fvgs = []
        bearish_fvgs = []

        for i in range(len(candles) - 3):
            c1, c2, c3 = candles[i], candles[i+1], candles[i+2]
            
            # Bullish FVG
            if c3.low > c1.high:
                gap_low = c1.high
                gap_high = c3.low
                gap_mid = (gap_low + gap_high) / 2.0
                # Check mitigation in subsequent candles (up to current)
                mitigated = any(c.low <= gap_mid for c in candles[i+3:])
                if not mitigated:
                    bullish_fvgs.append({
                        "gap_low": gap_low,
                        "gap_high": gap_high,
                        "gap_mid": gap_mid,
                        "c1_low": c1.low,
                        "index": i,
                    })

            # Bearish FVG
            elif c3.high < c1.low:
                gap_high = c1.low
                gap_low = c3.high
                gap_mid = (gap_low + gap_high) / 2.0
                mitigated = any(c.high >= gap_mid for c in candles[i+3:])
                if not mitigated:
                    bearish_fvgs.append({
                        "gap_low": gap_low,
                        "gap_high": gap_high,
                        "gap_mid": gap_mid,
                        "c1_high": c1.high,
                        "index": i,
                    })

        # Evaluate if current price is within or testing the most recent unmitigated Bullish FVG
        if bullish_fvgs:
            latest_fvg = bullish_fvgs[-1]
            if latest_fvg["gap_low"] <= current_price <= latest_fvg["gap_high"] * 1.002:
                sl = latest_fvg["gap_low"] - (latest_fvg["gap_high"] - latest_fvg["gap_low"]) * 0.2
                risk = current_price - sl
                if risk > 0:
                    tp = current_price + (risk * min_rr)
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction="buy",
                        valid=True,
                        confidence=0.80,
                        entry_price=current_price,
                        stop_loss=round(sl, 5),
                        take_profit=round(tp, 5),
                        factor_family="trend",
                        exit_style="intraday_adr",
                        ttl_minutes=180,
                        rationale=f"SMC Bullish FVG retest on {timeframe} ({latest_fvg['gap_low']:.5f} - {latest_fvg['gap_high']:.5f}) with RR 1:{min_rr}",
                        tags=["smc", "fvg", "bullish_imbalance"],
                        meta={"fvg": latest_fvg, "timeframe": timeframe},
                    )

        # Evaluate if current price is within or testing the most recent unmitigated Bearish FVG
        if bearish_fvgs:
            latest_fvg = bearish_fvgs[-1]
            if latest_fvg["gap_low"] * 0.998 <= current_price <= latest_fvg["gap_high"]:
                sl = latest_fvg["gap_high"] + (latest_fvg["gap_high"] - latest_fvg["gap_low"]) * 0.2
                risk = sl - current_price
                if risk > 0:
                    tp = current_price - (risk * min_rr)
                    return EdgeSignal(
                        strategy_id=self.strategy_id,
                        symbol=symbol,
                        direction="sell",
                        valid=True,
                        confidence=0.80,
                        entry_price=current_price,
                        stop_loss=round(sl, 5),
                        take_profit=round(tp, 5),
                        factor_family="trend",
                        exit_style="intraday_adr",
                        ttl_minutes=180,
                        rationale=f"SMC Bearish FVG retest on {timeframe} ({latest_fvg['gap_low']:.5f} - {latest_fvg['gap_high']:.5f}) with RR 1:{min_rr}",
                        tags=["smc", "fvg", "bearish_imbalance"],
                        meta={"fvg": latest_fvg, "timeframe": timeframe},
                    )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale=f"No active FVG re-test confluence found on {timeframe}",
        )
