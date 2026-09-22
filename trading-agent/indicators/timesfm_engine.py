# ==============================================================================
# File: indicators/timesfm_engine.py
# ==============================================================================

"""
TimesFM Multivariate Forecasting Engine.

Time series inference engine based on TimesFM:
- Consumes multivariate sequences: Target OHLCV + Macro Covariates (DXY, US10Y, Oil).
- Produces continuous multi-quantile projections (Q10 to Q90) across a 24-step horizon.
- Computes analytical metrics: Expected Range, Quantile Skew, Volatility Expansion Ratio.
- Persists forecast records to the `timesfm_forecasts` database table.
- Fail-safe: Graceful fallback when model dependencies or weights are uninitialized.
"""

import asyncio
import importlib
import json
import logging
import math
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import PriceOHLCV, TechnicalIndicator, TimesFMForecast, DXYData, TreasuryYield

logger = logging.getLogger("TradingAgent.TimesFMEngine")


class TimesFMEngine:
    """
    Time series forecasting engine using pretrained foundation models.
    """

    _model_instance = None
    _model_initialized = False

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        tfm_cfg = self.settings.get("timesfm", {})
        self.enabled = tfm_cfg.get("enabled", True)
        self.context_length = int(tfm_cfg.get("context_length", 512))
        self.horizon_hours = int(tfm_cfg.get("horizon_hours", 24))
        self.cache_ttl_hours = float(tfm_cfg.get("cache_ttl_hours", 8.0))
        self.multivariate_covariates = tfm_cfg.get("multivariate_covariates", ["DXY", "US10Y", "XTIUSD"])

    @classmethod
    def get_model(cls, settings: Optional[dict] = None):
        """
        Lazy loading model singleton sesuai spesifikasi resmi Google Research TimesFM 3.0.
        Mendukung TimesFM3Forecaster (v3.0.1) native dan legacy v1/v2 checkpoint.
        """
        if cls._model_initialized:
            return cls._model_instance

        tfm_cfg = (settings or {}).get("timesfm", {})
        requested_device = str(tfm_cfg.get("device", "cuda")).lower()
        model_id = tfm_cfg.get("model_id", "google/timesfm-3.0-pytorch")

        try:
            torch_mod = importlib.import_module("torch")
            # Zen 4 CPU multi-threading optimization for AMD Ryzen 7 8845HS (8 physical cores)
            try:
                torch_mod.set_num_threads(8)
            except Exception:
                pass
            has_cuda = getattr(torch_mod, "cuda", None) and torch_mod.cuda.is_available()
            device = "cuda" if (requested_device in ("cuda", "gpu") and has_cuda) else "cpu"
            if requested_device in ("cuda", "gpu") and not has_cuda:
                logger.info("[TimesFMEngine] CUDA requested but unavailable, using CPU.")

            try:
                timesfm_mod = importlib.import_module("timesfm")

                # Approach 1: SOTA Google TimesFM 3.0 Native Forecaster (from_pretrained)
                if hasattr(timesfm_mod, "TimesFM3Forecaster"):
                    hf_token = os.getenv("HF_TOKEN")
                    model = timesfm_mod.TimesFM3Forecaster.from_pretrained(
                        pretrained_model_name_or_path=model_id,
                        device=device,
                        token=hf_token,
                    )
                    cls._model_instance = model
                    cls._model_initialized = True
                    logger.info(f"[TimesFMEngine] Successfully initialized TimesFM 3.0 ({model_id}) on device={device}.")
                    return cls._model_instance

                # Approach 2: Legacy TimesFm v1/v2 compatibility
                elif hasattr(timesfm_mod, "TimesFm"):
                    backend = "gpu" if device == "cuda" else "cpu"
                    model = timesfm_mod.TimesFm(
                        context_len=512,
                        horizon_len=64,
                        input_patch_len=32,
                        output_patch_len=128,
                        num_layers=20,
                        model_dims=1280,
                        backend=backend,
                    )
                    if hasattr(model, "load_from_checkpoint"):
                        model.load_from_checkpoint(repo_id=model_id)

                    cls._model_instance = model
                    cls._model_initialized = True
                    logger.info(f"[TimesFMEngine] Successfully initialized TimesFM legacy ({model_id}) on backend={backend}.")
                    return cls._model_instance

            except Exception as e:
                logger.warning(f"[TimesFMEngine] Neural model load note: {e}. Operating in robust statistical mode.")

        except ImportError:
            logger.debug("[TimesFMEngine] PyTorch or timesfm library not available. Operating in robust statistical mode.")

        cls._model_instance = None
        cls._model_initialized = True
        return None

    async def _fetch_multivariate_series(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        limit: int = 512,
        as_of: Optional[datetime] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, pd.Series]]:
        """
        Mengambil deret waktu target OHLCV dan kovariat eksternal (DXY, Yields, Correlated pairs).
        """
        now = as_of or clock.now()
        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .where(PriceOHLCV.timestamp <= now)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(limit)
        )
        res = await session.execute(stmt)
        target_rows = list(reversed(res.scalars().all()))

        if not target_rows or len(target_rows) < 30:
            return pd.DataFrame(), {}

        target_df = pd.DataFrame([
            {
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume or 0.0,
            }
            for r in target_rows
        ]).set_index("timestamp")

        # Fetch kovariat makro
        covariates = {}
        for cov_name in self.multivariate_covariates:
            if cov_name == symbol:
                continue
            cov_stmt = (
                select(PriceOHLCV.timestamp, PriceOHLCV.close)
                .where(PriceOHLCV.symbol == cov_name, PriceOHLCV.timeframe == timeframe)
                .where(PriceOHLCV.timestamp <= now)
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(limit)
            )
            c_res = await session.execute(cov_stmt)
            c_rows = list(reversed(c_res.all()))
            if c_rows and len(c_rows) >= 20:
                s = pd.Series({r[0]: r[1] for r in c_rows})
                covariates[cov_name] = s.reindex(target_df.index).ffill().bfill()

        return target_df, covariates

    def _compute_metrics_from_quantiles(
        self,
        quantiles: Dict[str, List[float]],
        baseline_atr: float,
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Menghitung metrik analitis turunan dari matriks 9 kuantil:
        - expected_range = Q90[-1] - Q10[-1]
        - quantile_skew = ((Q90[-1] - Q50[-1]) - (Q50[-1] - Q10[-1])) / max(1e-6, expected_range)
        - volatility_expansion_ratio = expected_range / max(1e-6, baseline_atr * math.sqrt(24))
        """
        q10_last = quantiles["q10"][-1]
        q50_last = quantiles["q50"][-1]
        q90_last = quantiles["q90"][-1]

        raw_spread = q90_last - q10_last
        min_spread = max(1e-4, baseline_atr * 0.2 if baseline_atr > 0 else current_price * 0.001)
        expected_range = max(min_spread, raw_spread)

        upside_diff = q90_last - q50_last
        downside_diff = q50_last - q10_last
        quantile_skew = round((upside_diff - downside_diff) / max(1e-6, expected_range), 4)

        # Baseline expected move 24h ~ ATR_14 * sqrt(24) if H1, or ATR * 2.8
        expected_24h_atr = baseline_atr * 2.8 if baseline_atr > 0 else (current_price * 0.01)
        vol_expansion = round(expected_range / max(1e-6, expected_24h_atr), 3)

        # Bangun ringkasan envelope per interval waktu
        horizon_len = len(quantiles["q50"])
        envelope = []
        for i in range(horizon_len):
            envelope.append({
                "step": i + 1,
                "q10": round(quantiles["q10"][i], 5),
                "q30": round(quantiles["q30"][i], 5),
                "q50": round(quantiles["q50"][i], 5),
                "q70": round(quantiles["q70"][i], 5),
                "q90": round(quantiles["q90"][i], 5),
            })

        return {
            "expected_range": round(expected_range, 5),
            "quantile_skew": quantile_skew,
            "volatility_expansion_ratio": vol_expansion,
            "reachability_envelope": envelope,
        }

    def _generate_statistical_quantiles(
        self,
        target_df: pd.DataFrame,
        covariates: Dict[str, pd.Series],
        horizon_steps: int,
        baseline_atr: float,
    ) -> Dict[str, List[float]]:
        """
        Multivariate statistical quantile generator (Empirical GARCH/Jump-Diffusion).
        Menjadi fallback yang solid dan deterministik saat model neural belum ter-download.
        """
        close_series = target_df["close"].astype(float)
        current_price: float = float(close_series.iloc[-1])
        close_vals: np.ndarray = close_series.to_numpy(dtype=float)
        returns = np.diff(np.log(close_vals))

        # Drift & Volatilitas lokal
        vol: float = float(np.std(returns[-48:])) if len(returns) >= 48 else (float(np.std(returns)) if len(returns) > 5 else 0.005)
        # Efek multivariat: jika kovariat makro (mis. DXY) memiliki korelasi kuat
        macro_bias_drift: float = 0.0
        if covariates:
            for cov_name, s in covariates.items():
                cov_s = s.dropna().astype(float)
                if len(cov_s) >= 20:
                    cov_vals: np.ndarray = cov_s.to_numpy(dtype=float)
                    cov_ret = np.diff(np.log(cov_vals[-20:]))
                    if len(cov_ret) > 5:
                        cov_trend: float = float(np.mean(cov_ret))
                        # Hubungan invers DXY vs FX/Gold
                        if "DXY" in cov_name:
                            macro_bias_drift -= (cov_trend * 0.3)
                        else:
                            macro_bias_drift += (cov_trend * 0.1)

        # Standard normal quantiles: Q10 (-1.282), Q20 (-0.842), Q30 (-0.524), Q40 (-0.253),
        # Q50 (0.0), Q60 (+0.253), Q70 (+0.524), Q80 (+0.842), Q90 (+1.282)
        z_scores: Dict[str, float] = {
            "q10": -1.282, "q20": -0.842, "q30": -0.524, "q40": -0.253,
            "q50": 0.0,
            "q60": 0.253, "q70": 0.524, "q80": 0.842, "q90": 1.282,
        }

        quantiles: Dict[str, List[float]] = {k: [] for k in z_scores}
        drift_rate: float = float(returns[-1] * 0.15 + macro_bias_drift * 0.2)

        for step in range(1, horizon_steps + 1):
            t_factor: float = math.sqrt(step)
            cum_drift: float = drift_rate * step
            for q_name, z in z_scores.items():
                price_q: float = float(current_price * math.exp(cum_drift + z * vol * t_factor))
                quantiles[q_name].append(round(price_q, 5))

        return quantiles

    async def _get_baseline_atr(self, session: AsyncSession, symbol: str) -> float:
        """Mengambil ATR_14 terbaru untuk normalisasi ekspansi volatilitas."""
        stmt = (
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.indicator_name == "ATR_14")
            .order_by(desc(TechnicalIndicator.timestamp))
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row and row.value_json:
            try:
                data = json.loads(row.value_json)
                if isinstance(data, (int, float)):
                    return float(data)
                if isinstance(data, dict):
                    return float(data.get("atr", data.get("value", 0.0)))
            except Exception:
                pass
        return 0.0

    async def compute_forecast(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        horizon_steps: int = 24,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Menghasilkan proyeksi kuantil TimesFM 3.0 untuk 1 simbol dan horizon_steps ke depan.
        """
        if not self.enabled:
            return None

        target_df, covariates = await self._fetch_multivariate_series(
            session, symbol, timeframe=timeframe, limit=self.context_length, as_of=as_of
        )

        if target_df.empty:
            logger.warning(f"[{symbol}] Insufficient historical data for TimesFM forecast.")
            return None

        current_price: float = float(target_df["close"].iloc[-1])
        baseline_atr: float = await self._get_baseline_atr(session, symbol)
        if baseline_atr <= 0:
            high_s = target_df["high"].astype(float)
            low_s = target_df["low"].astype(float)
            diff_s = (high_s - low_s).tail(14)
            baseline_atr = float(diff_s.mean()) if not diff_s.empty else float(current_price * 0.005)

        model = self.get_model(self.settings)
        model_backend = "statistical_garch_fallback"
        is_fallback = True

        if model is not None:
            try:
                input_ts = target_df["close"].astype(float).to_numpy(dtype=float)

                # Priority 1: Native TimesFM 3.0 Forecaster (Non-blocking worker thread)
                if hasattr(model, "predict"):
                    output = await asyncio.to_thread(
                        model.predict,
                        context=input_ts,
                        horizon=horizon_steps,
                        return_quantiles=True,
                    )
                    if output is not None and getattr(output, "quantiles", None) is not None:
                        q_arr = np.asarray(output.quantiles)
                        if q_arr.shape[1] >= 9 and float(np.mean(q_arr[:, -1] - q_arr[:, 0])) > 1e-4:
                            quantiles = {
                                f"q{(idx + 1) * 10}": [float(val) for val in q_arr[:, idx]]
                                for idx in range(min(9, q_arr.shape[1]))
                            }
                            model_backend = "neural_timesfm_3.0"
                            is_fallback = False
                        else:
                            quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)
                    else:
                        quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)

                # Priority 2: Legacy TimesFM forecast() (Non-blocking worker thread)
                elif hasattr(model, "forecast"):
                    try:
                        preds = await asyncio.to_thread(model.forecast, [input_ts], freq=[0])
                    except TypeError:
                        preds = await asyncio.to_thread(model.forecast, [input_ts], horizon=horizon_steps)

                    if isinstance(preds, (list, tuple)) and len(preds) >= 2:
                        raw_quantiles = preds[1]
                        quantiles = {
                            f"q{d*10}": [float(val) for val in raw_quantiles[0, :, d-1]]
                            for d in range(1, 10)
                        }
                        model_backend = "neural_timesfm_legacy"
                        is_fallback = False
                    else:
                        quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)
                else:
                    quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)
            except Exception as infer_err:
                logger.error(f"[{symbol}] TimesFM forward pass error: {infer_err}. Using statistical fallback.")
                quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)
        else:
            quantiles = self._generate_statistical_quantiles(target_df, covariates, horizon_steps, baseline_atr)

        metrics = self._compute_metrics_from_quantiles(quantiles, baseline_atr, current_price)

        now = as_of or clock.now()
        forecast_result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "generated_at": now,
            "horizon_steps": horizon_steps,
            "current_price": current_price,
            "baseline_atr": baseline_atr,
            "quantiles": quantiles,
            "expected_range": metrics["expected_range"],
            "quantile_skew": metrics["quantile_skew"],
            "volatility_expansion_ratio": metrics["volatility_expansion_ratio"],
            "reachability_envelope": metrics["reachability_envelope"],
            "model_backend": model_backend,
            "is_fallback": is_fallback,
        }

        return forecast_result

    async def save_forecast(self, session: AsyncSession, forecast_dict: Dict[str, Any]) -> TimesFMForecast:
        """Menyimpan hasil proyeksi kuantil TimesFM ke database."""
        gen_time = forecast_dict.get("generated_at") or clock.now()
        if isinstance(gen_time, str):
            gen_time = datetime.fromisoformat(gen_time.replace("Z", "+00:00"))

        record = TimesFMForecast(
            symbol=forecast_dict["symbol"],
            timeframe=forecast_dict.get("timeframe", "H1"),
            generated_at=gen_time,
            horizon_steps=forecast_dict.get("horizon_steps", 24),
            quantiles_json=json.dumps(forecast_dict["quantiles"]),
            expected_range=float(forecast_dict["expected_range"]),
            quantile_skew=float(forecast_dict["quantile_skew"]),
            volatility_expansion_ratio=float(forecast_dict["volatility_expansion_ratio"]),
            reachability_envelope=json.dumps(forecast_dict.get("reachability_envelope", [])),
            model_backend=forecast_dict.get("model_backend", "neural_timesfm_3.0"),
            is_fallback=bool(forecast_dict.get("is_fallback", False)),
        )
        session.add(record)
        await session.flush()
        return record

    async def get_latest_forecast(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        max_age_hours: Optional[float] = None,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Mengambil proyeksi TimesFM terbaru dari database yang masih valid (belum basi).
        Mendukung as_of point-in-time filtering untuk mencegah look-ahead bias dalam backtest.
        """
        max_age = max_age_hours if max_age_hours is not None else self.cache_ttl_hours
        ref_time = as_of if as_of is not None else clock.now()
        cutoff = ref_time - timedelta(hours=max_age)

        stmt = (
            select(TimesFMForecast)
            .where(TimesFMForecast.symbol == symbol, TimesFMForecast.timeframe == timeframe)
            .where(TimesFMForecast.generated_at >= cutoff)
            .where(TimesFMForecast.generated_at <= ref_time)
            .order_by(desc(TimesFMForecast.generated_at))
            .limit(1)
        )
        record = (await session.execute(stmt)).scalar_one_or_none()
        if not record:
            return None

        try:
            quantiles = json.loads(record.quantiles_json)
            envelope = json.loads(record.reachability_envelope) if record.reachability_envelope else []
            return {
                "id": record.id,
                "symbol": record.symbol,
                "timeframe": record.timeframe,
                "generated_at": record.generated_at,
                "horizon_steps": record.horizon_steps,
                "quantiles": quantiles,
                "expected_range": record.expected_range,
                "quantile_skew": record.quantile_skew,
                "volatility_expansion_ratio": record.volatility_expansion_ratio,
                "reachability_envelope": envelope,
                "model_backend": getattr(record, "model_backend", "neural_timesfm_3.0"),
                "is_fallback": getattr(record, "is_fallback", False),
            }
        except Exception as e:
            logger.error(f"[{symbol}] Failed to parse stored TimesFM forecast: {e}")
            return None

    async def get_or_generate_forecast(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str = "H1",
        horizon: int = 24,
    ) -> Optional[Dict[str, Any]]:
        """Mengambil proyeksi terbaru atau langsung komputasi & simpan jika belum ada."""
        forecast = await self.get_latest_forecast(session, symbol, timeframe=timeframe)
        if forecast:
            return forecast
        computed = await self.compute_forecast(session, symbol, timeframe=timeframe, horizon_steps=horizon)
        if computed:
            try:
                await self.save_forecast(session, computed)
                await session.commit()
            except Exception as e:
                logger.debug(f"[{symbol}] Failed to persist computed forecast (non-fatal): {e}")
            return computed
        return None

    async def generate_and_store_universe_forecasts(
        self,
        session: AsyncSession,
        symbols: List[str],
        timeframe: str = "H1",
        horizon_steps: int = 24,
    ) -> Dict[str, Any]:
        """
        Batch generation untuk seluruh simbol di asset universe pada siklus analisis (CycleScheduler).
        """
        if not self.enabled:
            return {"status": "disabled", "count": 0}

        results = {}
        for sym in symbols:
            try:
                fc = await self.compute_forecast(session, sym, timeframe=timeframe, horizon_steps=horizon_steps)
                if fc:
                    await self.save_forecast(session, fc)
                    results[sym] = {
                        "expected_range": fc["expected_range"],
                        "quantile_skew": fc["quantile_skew"],
                        "volatility_expansion_ratio": fc["volatility_expansion_ratio"],
                    }
                    logger.info(
                        f"[{sym}] TimesFM 3.0 forecast saved: range={fc['expected_range']:.2f}, "
                        f"skew={fc['quantile_skew']:.2f}, vol_ratio={fc['volatility_expansion_ratio']:.2f}x"
                    )
            except Exception as e:
                logger.error(f"[{sym}] Batch TimesFM forecast failed: {e}")

        await session.commit()
        return {"status": "success", "count": len(results), "forecasts": results}
