# ==============================================================================
# File: graph/grounding.py
# Monika Pre-Execution Market Grounding Facade
# ==============================================================================

"""
Pre-Execution Market Grounding Facade:
Re-exports MarketGroundingEngine from canonical location in analysis.grounding.
Maintains backward-compatibility for legacy graph callers while upholding
Clean Architecture boundaries.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union
import pandas as pd

from monika.application.analysis.grounding.market_grounding import (
    MarketGroundingEngine as _CanonicalMarketGroundingEngine,
)


class MarketGroundingEngine:
    """Facade for canonical MarketGroundingEngine in analysis.grounding."""

    @classmethod
    async def build_grounding_table(
        cls,
        session: Any,
        symbols: Union[str, List[str]],
        days_back: int = 30,
    ) -> str:
        """Constructs Markdown Ground Truth section for prompt injection."""
        sym_list = [symbols] if isinstance(symbols, str) else list(symbols or [])
        if not sym_list:
            return ""

        tables = []
        for sym in sym_list:
            tbl = await _CanonicalMarketGroundingEngine.build_grounding_table(
                symbol=sym, session=session, days_back=days_back
            )
            if tbl:
                tables.append(tbl)
        return "\n".join(tables)

    @classmethod
    def format_grounding_from_df(cls, symbol: str, df: Optional[pd.DataFrame]) -> str:
        """Constructs Markdown Ground Truth section directly from an OHLCV DataFrame."""
        return _CanonicalMarketGroundingEngine.format_grounding_from_df(symbol=symbol, df=df)


__all__ = ["MarketGroundingEngine"]
