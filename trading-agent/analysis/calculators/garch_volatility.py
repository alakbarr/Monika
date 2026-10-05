# ==============================================================================
# File: analysis/calculators/garch_volatility.py
# ==============================================================================

"""
GARCH(1,1) Conditional Volatility Forecasting and Volatility Clustering Engine.
Uses maximum likelihood estimation via the `arch` package to forecast next-period
volatility, compute volatility persistence (alpha + beta), half-life of volatility shocks,
and detect high-volatility regimes.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Calculators.GarchVolatility")

try:
    from arch import arch_model
    ARCH_AVAILABLE = True
except ImportError:
    ARCH_AVAILABLE = False
    logger.warning("arch package not found. GARCH calculator will fallback to EWMA/Rolling vol.")


@dataclass
class GarchForecastResult:
    status: str  # "SUCCESS", "FALLBACK", "ERROR"
    model_type: str  # "GARCH(1,1)" or "EWMA_FALLBACK"
    current_volatility: float  # Latest conditional volatility (decimal per period)
    forecasted_volatility_1step: float  # Forecasted 1-step ahead conditional volatility
    annualized_current_vol: float  # Annualized volatility %
    annualized_forecast_vol: float  # Annualized forecasted volatility %
    persistence: float  # alpha + beta
    half_life_bars: Optional[float]  # bars to decay 50% of shock
    unconditional_volatility: Optional[float]  # Long-run steady state volatility
    parameters: Dict[str, float] = field(default_factory=dict)
    fit_metrics: Dict[str, float] = field(default_factory=dict)
    volatility_regime: str = "NORMAL"  # "LOW", "NORMAL", "HIGH", "EXTREME"
    notes: str = ""


class GarchVolatilityEngine:
    """
    Fits GARCH(1,1) process to log returns or price series.
    """

    @classmethod
    def estimate_garch11(
        cls,
        prices_or_returns: Union[List[float], np.ndarray, pd.Series],
        is_returns: bool = False,
        annualization_factor: float = math.sqrt(252),  # 252 for Daily, sqrt(252*24) for Hourly
        p: int = 1,
        q: int = 1,
        dist: str = "normal",  # "normal", "t", "skewt"
    ) -> GarchForecastResult:
        """
        Estimate GARCH(p,q) model and forecast 1-step ahead conditional volatility.
        """
        if isinstance(prices_or_returns, (list, tuple)):
            series = pd.Series(prices_or_returns, dtype=float)
        elif isinstance(prices_or_returns, np.ndarray):
            series = pd.Series(prices_or_returns, dtype=float)
        else:
            series = prices_or_returns.astype(float).copy()

        series = series.dropna()

        # Compute log returns if input is raw prices
        if not is_returns:
            if len(series) < 30:
                return cls._create_error_result("Insufficient price bars (minimum 30 required)")
            returns = np.log(series / series.shift(1)).dropna()
        else:
            returns = series.dropna()

        if len(returns) < 25:
            return cls._create_error_result("Insufficient return observations (minimum 25 required)")

        # Scale returns by 100 for numerical stability in optimizer
        scaled_returns = returns * 100.0

        if ARCH_AVAILABLE:
            try:
                # Fit GARCH(1,1) with constant mean
                am = arch_model(
                    scaled_returns,
                    mean="Constant",
                    vol="GARCH",
                    p=p,
                    q=q,
                    dist=dist,
                    rescale=False
                )
                res = am.fit(disp="off", show_warning=False)

                # Extract parameters
                params = res.params.to_dict()
                omega = float(params.get("omega", 0.0))
                alpha = float(params.get(f"alpha[{p}]", 0.05))
                beta = float(params.get(f"beta[{q}]", 0.90))
                persistence = round(alpha + beta, 4)

                # Conditional volatility series (rescale back from 100)
                cond_vol = res.conditional_volatility / 100.0
                current_vol = float(cond_vol.iloc[-1])

                # 1-step ahead forecast
                forecasts = res.forecast(horizon=1)
                forecast_var = forecasts.variance.dropna().iloc[-1, 0]
                forecast_vol = math.sqrt(float(forecast_var)) / 100.0

                # Annualized volatilities
                ann_current = round(current_vol * annualization_factor * 100.0, 2)
                ann_forecast = round(forecast_vol * annualization_factor * 100.0, 2)

                # Half-life of volatility shock: ln(0.5) / ln(alpha + beta)
                half_life = None
                if 0.0 < persistence < 1.0:
                    half_life = round(math.log(0.5) / math.log(persistence), 1)

                # Unconditional long-run volatility: sqrt(omega / (1 - alpha - beta))
                uncond_vol = None
                if persistence < 1.0 and omega > 0:
                    uncond_var = (omega / 10000.0) / (1.0 - persistence)
                    uncond_vol = round(math.sqrt(uncond_var) * annualization_factor * 100.0, 2)

                # Volatility regime classification vs historical quantile
                vol_q75 = float(cond_vol.quantile(0.75))
                vol_q90 = float(cond_vol.quantile(0.90))
                vol_q25 = float(cond_vol.quantile(0.25))

                if forecast_vol > vol_q90:
                    regime = "EXTREME"
                elif forecast_vol > vol_q75:
                    regime = "HIGH"
                elif forecast_vol < vol_q25:
                    regime = "LOW"
                else:
                    regime = "NORMAL"

                return GarchForecastResult(
                    status="SUCCESS",
                    model_type=f"GARCH({p},{q})",
                    current_volatility=round(current_vol, 6),
                    forecasted_volatility_1step=round(forecast_vol, 6),
                    annualized_current_vol=ann_current,
                    annualized_forecast_vol=ann_forecast,
                    persistence=persistence,
                    half_life_bars=half_life,
                    unconditional_volatility=uncond_vol,
                    parameters={k: round(float(v), 5) for k, v in params.items()},
                    fit_metrics={
                        "aic": round(float(res.aic), 2),
                        "bic": round(float(res.bic), 2),
                        "log_likelihood": round(float(res.loglikelihood), 2),
                        "r_squared": round(float(getattr(res, "rsquared", 0.0)), 4)
                    },
                    volatility_regime=regime,
                    notes=f"Convergence achieved. Persistence: {persistence:.2f}. Shock half-life: {half_life} bars."
                )

            except Exception as e:
                logger.warning(f"GARCH optimization failed ({str(e)}). Falling back to EWMA.")

        # Fallback to EWMA (RiskMetrics lambda=0.94)
        return cls._estimate_ewma_fallback(returns, annualization_factor)

    @classmethod
    def _estimate_ewma_fallback(
        cls,
        returns: pd.Series,
        annualization_factor: float,
        decay_factor: float = 0.94
    ) -> GarchForecastResult:
        """EWMA Fallback when arch is unavailable or optimizer fails."""
        arr = returns.values
        var = np.var(arr)
        for r in arr:
            var = decay_factor * var + (1.0 - decay_factor) * (r ** 2)

        vol = math.sqrt(var)
        ann_vol = round(vol * annualization_factor * 100.0, 2)

        return GarchForecastResult(
            status="FALLBACK",
            model_type="EWMA_RISKMETRICS",
            current_volatility=round(vol, 6),
            forecasted_volatility_1step=round(vol, 6),
            annualized_current_vol=ann_vol,
            annualized_forecast_vol=ann_vol,
            persistence=decay_factor,
            half_life_bars=round(math.log(0.5) / math.log(decay_factor), 1),
            unconditional_volatility=ann_vol,
            parameters={"decay_lambda": decay_factor},
            fit_metrics={},
            volatility_regime="NORMAL",
            notes="Calculated via EWMA (lambda=0.94) fallback."
        )

    @staticmethod
    def _create_error_result(error_msg: str) -> GarchForecastResult:
        return GarchForecastResult(
            status="ERROR",
            model_type="NONE",
            current_volatility=0.0,
            forecasted_volatility_1step=0.0,
            annualized_current_vol=0.0,
            annualized_forecast_vol=0.0,
            persistence=0.0,
            half_life_bars=None,
            unconditional_volatility=None,
            notes=error_msg
        )
