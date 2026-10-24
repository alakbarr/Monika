import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.infrastructure.database.models import PriceOHLCV

logger = logging.getLogger("TradingAgent.XTIPairsReadiness")

BRENT_MT5_SYMBOL = "XBRUSD"


@StrategyRegistry.register
class XTIPairsReadiness(EdgeStrategy):
    strategy_id = "xti_pairs_readiness"
    applicable_symbols = {"XTIUSD"}
    compatible_regimes = {"RANGE", "WEAK_TREND", "VOLATILE_CHOP"}
    factor_family = "stat_arb"

    async def evaluate(self, session, symbol, settings, as_of: Optional[datetime] = None) -> EdgeSignal:
        now = as_of or clock.now()
        cfg = settings.get("trading", {}).get("edge_strategy", {}).get("xti_pairs_readiness", {})
        if not cfg.get("enabled", False):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="strategy disabled in settings")

        brent_symbol = cfg.get("brent_symbol", BRENT_MT5_SYMBOL)
        lookback_bars = int(cfg.get("lookback_bars", 60))
        z_entry = float(cfg.get("z_entry_threshold", 2.0))
        z_tp = float(cfg.get("z_tp_target", 0.5))  # Partial mean reversion target (avoids swap decay)
        z_sl = float(cfg.get("z_sl_threshold", 3.0))  # Stop if spread diverges more
        max_hold = int(cfg.get("max_hold_minutes", 14400))  # 10 trading days (14400 mins) to match half-life
        adf_max_p_cfg = cfg.get("adf_max_pvalue", 0.15)
        adf_max_p = float(adf_max_p_cfg) if adf_max_p_cfg is not None else None

        query_limit = max(lookback_bars + 15, 75)

        # Fetch Brent from DB (replaces yfinance)
        brent_rows = (
            await session.execute(
                select(PriceOHLCV.timestamp, PriceOHLCV.close)
                .where(
                    PriceOHLCV.symbol == brent_symbol,
                    PriceOHLCV.timeframe == "D1",
                    PriceOHLCV.timestamp <= now,
                )
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(query_limit)
            )
        ).all()
        if not brent_rows:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=f"{brent_symbol} data missing")

        # Fetch daily XTIUSD from DB
        xti_rows = (
            await session.execute(
                select(PriceOHLCV.timestamp, PriceOHLCV.close)
                .where(
                    PriceOHLCV.symbol == "XTIUSD",
                    PriceOHLCV.timeframe == "D1",
                    PriceOHLCV.timestamp <= now,
                )
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(query_limit)
            )
        ).all()
        if not xti_rows:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="XTIUSD data missing")

        brent_df = pd.DataFrame(brent_rows, columns=["timestamp", "close"])
        brent_df["timestamp"] = (
            pd.to_datetime(brent_df["timestamp"], utc=True).dt.tz_localize(None).dt.tz_localize("UTC")
        )
        brent_df = brent_df.sort_values("timestamp")
        brent_series = brent_df.set_index("timestamp")["close"].resample("D").last().dropna()
        brent = float(brent_series.iloc[-1] if not brent_series.empty else brent_df.iloc[-1]["close"])

        xti_df = pd.DataFrame(xti_rows, columns=["timestamp", "close"])
        xti_df["timestamp"] = pd.to_datetime(xti_df["timestamp"], utc=True).dt.tz_localize(None).dt.tz_localize("UTC")
        xti_df = xti_df.sort_values("timestamp")
        xti_series = xti_df.set_index("timestamp")["close"].resample("D").last().dropna()
        last_xti = float(xti_series.iloc[-1] if not xti_series.empty else xti_df.iloc[-1]["close"])

        # Align series to calculate spread
        df = pd.concat([brent_series, xti_series], axis=1).dropna()
        df.columns = ["brent", "xti"]
        df["spread"] = df["brent"] - df["xti"]

        if df.empty or len(df) < 5:
            return EdgeSignal(
                self.strategy_id,
                symbol,
                None,
                False,
                0.0,
                rationale="insufficient joint Brent/WTI history for reliable Z-score — refusing to trade on fabricated statistics",
            )
        else:
            # We must not include the current unclosed bar in the mean/std calculation to avoid lookahead bias
            historical_spreads = df["spread"].iloc[:-1].tail(lookback_bars) if len(df) > 1 else df["spread"]
            if len(historical_spreads) < 2:
                return EdgeSignal(
                    self.strategy_id,
                    symbol,
                    None,
                    False,
                    0.0,
                    rationale="Not enough historical data for valid Z-score.",
                )
            mean_spread = float(np.mean(np.asarray(historical_spreads, dtype=float)))
            std_spread = float(np.std(np.asarray(historical_spreads, dtype=float)))
            spread = float(df["spread"].iloc[-1])

        if last_xti <= 0 or brent <= 0:
            return EdgeSignal(
                self.strategy_id,
                symbol,
                None,
                False,
                0.0,
                rationale=f"Invalid pricing data: XTI={last_xti}, Brent={brent}",
            )

        direction = None
        confluence = 0.0
        z_score = 0.0
        rationale = f"Brent={brent:.2f}, XTI={last_xti:.2f}, Spread={spread:.2f} (Mean={mean_spread:.2f}, Std={std_spread:.2f}). "

        if std_spread > 0:
            z_score = (spread - mean_spread) / std_spread
            if z_score > z_entry:
                direction = "buy"
                confluence = 3.0
                rationale += f"Spread abnormally wide (Z={z_score:.1f} > {z_entry}). WTI is undervalued."
            elif z_score < -z_entry:
                direction = "sell"
                confluence = 3.0
                rationale += f"Spread abnormally tight (Z={z_score:.1f} < -{z_entry}). WTI is overvalued."
            else:
                rationale += f"Spread is within normal range (Z={z_score:.1f})."
        else:
            rationale += "Not enough spread volatility to compute Z-score."

        if not direction:
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=rationale)

        # Stationarity / Cointegration Pre-Condition (ADF test)
        # In trending / non-stationary regimes, spread diverges and mean-reversion fails.
        if len(historical_spreads) >= 15 and adf_max_p is not None and adf_max_p > 0:
            try:
                from statsmodels.tsa.stattools import adfuller

                try:
                    adf_res = adfuller(np.asarray(historical_spreads, dtype=float), autolag="AIC", result_object=False)
                except TypeError:
                    adf_res = adfuller(np.asarray(historical_spreads, dtype=float), autolag="AIC")
                p_val = float(adf_res[1])
                if p_val > adf_max_p:
                    return EdgeSignal(
                        self.strategy_id,
                        symbol,
                        None,
                        False,
                        0.0,
                        rationale=(
                            f"{rationale} [REJECTED: Spread non-stationary (ADF p={p_val:.3f} > {adf_max_p:.2f}). "
                            "Refusing to counter-trend in diverging/trending spread regime.]"
                        ),
                    )
                rationale += f" Stationarity confirmed (ADF p={p_val:.3f} <= {adf_max_p:.2f})."
            except Exception as adf_err:
                logger.debug(f"ADF test failed in xti_pairs (non-fatal): {adf_err}")

        # TimesFM 3.0 Multivariate Confirmation for Oil Spread
        tfm_meta = {}
        try:
            from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

            tfm_engine = TimesFMEngine(settings)
            xti_fc = await tfm_engine.get_latest_forecast(session, "XTIUSD", timeframe="H1", max_age_hours=8.0)
            if xti_fc:
                tfm_skew = float(xti_fc.get("quantile_skew", 0.0))
                tfm_meta["timesfm_skew"] = tfm_skew
                tfm_meta["timesfm_expected_range"] = xti_fc.get("expected_range")
                if direction == "buy" and tfm_skew > 0.10:
                    confluence += 1.0
                    rationale += f" TimesFM confirms WTI bullish skew (+{tfm_skew:.2f})."
                elif direction == "sell" and tfm_skew < -0.10:
                    confluence += 1.0
                    rationale += f" TimesFM confirms WTI bearish skew ({tfm_skew:.2f})."
                elif (direction == "buy" and tfm_skew < -0.30) or (direction == "sell" and tfm_skew > 0.30):
                    rationale += f" [Caution: TimesFM counter-skew ({tfm_skew:.2f})]."
        except Exception as tfm_err:
            logger.debug(f"TimesFM check failed in xti_pairs (non-fatal): {tfm_err}")

        # Calculate spread-based SL/TP for both legs (with minimum distance floor to prevent SL == Entry)
        min_sl_dist = max(0.50, float(std_spread) * 0.5)
        if direction == "buy":  # WTI undervalued, spread too wide
            # TP: spread narrows toward mean → WTI rises, Brent falls (or both converge)
            tp_spread_change = max(min_sl_dist * 1.5, abs(spread - (mean_spread + z_tp * std_spread)) / 2)
            sl_spread_change = max(min_sl_dist, abs((mean_spread + z_sl * std_spread) - spread) / 2)
            wti_tp = round(last_xti + tp_spread_change, 2)
            wti_sl = round(last_xti - sl_spread_change, 2)
            brn_tp = round(brent - tp_spread_change, 2)
            brn_sl = round(brent + sl_spread_change, 2)
            brn_direction = "sell"
        else:  # WTI overvalued, spread too tight
            # TP: spread widens toward mean → Brent rises, WTI falls (or both converge)
            tp_spread_change = max(min_sl_dist * 1.5, abs((mean_spread - z_tp * std_spread) - spread) / 2)
            sl_spread_change = max(min_sl_dist, abs(spread - (mean_spread - z_sl * std_spread)) / 2)
            wti_tp = round(last_xti - tp_spread_change, 2)
            wti_sl = round(last_xti + sl_spread_change, 2)
            brn_tp = round(brent + tp_spread_change, 2)
            brn_sl = round(brent - sl_spread_change, 2)
            brn_direction = "buy"

        # Dollar-neutral sizing multiplier for the hedge leg
        # Ensures Notional(Brent) == Notional(WTI)
        hedge_size_multiplier = round(last_xti / brent, 2)

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
            exit_style="spread_pair",
            rationale=f"Hedge leg: {brn_direction} {brent_symbol}",
            tags=["xti_pairs_readiness", "stat_arb", "hedge_leg"],
            meta={
                "is_hedge_leg": True,
                "z_score": z_score,
                "size_multiplier": hedge_size_multiplier,
            },
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
            exit_style="spread_pair",
            rationale=rationale,
            tags=["xti_pairs_readiness", "stat_arb", "primary_leg"],
            meta={
                "brent_price": brent,
                "wti_price": last_xti,
                "spread": spread,
                "z_score": z_score,
                "hedge_ratio": hedge_size_multiplier,
            },
            paired_leg=brent_leg,  # ← Links the hedge leg
        )
