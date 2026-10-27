# ==============================================================================
# File: application/services/technical_indicator_service.py
# Monika Technical Indicator Application Service
# ==============================================================================

"""
Technical Indicator Application Service.

Orchestrates technical indicator computation (Moving Averages, RSI, MACD,
Stochastic, Bollinger Bands, ATR, ADX, Yang-Zhang) by loading historical OHLCV
from the database, computing indicators via vectorized algorithms, and
persisting the computed time-series to the relational database.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, cast

import numpy as np
import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.primitives import clock
from monika.domain.indicators.technical import (
    TechnicalIndicatorCalculator as DomainTechnicalIndicatorCalculator,
    compute_lag1_autocorrelation,
    compute_yang_zhang_volatility,
    evaluate_workspace_indicators,
    normalize_chart_workspace_config,
)
from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator

logger = logging.getLogger("TradingAgent.Services.TechnicalIndicator")
_WARNED_INSUFFICIENT_BARS: set[str] = set()


class TechnicalIndicatorService(DomainTechnicalIndicatorCalculator):
    """
    Application Service that computes and persists technical indicators from OHLCV data.

    Usage:
        service = TechnicalIndicatorService(session, settings)
        await service.compute_and_save("XAUUSD", "H1")
    """

    def __init__(self, session: Any, settings: Optional[dict] = None):
        super().__init__(session=session, settings=settings)
        """
        Args:
            session: Async SQLAlchemy session.
            settings: trading.indicators section from settings.yaml.
        """
        self.session = session
        cfg = (settings or {}).get("trading", {}).get("indicators", {}) or (settings or {}).get("indicators", {})
        self.ma_periods: list[int] = cfg.get("ma_periods", [20, 50, 200])
        self.rsi_period: int = cfg.get("rsi_period", 14)
        self.stoch_k: int = cfg.get("stochastic_k", 14)
        self.stoch_d: int = cfg.get("stochastic_d", 3)
        self.macd_fast: int = cfg.get("macd_fast", 12)
        self.macd_slow: int = cfg.get("macd_slow", 26)
        self.macd_signal: int = cfg.get("macd_signal", 9)
        self.bb_period: int = cfg.get("bollinger_period", 20)
        self.bb_std: float = float(cfg.get("bollinger_std", 2.0))
        self.atr_period: int = cfg.get("atr_period", 14)
        self.adx_period: int = cfg.get("adx_period", 14)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compute_and_save(self, symbol: str, timeframe: str) -> int:
        """
        Menjalankan alur lengkap: load OHLCV -> hitung -> simpan.

        Returns:
            Jumlah baris indikator yang disimpan.
        """
        if not self.session:
            logger.warning(
                f"No DB session provided to TechnicalIndicatorService, cannot compute and save for {symbol}/{timeframe}"
            )
            return 0
        df = await self._load_ohlcv(symbol, timeframe)
        if df is None:
            logger.warning(f"No OHLCV data for {symbol}/{timeframe}")
            return 0

        min_bars = max(self.ma_periods) if self.ma_periods else 30

        if len(df) < min_bars:
            warn_key = f"{symbol}/{timeframe}"
            if warn_key not in _WARNED_INSUFFICIENT_BARS:
                _WARNED_INSUFFICIENT_BARS.add(warn_key)
                logger.warning(
                    f"Insufficient OHLCV bars for {symbol}/{timeframe}: "
                    f"have {len(df)}, need {min_bars}. "
                    f"{'SMA_200 requires ~200 D1 bars — wait for more history.' if timeframe == 'D1' else 'Fetch more price history.'}"
                )
            else:
                logger.debug(f"Insufficient OHLCV bars for {symbol}/{timeframe}: have {len(df)}, need {min_bars}.")
            if len(df) < 20:
                return 0

            computable_periods = [p for p in self.ma_periods if p <= len(df)]
            if not computable_periods:
                return 0

            original_periods = self.ma_periods
            self.ma_periods = computable_periods

            try:
                indicators = await asyncio.to_thread(self._compute_all, df)
                saved = await self._save(symbol, timeframe, indicators)
            finally:
                self.ma_periods = original_periods
        else:
            indicators = await asyncio.to_thread(self._compute_all, df)
            saved = await self._save(symbol, timeframe, indicators)

        # Wire OrderFlow snapshot calculation
        try:
            from monika.domain.indicators.order_flow import OrderFlowEngine

            of_engine = OrderFlowEngine(mt5_client=getattr(self, "mt5_client", None))
            of_snapshot = await of_engine.analyze_order_flow(self.session, symbol, df=df)
            bar_ts = df.index[-1] if not df.empty else clock.now()
            if isinstance(bar_ts, pd.Timestamp):
                bar_ts = bar_ts.to_pydatetime()
            if isinstance(bar_ts, datetime):
                if bar_ts.tzinfo is None:
                    bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                else:
                    bar_ts = bar_ts.astimezone(timezone.utc)
            add_res: Any = self.session.add(
                TechnicalIndicator(
                    symbol=symbol,
                    timeframe=timeframe,
                    indicator_name="ORDER_FLOW_SNAPSHOT",
                    value_json=json.dumps(of_snapshot.to_dict()),
                    timestamp=bar_ts,
                )
            )
            if inspect.isawaitable(add_res):
                await cast(Any, add_res)
            await self.session.commit()
        except Exception as of_err:
            logger.debug(f"OrderFlow snapshot save failed for {symbol}: {of_err}")

        logger.debug(f"Saved {saved} indicator rows for {symbol}/{timeframe}")
        return saved

    async def compute_all_symbols(
        self, symbols: list[str], timeframes: list[str], force: bool = False
    ) -> dict[str, int]:
        """
        Menjalankan komputasi untuk semua aset dan timeframe.
        Mendukung smart delta-check: jika timestamp indikator terbaru sudah cocok dengan
        bar OHLCV kanonikal terbaru, komputasi ulang yang memakan resource di-bypass.
        """
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}/{tf}"
                try:
                    if not force and self.session:
                        from sqlalchemy import func, select
                        from monika.infrastructure.database.models import PriceOHLCV, TechnicalIndicator

                        ts_col = func.coalesce(PriceOHLCV.canonical_timestamp, PriceOHLCV.timestamp)
                        res_p = await self.session.execute(
                            select(ts_col)
                            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == tf)
                            .order_by(ts_col.desc())
                            .limit(1)
                        )
                        latest_price_ts = res_p.scalar_one_or_none() if hasattr(res_p, "scalar_one_or_none") else None

                        res_i = await self.session.execute(
                            select(TechnicalIndicator.timestamp)
                            .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == tf)
                            .order_by(TechnicalIndicator.timestamp.desc())
                            .limit(1)
                        )
                        latest_ind_ts = res_i.scalar_one_or_none() if hasattr(res_i, "scalar_one_or_none") else None

                        if (
                            isinstance(latest_price_ts, datetime)
                            and isinstance(latest_ind_ts, datetime)
                            and latest_price_ts == latest_ind_ts
                        ):
                            logger.debug(f"Indicators for {key} up-to-date ({latest_ind_ts}), bypassing recompute")
                            results[key] = 0
                            continue

                    n = await self.compute_and_save(symbol, tf)
                    results[key] = n
                except Exception as e:
                    logger.error(f"Indicator computation failed for {key}: {e}")
                    if hasattr(self.session, "rollback"):
                        try:
                            await self.session.rollback()
                            if hasattr(self.session, "expunge_all"):
                                exp_res = self.session.expunge_all()
                                if inspect.isawaitable(exp_res):
                                    await exp_res
                        except Exception:
                            pass
                    results[key] = 0
        total_rows = sum(results.values())
        logger.info(f"Technical indicators complete: {len(results)} pairs ({total_rows} indicator rows computed)")
        return results

    # ------------------------------------------------------------------
    # Chart Workspace & Multi-TF Indicator Studio
    # ------------------------------------------------------------------

    async def compute_chart_workspace_payload(
        self,
        symbol: str,
        timeframe: str,
        count: int = 250,
        workspace_config: Optional[dict[str, Any]] = None,
        ohlcv_rows: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """
        Compute indicator workspace series, pivot points, and alignment summary.
        Normalizes workspace configuration, loads/ensures required historical bars,
        and computes all active overlays and oscillators.
        """
        cfg = normalize_chart_workspace_config(workspace_config)

        if ohlcv_rows:
            df = pd.DataFrame(ohlcv_rows)
            time_col = next((c for c in ("timestamp", "time") if c in df.columns), None)
            if time_col is not None:
                df["timestamp"] = pd.to_datetime(df[time_col], utc=True)
                df.set_index("timestamp", inplace=True)
                if not df.index.is_monotonic_increasing:
                    df.sort_index(inplace=True)
                df = df.loc[~df.index.duplicated(keep="last")]
        else:
            df = await self._load_ohlcv(symbol, timeframe)
            if (df is None or len(df) == 0) and self.session is not None:
                try:
                    from monika.application.services.market_data_service import MarketDataService

                    md_svc = getattr(self, "market_data_service", None) or MarketDataService
                    if hasattr(md_svc, "ensure_bars"):
                        await md_svc.ensure_bars(
                            symbol=symbol,
                            timeframe=timeframe,
                            count=max(count + 200, 300),
                            session=self.session,
                        )
                        df = await self._load_ohlcv(symbol, timeframe)
                except Exception as e:
                    logger.debug(f"Failed to ensure bars for {symbol}/{timeframe}: {e}")

        if df is None or len(df) == 0:
            return evaluate_workspace_indicators(pd.DataFrame(), cfg, max_bars=count)

        return await asyncio.to_thread(evaluate_workspace_indicators, df, cfg, count)

    async def compute_multi_tf_workspace_summary(
        self,
        symbol: str,
        workspace_config: Optional[dict[str, Any]] = None,
        timeframes: tuple[str, ...] = ("D1", "H4", "H1", "M15"),
    ) -> dict[str, Any]:
        """
        Compute multi-timeframe workspace alignment, merged declared figures, and confluence summary.
        Combines primary timeframe signals with higher/lower timeframe confirmation.
        """
        cfg = normalize_chart_workspace_config(workspace_config)
        primary_tf = str(cfg.get("timeframe", "H4")).upper()
        ordered_tfs = list(dict.fromkeys([primary_tf, *timeframes]))

        tf_summaries: dict[str, Any] = {}
        merged_figures: dict[str, float] = {}

        for tf in ordered_tfs:
            df = await self._load_ohlcv(symbol, tf)
            if df is not None and len(df) >= 5:
                eval_res = await asyncio.to_thread(evaluate_workspace_indicators, df, cfg, 30)
            else:
                eval_res = evaluate_workspace_indicators(pd.DataFrame(), cfg, 30)

            overall_data = eval_res.get("overall", {})
            bias_upper = str(overall_data.get("bias", "neutral")).upper()
            align_pct = overall_data.get("alignment_pct")
            if align_pct is None:
                align_pct = round(float(overall_data.get("alignment_ratio", 0.0)) * 100.0, 1)

            tf_summaries[tf] = {
                "bias": bias_upper,
                "bullish_count": overall_data.get("bullish_count", 0),
                "bearish_count": overall_data.get("bearish_count", 0),
                "neutral_count": overall_data.get("neutral_count", 0),
                "alignment_pct": float(align_pct),
                "indicators": eval_res.get("summary", {}),
                "pivot_points": eval_res.get("pivot_points"),
            }

            for k, v in eval_res.get("declared_figures", {}).items():
                merged_figures[f"{tf}_{k}"] = v
                if tf == primary_tf:
                    merged_figures[k] = v

        bullish_tfs = [tf for tf, info in tf_summaries.items() if info["bias"] == "BULLISH"]
        bearish_tfs = [tf for tf, info in tf_summaries.items() if info["bias"] == "BEARISH"]

        if len(bullish_tfs) > len(bearish_tfs):
            overall_bias = "BULLISH"
        elif len(bearish_tfs) > len(bullish_tfs):
            overall_bias = "BEARISH"
        else:
            overall_bias = tf_summaries.get(primary_tf, {}).get("bias", "NEUTRAL")

        prim_info = tf_summaries.get(primary_tf, {})
        prim_total_dir = int(prim_info.get("bullish_count", 0)) + int(prim_info.get("bearish_count", 0))
        prim_align = float(prim_info.get("alignment_pct", 0.0))
        matching_count = len(bullish_tfs if overall_bias == "BULLISH" else bearish_tfs)

        if prim_total_dir >= 3 and prim_align >= 75.0 and matching_count >= 2:
            confluence_adjustment = 2
        elif prim_total_dir >= 1 and prim_align >= 60.0:
            confluence_adjustment = 1
        else:
            confluence_adjustment = 0

        active_preset = cfg.get("active_preset") or cfg.get("preset_id", "smc_institutional")

        report_lines = [
            f"=== TECHNICAL INDICATOR WORKSPACE: {symbol.upper()} ===",
            f"Active Preset: {active_preset} | Primary TF: {primary_tf} | Overall Bias: {overall_bias} (Bullish TFs: {', '.join(bullish_tfs) or 'None'} | Bearish TFs: {', '.join(bearish_tfs) or 'None'})",
            f"Confluence Adjustment: {confluence_adjustment:+d}",
            "",
            f"[Primary TF ({primary_tf}) Active Indicators]",
        ]

        prim_indicators = prim_info.get("indicators", {})
        if prim_indicators:
            for ind_k, ind_v in prim_indicators.items():
                sig = str(ind_v.get("signal", "neutral")).upper()
                latest = ind_v.get("latest")
                details = ind_v.get("details", "")
                report_lines.append(f"- {ind_k}: {latest} | {sig} | {details}")
        else:
            report_lines.append("- No active indicators evaluated")

        report_lines.append("")
        report_lines.append("[Multi-TF Matrix]")
        for tf in ordered_tfs:
            info = tf_summaries.get(tf, {})
            b_cnt = info.get("bullish_count", 0)
            bear_cnt = info.get("bearish_count", 0)
            align = float(info.get("alignment_pct", 0.0))
            t_bias = info.get("bias", "NEUTRAL")

            t_inds = info.get("indicators", {})
            snippets = []
            for candidate in ("RSI_14", "MACD", "Supertrend", "ADX_14"):
                if candidate in t_inds:
                    cand_data = t_inds[candidate]
                    snippets.append(f"{candidate}: {cand_data.get('latest')} ({cand_data.get('signal')})")
            highlight_str = f" | {', '.join(snippets)}" if snippets else ""
            report_lines.append(
                f"- {tf}: {t_bias} (Bull: {b_cnt}, Bear: {bear_cnt}, Align: {align:.1f}%){highlight_str}"
            )

        formatted_report = "\n".join(report_lines)

        return {
            "symbol": symbol.upper(),
            "primary_timeframe": primary_tf,
            "vision_sync_enabled": bool(cfg.get("vision_sync_enabled", True)),
            "active_preset": active_preset,
            "workspace_config": cfg,
            "timeframes": tf_summaries,
            "overall_bias": overall_bias,
            "bullish_tfs": bullish_tfs,
            "bearish_tfs": bearish_tfs,
            "confluence_adjustment": confluence_adjustment,
            "declared_figures": merged_figures,
            "formatted_report": formatted_report,
        }

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    async def _load_ohlcv(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Memuat OHLCV secara descending, lalu dibalik menjadi kronologis untuk kalkulasi."""
        fetch_limit = 1000 if timeframe.upper() in ("D1", "H4") else 500
        if not self.session:
            return None

        result = await self.session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == timeframe)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(fetch_limit)
        )
        rows = result.scalars().all()
        if not rows:
            logger.warning(f"No OHLCV data found for {symbol}/{timeframe}")
            return None

        rows = list(reversed(rows))

        def _get_ts(r: Any) -> Any:
            c = getattr(r, "canonical_timestamp", None)
            return c if isinstance(c, datetime) else getattr(r, "timestamp", None)

        df = pd.DataFrame(
            {
                "timestamp": [_get_ts(r) for r in rows],
                "open": [r.open for r in rows],
                "high": [r.high for r in rows],
                "low": [r.low for r in rows],
                "close": [r.close for r in rows],
                "volume": [r.volume for r in rows],
            }
        )
        df.set_index("timestamp", inplace=True)
        df.index = pd.to_datetime(df.index, utc=True)

        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)

        df = df.loc[~df.index.duplicated(keep="last")]

        if timeframe.upper() == "D1" and len(df) > 1:
            df.index = pd.to_datetime([pd.Timestamp(t).strftime("%Y-%m-%d") for t in df.index], utc=True)
            df = df.loc[~df.index.duplicated(keep="last")]

        tf_freq_map = {
            "M1": "1min",
            "M5": "5min",
            "M15": "15min",
            "M30": "30min",
            "H1": "1h",
            "H4": "4h",
            "D1": "1D",
        }
        freq = tf_freq_map.get(timeframe.upper())
        if freq and len(df) > 1:
            try:
                deduped: pd.DataFrame = df.loc[~df.index.duplicated(keep="last")]
                if freq == "1D":
                    resampled = deduped.resample(freq).asfreq()
                else:
                    resampled = deduped.resample(freq, origin="epoch").asfreq()
                if not resampled["close"].isna().all():
                    is_crypto = any(c in symbol.upper() for c in ("BTC", "ETH", "SOL"))
                    if not is_crypto:
                        idx: Any = pd.DatetimeIndex(resampled.index)
                        is_weekend = (
                            (idx.dayofweek == 5)
                            | ((idx.dayofweek == 6) & (idx.hour < 21))
                            | ((idx.dayofweek == 4) & (idx.hour >= 22))
                        )
                        resampled = resampled[~is_weekend]
                    resampled["close"] = resampled["close"].ffill()
                    resampled["open"] = resampled["open"].fillna(resampled["close"])
                    resampled["high"] = resampled["high"].fillna(resampled["close"])
                    resampled["low"] = resampled["low"].fillna(resampled["close"])
                    resampled["volume"] = resampled["volume"].fillna(0.0)
                    if not resampled.empty and not resampled["close"].isna().all():
                        df = resampled
                    else:
                        df = deduped
                else:
                    df = deduped
            except Exception as e:
                logger.debug(f"Resampling error for {symbol}/{timeframe} (fallback to raw): {e}")

        if df is not None and not df.empty:
            df.index = pd.to_datetime(df.index, utc=True)

        return cast(Optional[pd.DataFrame], df)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _save(
        self,
        symbol: str,
        timeframe: str,
        indicators: dict[datetime, list[dict]],
    ) -> int:
        """
        Menyimpan indikator (upsert per timestamp) agar data sinkron
        dengan bar/candle terbaru.
        """
        # Defensive normalization: ensure all timestamps are timezone-aware UTC datetime objects
        clean_indicators: dict[datetime, list[dict]] = {}
        for raw_ts, entries in indicators.items():
            if raw_ts is None or pd.isna(raw_ts):
                continue
            if isinstance(raw_ts, pd.Timestamp):
                ts_pydt = raw_ts.to_pydatetime()
            elif isinstance(raw_ts, datetime):
                ts_pydt = raw_ts
            else:
                parsed_ts = pd.Timestamp(raw_ts)
                if pd.isna(parsed_ts):
                    continue
                ts_pydt = parsed_ts.to_pydatetime()

            if not isinstance(ts_pydt, datetime):
                continue

            if ts_pydt.tzinfo is None:
                ts_final = ts_pydt.replace(tzinfo=timezone.utc)
            else:
                ts_final = ts_pydt.astimezone(timezone.utc)

            clean_indicators[ts_final] = entries

        timestamps = list(clean_indicators.keys())
        if not timestamps:
            return 0

        # Simpan maksimal 100 bar terkini untuk efisiensi runtime
        if len(timestamps) > 100:
            timestamps = timestamps[-100:]

        from sqlalchemy import delete

        if not self.session:
            return 0

        await self.session.execute(
            delete(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.timestamp.in_(timestamps))
        )

        saved = 0
        for ts in timestamps:
            for entry in clean_indicators.get(ts, []):
                val_json = entry.get("value_json")
                if val_json is None and "value" in entry:
                    val_json = json.dumps(entry["value"])
                self.session.add(
                    TechnicalIndicator(
                        symbol=symbol,
                        timeframe=timeframe,
                        timestamp=ts,
                        indicator_name=entry["name"],
                        value_json=str(val_json or ""),
                    )
                )
                saved += 1

        await self.session.commit()
        return saved

    # ------------------------------------------------------------------
    # Read helpers (used by analysis stage)
    # ------------------------------------------------------------------

    async def get_latest(self, symbol: str, timeframe: str, indicator_name: str) -> Optional[dict]:
        """Mengambil metrik indikator terbaru untuk suatu symbol/timeframe."""
        if not self.session:
            return None

        result = await self.session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.indicator_name == indicator_name)
            .where(TechnicalIndicator.timestamp <= clock.now())
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {"timestamp": row.timestamp, "value": json.loads(row.value_json)}

    async def get_snapshot(
        self, symbol: str, timeframe: str, series_depth: int = 15, as_of: Optional[datetime] = None
    ) -> dict:
        """
        Mengambil semua nilai indikator pada timestamp terkini dengan konteks delta, arah,
        dan histori pergerakan N-bar (series_depth) untuk indikator kunci (RSI, MACD, Stoch, ADX, dsb).
        Berguna untuk analisis trend, cross, dan divergence oleh specialist LLM.
        """
        mock_hook = await super().get_snapshot(symbol, timeframe, series_depth, as_of)
        if mock_hook:
            return mock_hook

        if not self.session:
            return {}

        fetch_limit = max(2, min(series_depth, 30))
        cutoff = as_of if as_of is not None else clock.now()
        recent_ts_result = await self.session.execute(
            select(TechnicalIndicator.timestamp)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == timeframe)
            .where(TechnicalIndicator.timestamp <= cutoff)
            .group_by(TechnicalIndicator.timestamp)
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(fetch_limit)
        )
        recent_ts = recent_ts_result.scalars().all()
        if not recent_ts:
            return {}

        latest_ts = recent_ts[0]
        prev_ts = recent_ts[1] if len(recent_ts) > 1 else None

        rows_by_indicator: dict[str, list[Any]] = {}
        if len(recent_ts) <= 2:
            result_latest = await self.session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.timestamp == latest_ts)
            )
            latest_rows = result_latest.scalars().all()
            prev_map: dict[str, tuple[Any, Any]] = {}
            if prev_ts:
                result_prev = await self.session.execute(
                    select(TechnicalIndicator)
                    .where(TechnicalIndicator.symbol == symbol)
                    .where(TechnicalIndicator.timeframe == timeframe)
                    .where(TechnicalIndicator.timestamp == prev_ts)
                )
                prev_map = {r.indicator_name: (r, json.loads(r.value_json)) for r in result_prev.scalars().all()}

            for r in latest_rows:
                pair = [r]
                if r.indicator_name in prev_map:
                    pair.insert(0, prev_map[r.indicator_name][0])
                rows_by_indicator[r.indicator_name] = pair
        else:
            result_rows = await self.session.execute(
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == timeframe)
                .where(TechnicalIndicator.timestamp.in_(recent_ts))
                .order_by(TechnicalIndicator.timestamp.asc())
            )
            all_rows = result_rows.scalars().all()
            for r in all_rows:
                rows_by_indicator.setdefault(r.indicator_name, []).append(r)

        def _extract_scalar(val: Any) -> Optional[float]:
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                for k in ("rsi", "histogram", "macd", "adx", "k", "pct_b", "atr", "value"):
                    if k in val and isinstance(val[k], (int, float)):
                        return float(val[k])
            return None

        KEY_SERIES_INDICATORS = {
            "RSI_14",
            "MACD_12_26_9",
            "MACD",
            "STOCH_14_3",
            "STOCH",
            "ADX_14",
            "ADX",
            "EMA_20",
            "EMA_50",
            "EMA_200",
            "SMA_20",
            "SMA_50",
            "BB_20_2",
            "AC1_20",
            "YANG_ZHANG_VOL_20",
        }

        snapshot = {}
        for ind_name, rows in rows_by_indicator.items():
            latest_row = next((r for r in reversed(rows) if r.timestamp == latest_ts), rows[-1])
            prev_row = next((r for r in reversed(rows) if prev_ts and r.timestamp == prev_ts), None)

            curr_val = json.loads(latest_row.value_json)
            prev_val = json.loads(prev_row.value_json) if prev_row else None
            curr_num = _extract_scalar(curr_val)
            prev_num = _extract_scalar(prev_val) if prev_val is not None else None

            delta = None
            direction = "flat"
            if curr_num is not None and prev_num is not None:
                delta = round(curr_num - prev_num, 5)
                threshold = 0.0001 if abs(curr_num) < 10 else 0.01
                if delta > threshold:
                    direction = "rising"
                elif delta < -threshold:
                    direction = "falling"

            entry: dict[str, Any] = {
                "timestamp": latest_row.timestamp,
                "value": curr_val,
                "prev": prev_val,
                "delta": delta,
                "direction": direction,
            }

            if ind_name in KEY_SERIES_INDICATORS and len(rows) > 1:
                series_vals = []
                for r in rows:
                    parsed = json.loads(r.value_json)
                    if isinstance(parsed, dict) and "histogram" in parsed:
                        series_vals.append(round(float(parsed.get("histogram", 0)), 5))
                    elif isinstance(parsed, dict) and "k" in parsed and "d" in parsed:
                        series_vals.append(
                            {
                                "k": round(float(parsed.get("k", 0)), 2),
                                "d": round(float(parsed.get("d", 0)), 2),
                            }
                        )
                    elif isinstance(parsed, dict) and "adx" in parsed:
                        series_vals.append(round(float(parsed.get("adx", 0)), 2))
                    else:
                        num = _extract_scalar(parsed)
                        if num is not None:
                            series_vals.append(round(num, 4))
                if series_vals:
                    entry["series"] = series_vals

            snapshot[ind_name] = entry

        return snapshot


# Aliases for backward compatibility
TechnicalIndicatorCalculator = TechnicalIndicatorService

from monika.domain.indicators.technical import (
    TechnicalIndicatorCalculator as _DomainTechnicalIndicatorCalculator,
)

_DomainTechnicalIndicatorCalculator.register_service_class(TechnicalIndicatorService)
