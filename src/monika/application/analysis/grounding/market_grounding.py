# ==============================================================================
# File: application/analysis/grounding/market_grounding.py
# Monika Pre-Execution Market Grounding & Anti-Hallucination Engine
# ==============================================================================

"""
Pre-Execution Market Grounding:
Extracts empirical OHLCV price action and generates Markdown tables of absolute
ground truth. Injected into agent system prompts and fact sheets to eliminate
cutoff hallucinations and anchor LLMs in live price levels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger("TradingAgent.Grounding")


class MarketGroundingEngine:
    """Extracts empirical market realities and constructs Ground Truth prompt context."""

    @classmethod
    async def build_grounding_table(
        cls,
        symbol: str,
        session: Any = None,
        days_back: int = 30,
        repository: Any = None,
    ) -> str:
        """Constructs Markdown Ground Truth section for prompt injection via MarketDataRepository."""
        if not symbol:
            return ""

        norm_sym = symbol.upper().replace("/", "")
        repo = repository
        if repo is None and session is not None:
            try:
                from monika.infrastructure.database.repositories.market_data_repository import (
                    SqlAlchemyMarketDataRepository,
                )

                repo = SqlAlchemyMarketDataRepository(session)
            except Exception as e:
                logger.debug(f"[MarketGroundingEngine] Could not initialize SqlAlchemyMarketDataRepository: {e}")

        rows: Sequence[Any] = []
        if repo is not None and hasattr(repo, "get_recent_bars"):
            try:
                bars = await repo.get_recent_bars(norm_sym, timeframe="D1", limit=days_back)
                if not bars:
                    bars = await repo.get_recent_bars(norm_sym, timeframe="H4", limit=min(days_back * 6, 120))
                rows = bars or []
            except Exception as e:
                logger.warning(f"[MarketGroundingEngine] Failed fetching bars from repository for {norm_sym}: {e}")

        if not rows:
            return ""

        closes = [float(r.close) for r in rows]
        highs = [float(r.high) for r in rows]
        lows = [float(r.low) for r in rows]

        if not closes or not highs or not lows:
            return ""

        last_close = closes[-1]
        period_high = max(highs)
        period_low = min(lows)
        total_range = period_high - period_low
        range_pos_pct = round(((last_close - period_low) / max(total_range, 1e-9)) * 100.0, 1)

        pct_change = round(((last_close - closes[0]) / max(closes[0], 1e-9)) * 100.0, 2)
        trend_str = f"+{pct_change}% (BULLISH)" if pct_change > 0 else f"{pct_change}% (BEARISH)"

        sections: List[str] = [
            "## Ground Truth — Empirical Market Context (Strict Anchor)",
            f"*Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            "You MUST treat the prices below as absolute ground truth. Do not invent or assume historical prices.\n",
            f"### {norm_sym} (Recent {days_back}-Day Context)",
            f"- **Current Reference Price**: `{last_close:,.4f}`",
            f"- **Observed Range**: `{period_low:,.4f}` — `{period_high:,.4f}` (Span: `{total_range:,.4f}`)",
            f"- **Position in Range**: `{range_pos_pct}%` from range low",
            f"- **Period Net Return**: `{trend_str}`\n",
            "| Date | Open | High | Low | Close | Volume |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        recent_rows = list(rows)[-5:]
        for r in recent_rows:
            ts = getattr(r, "timestamp", None)
            d_str = ts.strftime("%Y-%m-%d") if isinstance(ts, datetime) else "N/A"
            o_val = float(getattr(r, "open", 0.0) or 0.0)
            h_val = float(getattr(r, "high", 0.0) or 0.0)
            l_val = float(getattr(r, "low", 0.0) or 0.0)
            c_val = float(getattr(r, "close", 0.0) or 0.0)
            v_val = float(getattr(r, "volume", 0.0) or 0.0)
            sections.append(f"| {d_str} | {o_val:.4f} | {h_val:.4f} | {l_val:.4f} | {c_val:.4f} | {v_val:,.0f} |")

        return "\n".join(sections) + "\n"

    @classmethod
    def format_grounding_from_df(cls, symbol: str, df: Optional[pd.DataFrame]) -> str:
        """Constructs Markdown Ground Truth section directly from an OHLCV DataFrame."""
        if df is None or df.empty:
            return ""
        norm_sym = symbol.upper().replace("/", "")
        closes = [float(x) for x in df["close"]]
        highs = [float(x) for x in df["high"]]
        lows = [float(x) for x in df["low"]]
        if not closes or not highs or not lows:
            return ""

        last_close = closes[-1]
        period_high = max(highs)
        period_low = min(lows)
        total_range = period_high - period_low
        range_pos_pct = round(((last_close - period_low) / max(total_range, 1e-9)) * 100.0, 1)
        pct_chg = round(((last_close - closes[0]) / max(closes[0], 1e-9)) * 100.0, 2)
        trend_str = f"+{pct_chg}% (BULLISH)" if pct_chg > 0 else f"{pct_chg}% (BEARISH)"

        sections = [
            "## Ground Truth — Empirical Market Context (Strict Anchor)",
            f"*Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            "You MUST treat the prices below as absolute ground truth. Do not invent or assume historical prices.\n",
            f"### {norm_sym} (Empirical Regime Context)",
            f"- **Current Reference Price**: `{last_close:,.4f}`",
            f"- **Observed Range**: `{period_low:,.4f}` — `{period_high:,.4f}` (Span: `{total_range:,.4f}`)",
            f"- **Position in Range**: `{range_pos_pct}%` from range low",
            f"- **Period Net Return**: `{trend_str}`\n",
            "| Date | Open | High | Low | Close | Volume |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        recent = df.tail(5)
        for idx, row in recent.iterrows():
            d_str = str(idx)[:10]
            o_val = float(str(row["open"]))
            h_val = float(str(row["high"]))
            l_val = float(str(row["low"]))
            c_val = float(str(row["close"]))
            vol_val = float(str(row.get("volume", 0.0) or 0.0))
            sections.append(f"| {d_str} | {o_val:.4f} | {h_val:.4f} | {l_val:.4f} | {c_val:.4f} | {vol_val:,.0f} |")
        return "\n".join(sections)
