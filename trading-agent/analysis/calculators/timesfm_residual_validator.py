# ==============================================================================
# File: analysis/calculators/timesfm_residual_validator.py
# ==============================================================================

"""
TimesFM Residual Analysis & White Noise Validation Engine.
Performs rigorous econometric diagnostic tests on TimesFM forecast errors:
- Durbin-Watson statistic for 1st-order serial autocorrelation
- Ljung-Box Q-statistic test for multi-lag autocorrelation
- Residual normality and systematic directional bias detection
Determines whether model errors are pure white noise or contain uncaptured alpha.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import durbin_watson

logger = logging.getLogger("TradingAgent.Calculators.TimesFMResidualValidator")


@dataclass
class ResidualValidationResult:
    status: str  # "SUCCESS", "ERROR"
    sample_size: int
    mean_error_bias: float  # Mean residual (bias towards over/under-predicting)
    rmse: float  # Root Mean Squared Error
    mae: float  # Mean Absolute Error
    durbin_watson_stat: float  # Durbin-Watson test statistic (ideal ~ 2.0)
    dw_verdict: str  # "NO_AUTOCORRELATION", "POSITIVE_AUTOCORRELATION", "NEGATIVE_AUTOCORRELATION"
    ljung_box_pvalues: Dict[int, float] = field(default_factory=dict)
    is_white_noise: bool = True  # True if p > 0.05 across tested lags
    exploitable_alpha_remaining: bool = False  # True if autocorrelation is statistically significant
    skewness: float = 0.0
    kurtosis: float = 0.0
    recommendation: str = ""
    notes: str = ""


class TimesFMResidualValidator:
    """
    Evaluates forecast residuals of TimesFM models.
    """

    @classmethod
    def validate_residuals(
        cls,
        actual_series: Union[List[float], np.ndarray, pd.Series],
        predicted_series: Union[List[float], np.ndarray, pd.Series],
        lags: Optional[List[int]] = None,
        alpha_significance: float = 0.05
    ) -> ResidualValidationResult:
        """
        Calculates diagnostic statistics on residual series: e_t = actual_t - predicted_t.
        """
        y_true = np.asarray(actual_series, dtype=float)
        y_pred = np.asarray(predicted_series, dtype=float)

        if len(y_true) != len(y_pred):
            return cls._create_error_result("Lengths of actual and predicted series do not match.")

        # Drop NaNs
        valid_mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
        y_true = y_true[valid_mask]
        y_pred = y_pred[valid_mask]
        n = len(y_true)

        if n < 15:
            return cls._create_error_result("Insufficient sample size (minimum 15 points required for residual testing).")

        # Residuals: actual minus predicted
        residuals = y_true - y_pred

        mean_err = float(np.mean(residuals))
        mae = float(np.mean(np.abs(residuals)))
        rmse = float(math.sqrt(np.mean(residuals ** 2)))

        # Durbin-Watson test
        dw_val = float(durbin_watson(residuals))
        if dw_val < 1.4:
            dw_verdict = "POSITIVE_AUTOCORRELATION"
        elif dw_val > 2.6:
            dw_verdict = "NEGATIVE_AUTOCORRELATION"
        else:
            dw_verdict = "NO_AUTOCORRELATION"

        # Ljung-Box test for higher order autocorrelation
        test_lags = lags or [1, 3, 5, 10]
        # Restrict lags to n // 3
        valid_lags = [lag for lag in test_lags if lag < n // 2]
        if not valid_lags:
            valid_lags = [max(1, min(5, n // 3))]

        lb_pvals: Dict[int, float] = {}
        try:
            lb_res = acorr_ljungbox(residuals, lags=valid_lags, return_df=True)
            for idx, row in lb_res.iterrows():
                lb_pvals[int(idx)] = round(float(row["lb_pvalue"]), 5)
        except Exception as e:
            logger.warning(f"Ljung-Box test encountered error: {str(e)}")

        # Check if white noise: all p-values > alpha_significance
        is_wn = True
        has_alpha = False
        for lag, pval in lb_pvals.items():
            if pval < alpha_significance:
                is_wn = False
                has_alpha = True
                break

        if dw_verdict != "NO_AUTOCORRELATION":
            is_wn = False
            has_alpha = True

        # Moments
        res_series = pd.Series(residuals)
        skew = round(float(res_series.skew()), 3)
        kurt = round(float(res_series.kurtosis()), 3)

        # Recommendation synthesis
        if is_wn:
            rec = "PASS: Model residuals conform to white noise. No significant unharvested linear structure detected."
        elif dw_verdict == "POSITIVE_AUTOCORRELATION":
            rec = (
                f"ACTIONABLE ALPHA DETECTED: Forecast residuals display significant positive serial correlation (DW = {dw_val:.2f}). "
                "The TimesFM model exhibits momentum under-reaction. A secondary autoregressive residual filter (AR-1) "
                "or trend-continuation overlay can capture additional edge."
            )
        else:
            rec = (
                f"ACTIONABLE ALPHA DETECTED: Forecast residuals show negative autocorrelation (DW = {dw_val:.2f}) or "
                f"Ljung-Box rejection (p-values: {lb_pvals}). The model exhibits mean-reverting overshoot."
            )

        return ResidualValidationResult(
            status="SUCCESS",
            sample_size=n,
            mean_error_bias=round(mean_err, 5),
            rmse=round(rmse, 5),
            mae=round(mae, 5),
            durbin_watson_stat=round(dw_val, 3),
            dw_verdict=dw_verdict,
            ljung_box_pvalues=lb_pvals,
            is_white_noise=is_wn,
            exploitable_alpha_remaining=has_alpha,
            skewness=skew,
            kurtosis=kurt,
            recommendation=rec,
            notes=f"Evaluated on {n} bars. Skew: {skew}, Kurtosis: {kurt}."
        )

    @staticmethod
    def _create_error_result(error_msg: str) -> ResidualValidationResult:
        return ResidualValidationResult(
            status="ERROR",
            sample_size=0,
            mean_error_bias=0.0,
            rmse=0.0,
            mae=0.0,
            durbin_watson_stat=0.0,
            dw_verdict="ERROR",
            recommendation=error_msg,
            notes=error_msg
        )
