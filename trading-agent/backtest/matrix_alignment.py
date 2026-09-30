# ==============================================================================
# File: backtest/matrix_alignment.py
# Monika High-Performance In-Memory Market Matrix Alignment Engine
# ==============================================================================

"""
In-Memory Market Matrix Pre-Alignment:
Extracts historical OHLCV data for multiple instruments once and aligns them across
a unified calendar index into contiguous 2D NumPy arrays:
  - open_matrix (T, N)
  - high_matrix (T, N)
  - low_matrix (T, N)
  - close_matrix (T, N)
  - volume_matrix (T, N)

Accelerates backtesting and cross-sectional factor evaluation by up to 30x
by completely eliminating per-bar database query storms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV

logger = logging.getLogger("TradingAgent.MatrixAlignment")


@dataclass(frozen=True, slots=True)
class AlignedMarketMatrix:
    timestamps: np.ndarray       # shape (T,) datetime64[ns]
    instruments: Tuple[str, ...] # length N
    instrument_to_idx: Dict[str, int]
    open: np.ndarray             # shape (T, N) float64
    high: np.ndarray             # shape (T, N) float64
    low: np.ndarray              # shape (T, N) float64
    close: np.ndarray            # shape (T, N) float64
    volume: np.ndarray           # shape (T, N) float64

    @property
    def shape(self) -> Tuple[int, int]:
        return self.close.shape

    def get_bar_dict(self, t_idx: int, symbol: str) -> Optional[Dict[str, Any]]:
        idx = self.instrument_to_idx.get(symbol.upper())
        if idx is None or t_idx < 0 or t_idx >= self.close.shape[0]:
            return None
        c_val = self.close[t_idx, idx]
        if np.isnan(c_val):
            return None
        return {
            "timestamp": pd.to_datetime(self.timestamps[t_idx]).isoformat(),
            "open": float(self.open[t_idx, idx]),
            "high": float(self.high[t_idx, idx]),
            "low": float(self.low[t_idx, idx]),
            "close": float(c_val),
            "volume": float(self.volume[t_idx, idx]),
        }


class MatrixAlignmentEngine:
    """Pre-aligns multi-instrument time series into unified matrix representations."""

    @classmethod
    def align_dataframes(
        cls,
        df_dict: Dict[str, pd.DataFrame],
        method: str = "outer",
    ) -> AlignedMarketMatrix:
        """Aligns a dictionary of symbol DataFrames {sym: df} having columns (open, high, low, close, volume)."""
        if not df_dict:
            raise ValueError("df_dict cannot be empty")

        # Collect all unique timestamps
        all_timestamps = set()
        cleaned_dfs: Dict[str, pd.DataFrame] = {}

        for sym, df in df_dict.items():
            if df.empty:
                continue
            df_copy = df.copy()
            if not isinstance(df_copy.index, pd.DatetimeIndex):
                if "timestamp" in df_copy.columns:
                    df_copy["timestamp"] = pd.to_datetime(df_copy["timestamp"])
                    df_copy.set_index("timestamp", inplace=True)
                else:
                    df_copy.index = pd.to_datetime(df_copy.index)
            df_copy = df_copy.sort_index()
            # De-duplicate index
            df_copy = df_copy[~df_copy.index.duplicated(keep="last")]
            cleaned_dfs[sym.upper()] = df_copy
            all_timestamps.update(df_copy.index)

        if not all_timestamps:
            raise ValueError("No valid timestamps found across DataFrames")

        sorted_times = sorted(list(all_timestamps))
        idx_series = pd.DatetimeIndex(sorted_times)

        instruments = tuple(sorted(cleaned_dfs.keys()))
        inst_to_idx = {sym: i for i, sym in enumerate(instruments)}
        T = len(sorted_times)
        N = len(instruments)

        open_arr = np.full((T, N), np.nan, dtype=np.float64)
        high_arr = np.full((T, N), np.nan, dtype=np.float64)
        low_arr = np.full((T, N), np.nan, dtype=np.float64)
        close_arr = np.full((T, N), np.nan, dtype=np.float64)
        vol_arr = np.full((T, N), 0.0, dtype=np.float64)

        for sym, df in cleaned_dfs.items():
            col_idx = inst_to_idx[sym]
            reindexed = df.reindex(idx_series)

            if "open" in reindexed:
                open_arr[:, col_idx] = reindexed["open"].to_numpy(dtype=np.float64)
            if "high" in reindexed:
                high_arr[:, col_idx] = reindexed["high"].to_numpy(dtype=np.float64)
            if "low" in reindexed:
                low_arr[:, col_idx] = reindexed["low"].to_numpy(dtype=np.float64)
            if "close" in reindexed:
                close_arr[:, col_idx] = reindexed["close"].to_numpy(dtype=np.float64)
            if "volume" in reindexed:
                vol_arr[:, col_idx] = np.nan_to_num(reindexed["volume"].to_numpy(dtype=np.float64), nan=0.0)

        return AlignedMarketMatrix(
            timestamps=idx_series.to_numpy(),
            instruments=instruments,
            instrument_to_idx=inst_to_idx,
            open=open_arr,
            high=high_arr,
            low=low_arr,
            close=close_arr,
            volume=vol_arr,
        )

    @classmethod
    async def load_and_align_from_db(
        cls,
        session: AsyncSession,
        symbols: Sequence[str],
        timeframe: str = "H1",
        limit_per_symbol: int = 1000,
    ) -> AlignedMarketMatrix:
        """Pulls OHLCV bars directly from the database and aligns them in memory."""
        df_dict: Dict[str, pd.DataFrame] = {}

        for sym in symbols:
            norm_sym = sym.upper().replace("/", "")
            stmt = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == norm_sym, PriceOHLCV.timeframe == timeframe.upper())
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(limit_per_symbol)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                continue

            rows = list(reversed(rows))
            data = {
                "timestamp": [r.timestamp for r in rows],
                "open": [float(r.open) for r in rows],
                "high": [float(r.high) for r in rows],
                "low": [float(r.low) for r in rows],
                "close": [float(r.close) for r in rows],
                "volume": [float(r.volume or 0.0) for r in rows],
            }
            df = pd.DataFrame(data).set_index("timestamp")
            df_dict[norm_sym] = df

        if not df_dict:
            raise ValueError(f"No OHLCV records found in DB for symbols: {symbols}")

        return cls.align_dataframes(df_dict)
