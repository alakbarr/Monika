from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from database.models import PriceOHLCV
from sqlalchemy import select
from datetime import datetime, timezone
import logging
import pandas as pd
import utils.clock as clock

logger = logging.getLogger('TradingAgent.XTIPairsReadiness')

BRENT_MT5_SYMBOL = 'XBRUSD'

@StrategyRegistry.register
class XTIPairsReadiness(EdgeStrategy):
    strategy_id = "xti_pairs_readiness"
    applicable_symbols = {'XTIUSD'}

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        cfg = settings.get('trading', {}).get('edge_strategy', {}).get('xti_pairs_readiness', {})
        if not cfg.get('enabled', False):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="strategy disabled in settings")

        now = clock.now()
        brent_symbol = cfg.get('brent_symbol', BRENT_MT5_SYMBOL)
        z_entry = cfg.get('z_entry_threshold', 2.0)
        z_tp = cfg.get('z_tp_target', 0.0)        # Mean reversion target
        z_sl = cfg.get('z_sl_threshold', 3.0)      # Stop if spread diverges more
        max_hold = cfg.get('max_hold_minutes', 7200)  # 5 trading days

        # Fetch Brent from DB (replaces yfinance)
        brent_rows = (await session.execute(
            select(PriceOHLCV.timestamp, PriceOHLCV.close)
            .where(
                PriceOHLCV.symbol == brent_symbol,
                PriceOHLCV.timeframe == 'D1',
                PriceOHLCV.timestamp <= now,
            )
            .order_by(PriceOHLCV.timestamp.desc()).limit(30)
        )).all()
        if not brent_rows:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale=f"{brent_symbol} data missing")

        # Fetch daily XTIUSD from DB
        xti_rows = (await session.execute(
            select(PriceOHLCV.timestamp, PriceOHLCV.close)
            .where(
                PriceOHLCV.symbol == 'XTIUSD',
                PriceOHLCV.timeframe == 'D1',
                PriceOHLCV.timestamp <= now,
            )
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(30)
        )).all()
        if not xti_rows:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="XTIUSD data missing")

        brent_df = pd.DataFrame(brent_rows, columns=['timestamp', 'close'])
        brent_df['timestamp'] = pd.to_datetime(brent_df['timestamp'], utc=True).dt.tz_localize(None).dt.tz_localize('UTC')
        brent_series = brent_df.set_index('timestamp')['close'].resample('D').last().dropna()
        brent = float(brent_series.iloc[-1] if not brent_series.empty else brent_df.iloc[0]['close'])

        xti_df = pd.DataFrame(xti_rows, columns=['timestamp', 'close'])
        xti_df['timestamp'] = pd.to_datetime(xti_df['timestamp'], utc=True).dt.tz_localize(None).dt.tz_localize('UTC')
        xti_series = xti_df.set_index('timestamp')['close'].resample('D').last().dropna()
        last_xti = float(xti_series.iloc[-1] if not xti_series.empty else xti_df.iloc[0]['close'])
        
        # Align series to calculate spread
        df = pd.concat([brent_series, xti_series], axis=1).dropna()
        df.columns = ['brent', 'xti']
        df['spread'] = df['brent'] - df['xti']

        if df.empty or len(df) < 5:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0,
                               rationale='insufficient joint Brent/WTI history for reliable Z-score — refusing to trade on fabricated statistics')
        else:
            # We must not include the current unclosed bar in the mean/std calculation to avoid lookahead bias
            historical_spreads = df['spread'].iloc[:-1] if len(df) > 1 else df['spread']
            if len(historical_spreads) < 2:
                return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="Not enough historical data for valid Z-score.")
            mean_spread = float(historical_spreads.mean())
            std_spread = float(historical_spreads.std())
            spread = float(df['spread'].iloc[-1])

        direction = None
        confluence = 0.0
        z_score = 0.0
        rationale = f"Brent={brent:.2f}, XTI={last_xti:.2f}, Spread={spread:.2f} (Mean={mean_spread:.2f}, Std={std_spread:.2f}). "

        if std_spread > 0:
            z_score = (spread - mean_spread) / std_spread
            if z_score > z_entry:
                direction = 'buy'
                confluence = 3.0
                rationale += f"Spread abnormally wide (Z={z_score:.1f} > {z_entry}). WTI is undervalued."
            elif z_score < -z_entry:
                direction = 'sell'
                confluence = 3.0
                rationale += f"Spread abnormally tight (Z={z_score:.1f} < -{z_entry}). WTI is overvalued."
            else:
                rationale += f"Spread is within normal range (Z={z_score:.1f})."
        else:
            rationale += "Not enough spread volatility to compute Z-score."

        # TimesFM 3.0 Multivariate Confirmation for Oil Spread
        tfm_meta = {}
        try:
            from indicators.timesfm_engine import TimesFMEngine
            tfm_engine = TimesFMEngine(settings)
            xti_fc = await tfm_engine.get_latest_forecast(session, 'XTIUSD', timeframe='H1', max_age_hours=8.0)
            if xti_fc:
                tfm_skew = float(xti_fc.get('quantile_skew', 0.0))
                tfm_meta['timesfm_skew'] = tfm_skew
                tfm_meta['timesfm_expected_range'] = xti_fc.get('expected_range')
                if direction == 'buy' and tfm_skew > 0.10:
                    confluence += 1.0
                    rationale += f" TimesFM confirms WTI bullish skew (+{tfm_skew:.2f})."
                elif direction == 'sell' and tfm_skew < -0.10:
                    confluence += 1.0
                    rationale += f" TimesFM confirms WTI bearish skew ({tfm_skew:.2f})."
                elif (direction == 'buy' and tfm_skew < -0.30) or (direction == 'sell' and tfm_skew > 0.30):
                    rationale += f" [Caution: TimesFM counter-skew ({tfm_skew:.2f})]."
        except Exception as tfm_err:
            logger.debug(f"TimesFM check failed in xti_pairs (non-fatal): {tfm_err}")

        if not direction:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=rationale)

        # Calculate spread-based SL/TP for both legs
        if direction == 'buy':  # WTI undervalued, spread too wide
            # TP: spread narrows to mean → WTI rises, Brent falls (or both converge)
            tp_spread_change = spread - (mean_spread + z_tp * std_spread)
            sl_spread_change = (mean_spread + z_sl * std_spread) - spread
            # Split change 50/50 between legs
            wti_tp = last_xti + tp_spread_change / 2
            wti_sl = last_xti - abs(sl_spread_change) / 2
            brn_tp = brent - tp_spread_change / 2
            brn_sl = brent + abs(sl_spread_change) / 2
            brn_direction = 'sell'
        else:  # WTI overvalued, spread too tight
            tp_spread_change = (mean_spread + z_tp * std_spread) - spread
            sl_spread_change = spread - (mean_spread - z_sl * std_spread)
            wti_tp = last_xti - tp_spread_change / 2
            wti_sl = last_xti + abs(sl_spread_change) / 2
            brn_tp = brent + tp_spread_change / 2
            brn_sl = brent - abs(sl_spread_change) / 2
            brn_direction = 'buy'

        # Build paired EdgeSignal
        brent_leg = EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=brent_symbol,
            direction=brn_direction,
            valid=True,
            confidence=min(1.0, confluence / 3.0),
            entry_price=brent,
            stop_loss=brn_sl,
            take_profit=brn_tp,
            max_hold_minutes=max_hold,
            exit_style='spread_pair',
            rationale=f"Hedge leg: {brn_direction} {brent_symbol}",
            tags=['xti_pairs_readiness', 'stat_arb', 'hedge_leg'],
            meta={'is_hedge_leg': True, 'z_score': z_score}
        )

        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            valid=True,
            confidence=min(1.0, confluence / 3.0),
            entry_price=last_xti,
            stop_loss=wti_sl,
            take_profit=wti_tp,
            max_hold_minutes=max_hold,
            exit_style='spread_pair',
            rationale=rationale,
            tags=['xti_pairs_readiness', 'stat_arb', 'primary_leg'],
            meta={'brent_price': brent, 'wti_price': last_xti,
                  'spread': spread, 'z_score': z_score},
            paired_leg=brent_leg,  # ← Links the hedge leg
        )
