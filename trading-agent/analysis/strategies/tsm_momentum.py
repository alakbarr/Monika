import logging
from typing import Any
from sqlalchemy import select
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.models import PriceOHLCV, StructureBreak
from analysis.calculators.regime_classifier import classify_market_regime

import utils.clock as clock

logger = logging.getLogger("TradingAgent.TSMMomentum")

LOOKBACKS = (63, 126, 252)
PURE_TSM = {'USDJPY', 'EURUSD'}
STRICT_REGIME = {'AUDUSD', 'GBPUSD'}

@StrategyRegistry.register
class TimeSeriesMomentum(EdgeStrategy):
    strategy_id = "tsm_momentum"
    applicable_symbols = {'USDJPY', 'EURUSD', 'AUDUSD', 'GBPUSD', 'XAUUSD'}
    compatible_regimes = {'TREND', 'STRONG_TREND'}
    factor_family = 'trend'
    min_sample_size = 30

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        now = clock.now()
        lookbacks = (
            int(self.cfg.get('lookback_short', LOOKBACKS[0])),
            int(self.cfg.get('lookback_med', LOOKBACKS[1])),
            int(self.cfg.get('lookback_long', LOOKBACKS[2])),
        )
        max_lb = max(lookbacks)
        min_lb = min(lookbacks)

        rows = (await session.execute(select(PriceOHLCV.close).where(
            PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'D1',
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.desc()).limit(max_lb + 5))).scalars().all()
        if len(rows) < min_lb + 1:
            # Fallback: Try resampling from H1 candles if available
            h1_rows = (await session.execute(select(PriceOHLCV.close).where(
                PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H1',
                PriceOHLCV.timestamp <= now
            ).order_by(PriceOHLCV.timestamp.desc()).limit((max_lb + 5) * 24))).scalars().all()
            if len(h1_rows) >= (min_lb + 1) * 24:
                rows = [h1_rows[i] for i in range(0, len(h1_rows), 24)][:max_lb + 5]
            else:
                return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="insufficient D1 history")

        closes = list(reversed(rows))
        latest = closes[-1]
        votes = [1 if (latest - closes[-1-lb]) > 0 else -1
                 for lb in lookbacks if len(closes) > lb and closes[-1-lb]]
        if not votes:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="no valid lookback windows")

        net, agreement = sum(votes), abs(sum(votes)) / len(votes)
        default_min_agreement = 1.0 if symbol in PURE_TSM else 0.67
        min_agreement = float(self.cfg.get('min_agreement', default_min_agreement))
        if agreement < min_agreement or net == 0:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                                rationale=f"agreement={agreement:.2f} < {min_agreement}")

        direction = 'buy' if net > 0 else 'sell'

        if symbol in STRICT_REGIME:
            regime = await classify_market_regime(session, symbol, settings)
            if regime['regime'] not in ('TREND', 'STRONG_TREND'):
                return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                                   rationale=f"regime={regime['regime']} fails strict confirmation")

        last_break = (await session.execute(select(StructureBreak).where(
            StructureBreak.symbol == symbol, StructureBreak.timeframe == 'D1',
            StructureBreak.formed_at <= now
        ).order_by(StructureBreak.formed_at.desc()).limit(1))).scalar_one_or_none()
        if last_break:
            htf_dir = 'buy' if last_break.direction == 'bullish' else 'sell'
            if htf_dir != direction:
                return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                                   rationale=f"D1 structure ({htf_dir}) conflicts with TSM ({direction})")

        # Predictive Momentum Check via TimesFM 3.0 (Anti-exhaustion gate)
        meta_data: dict[str, Any] = {
            "votes": votes,
            "sl_atr_multiplier": float(self.cfg.get("sl_atr_multiplier", 1.5)),
            "tp_sl_multiplier": float(self.cfg.get("tp_sl_multiplier", 2.5)),
        }
        try:
            from indicators.timesfm_engine import TimesFMEngine
            tfm_engine = TimesFMEngine(settings)
            tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe='H1', max_age_hours=8.0)
            if tfm_fc:
                tfm_skew = float(tfm_fc.get('quantile_skew', 0.0))
                meta_data['timesfm_skew'] = tfm_skew
                meta_data['timesfm_range'] = tfm_fc.get('expected_range')
                # Severe counter-skew indicates trend exhaustion
                if direction == 'buy' and tfm_skew < -0.35:
                    return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                                       rationale=f"TSM BUY vetoed: TimesFM detects strong counter-trend momentum exhaustion (skew={tfm_skew:.2f})")
                elif direction == 'sell' and tfm_skew > 0.35:
                    return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                                       rationale=f"TSM SELL vetoed: TimesFM detects strong counter-trend momentum exhaustion (skew={tfm_skew:.2f})")
                elif (direction == 'buy' and tfm_skew > 0.15) or (direction == 'sell' and tfm_skew < -0.15):
                    agreement = min(1.0, agreement + 0.10)
        except Exception as tfm_err:
            logger.debug(f"[{symbol}] TimesFM check failed in TSM (non-fatal): {tfm_err}")

        # Directional bias only — no entry/SL/TP; consumed either as a confluence_factor
        # by the LLM stage, or as a veto gate for other edges via meta['direction'].
        return EdgeSignal(self.strategy_id, symbol, direction, True, confidence=agreement,
                           rationale=f"TSM agreement={agreement:.2f}/{len(votes)}, HTF-confirmed.",
                           tags=["tsm", "trend_continuation", "trend"],
                           exit_style='trend_trailing',
                           meta=meta_data)


@StrategyRegistry.register
class TrendTrailingMomentum(TimeSeriesMomentum):
    strategy_id = "trend_trailing"

