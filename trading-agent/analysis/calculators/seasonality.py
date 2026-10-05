# ==============================================================================
# File: analysis/calculators/seasonality.py
# ==============================================================================

"""
Seasonality & Calendar Tendency Calculator.
Computes:
1. Monthly seasonality (average return, win rate % positive months, sample size)
2. Day-of-week seasonality (Monday through Friday returns, volatility, tendencies)
3. Hourly session seasonality
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("TradingAgent.Calculators.Seasonality")

MONTH_NAMES = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


class SeasonalityCalculator:
    """Calculates historical calendar seasonal tendencies for any asset."""

    @staticmethod
    def compute_monthly_seasonality(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates average return and win rate for each month of the year.
        Expects df with DateTimeIndex or 'timestamp'/'time' column, and 'close'.
        """
        if df is None or len(df) < 30:
            return {"error": "Insufficient data for seasonality (need >= 30 bars)"}

        df = df.copy()
        if "timestamp" in df.columns:
            df["dt"] = pd.to_datetime(df["timestamp"])
        elif "time" in df.columns:
            df["dt"] = pd.to_datetime(df["time"])
        elif isinstance(df.index, pd.DatetimeIndex):
            df["dt"] = df.index
        else:
            return {"error": "No datetime column found"}

        df = df.sort_values("dt").reset_index(drop=True)
        df["month"] = df["dt"].dt.month
        df["year"] = df["dt"].dt.year
        df["pct_change"] = df["close"].pct_change() * 100.0

        # Resample to monthly returns to avoid daily noise
        monthly_df = df.set_index("dt")["close"].resample("ME").last().pct_change() * 100.0
        monthly_df = monthly_df.dropna()

        if len(monthly_df) == 0:
            return {"error": "Insufficient history for monthly aggregation"}

        monthly_returns = pd.DataFrame({
            "return": monthly_df,
            "month": monthly_df.index.month,
            "year": monthly_df.index.year,
        })

        monthly_summary = {}
        for m in range(1, 13):
            sub = monthly_returns[monthly_returns["month"] == m]
            count = len(sub)
            if count > 0:
                avg_ret = float(sub["return"].mean())
                pos_count = int((sub["return"] > 0).sum())
                win_rate = (pos_count / count) * 100.0
                monthly_summary[MONTH_NAMES[m]] = {
                    "month_number": m,
                    "avg_return_pct": round(avg_ret, 2),
                    "win_rate_pct": round(win_rate, 1),
                    "positive_years": pos_count,
                    "total_years": count,
                    "tendency": "BULLISH" if avg_ret > 0.5 and win_rate >= 55.0 else ("BEARISH" if avg_ret < -0.5 and win_rate <= 45.0 else "NEUTRAL"),
                }
            else:
                monthly_summary[MONTH_NAMES[m]] = {
                    "month_number": m,
                    "avg_return_pct": 0.0,
                    "win_rate_pct": 0.0,
                    "total_years": 0,
                    "tendency": "NO_DATA",
                }

        return {
            "monthly_seasonality": monthly_summary,
            "years_covered": int(monthly_returns["year"].nunique()),
            "status": "success",
        }

    @staticmethod
    def compute_day_of_week_seasonality(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates average daily return, volatility, and win rate for Monday - Friday.
        """
        if df is None or len(df) < 20:
            return {"error": "Insufficient data"}

        df = df.copy()
        if "timestamp" in df.columns:
            df["dt"] = pd.to_datetime(df["timestamp"])
        elif "time" in df.columns:
            df["dt"] = pd.to_datetime(df["time"])
        elif isinstance(df.index, pd.DatetimeIndex):
            df["dt"] = df.index
        else:
            return {"error": "No datetime column found"}

        # Resample to daily if intraday
        daily_close = df.set_index("dt")["close"].resample("D").last().dropna()
        daily_ret = daily_close.pct_change() * 100.0
        daily_df = pd.DataFrame({"return": daily_ret, "dayofweek": daily_ret.index.dayofweek}).dropna()

        dow_summary = {}
        for d in range(5):  # 0: Monday, 4: Friday
            sub = daily_df[daily_df["dayofweek"] == d]
            count = len(sub)
            if count > 0:
                avg_ret = float(sub["return"].mean())
                pos_count = int((sub["return"] > 0).sum())
                win_rate = (pos_count / count) * 100.0
                dow_summary[DAY_NAMES[d]] = {
                    "avg_return_pct": round(avg_ret, 3),
                    "win_rate_pct": round(win_rate, 1),
                    "sample_size": count,
                    "tendency": "BULLISH" if avg_ret > 0.05 and win_rate >= 53.0 else ("BEARISH" if avg_ret < -0.05 and win_rate <= 47.0 else "NEUTRAL"),
                }
            else:
                dow_summary[DAY_NAMES[d]] = {"avg_return_pct": 0.0, "win_rate_pct": 0.0, "sample_size": 0, "tendency": "NO_DATA"}

        return {
            "day_of_week_seasonality": dow_summary,
            "total_days_analyzed": len(daily_df),
            "status": "success",
        }
