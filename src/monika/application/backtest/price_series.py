"""Canonical Price Series Provider for Backtesting and Alpha Discovery.

Enforces:
1. Canonical timestamp normalization via BrokerTimeResolver.
2. Zero duplicate timestamps.
3. Monotonically increasing chronology.
4. Fail-closed data quality assertions (min_bars, max_gap_ratio).
5. Seamless loading from PostgreSQL database.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.core.exceptions import DataQualityError
from monika.infrastructure.database.models import PriceOHLCV

logger = logging.getLogger("TradingAgent.Backtest.PriceSeries")

TIMEFRAME_DELTA_MAP = {
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "M30": timedelta(minutes=30),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
    "W1": timedelta(weeks=1),
}


class CanonicalPriceLoader:
    """Canonical price series loader for backtesting, strategy validation, and playbooks."""

    def __init__(self, settings: Optional[dict] = None) -> None:
        self.settings = settings

    async def load_series(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 5000,
        min_bars: int = 100,
        max_gap_pct: float = 0.05,
    ) -> pd.DataFrame:
        """
        Load clean, deduplicated, monotonically ascending OHLCV dataframe.
        Fails closed with DataQualityError if min_bars not satisfied or gap ratio exceeds max_gap_pct.
        """
        sym = symbol.upper().strip()
        tf = timeframe.upper().strip()

        stmt = select(PriceOHLCV).where(
            PriceOHLCV.symbol == sym,
            PriceOHLCV.timeframe == tf,
        )
        if start_date:
            stmt = stmt.where(
                (PriceOHLCV.canonical_timestamp >= start_date)
                | (PriceOHLCV.canonical_timestamp.is_(None) & (PriceOHLCV.timestamp >= start_date))
            )
        if end_date:
            stmt = stmt.where(
                (PriceOHLCV.canonical_timestamp <= end_date)
                | (PriceOHLCV.canonical_timestamp.is_(None) & (PriceOHLCV.timestamp <= end_date))
            )

        stmt = stmt.order_by(
            PriceOHLCV.canonical_timestamp.desc().nulls_last(),
            PriceOHLCV.timestamp.desc(),
        ).limit(limit)

        res = await session.execute(stmt)
        rows = res.scalars().all()

        if not rows or len(rows) < min_bars:
            raise DataQualityError(
                f"Insufficient historical bars for {sym}/{tf}: found {len(rows)}, required minimum {min_bars}.",
                code="INSUFFICIENT_BARS",
                details={"symbol": sym, "timeframe": tf, "found": len(rows), "required": min_bars},
            )

        # Reverse to ascending chronological order
        chronological = list(reversed(rows))

        # Extract rows
        records: List[Dict[str, Any]] = []
        for r in chronological:
            ts = r.canonical_timestamp or r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            records.append(
                {
                    "time": ts,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume),
                }
            )

        df = pd.DataFrame(records)
        df.set_index("time", inplace=True)

        # Strict deduplication on index
        df = df.loc[~df.index.duplicated(keep="last")]

        # Chronological monotonicity
        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)

        # Gap verification
        self._validate_continuity(df, sym, tf, max_gap_pct)

        return df

    def _validate_continuity(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        max_gap_pct: float,
    ) -> None:
        """Verify that bar gaps (excluding weekends for Forex/Commodities) do not exceed threshold."""
        if len(df) < 2:
            return

        expected_delta = TIMEFRAME_DELTA_MAP.get(timeframe)
        if not expected_delta:
            return

        is_crypto = any(c in symbol for c in ("BTC", "ETH", "SOL", "XRP"))
        times = df.index.to_pydatetime()
        gaps = 0
        total_intervals = len(times) - 1

        for i in range(1, len(times)):
            delta = times[i] - times[i - 1]
            if delta > expected_delta:
                # If non-crypto and weekend (Friday evening to Sunday evening), allow normal market closure
                if not is_crypto:
                    prev_w = times[i - 1].weekday()
                    curr_w = times[i].weekday()
                    if prev_w == 4 and (curr_w == 6 or curr_w == 0):
                        # Friday to Sunday/Monday weekend closure is allowed
                        continue
                gaps += 1

        gap_ratio = gaps / total_intervals if total_intervals > 0 else 0.0
        if gap_ratio > max_gap_pct:
            raise DataQualityError(
                f"Data gap ratio for {symbol}/{timeframe} ({gap_ratio:.2%}) exceeds threshold ({max_gap_pct:.2%}).",
                code="EXCESSIVE_DATA_GAPS",
                details={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "gap_ratio": round(gap_ratio, 4),
                    "max_allowed": max_gap_pct,
                },
            )
