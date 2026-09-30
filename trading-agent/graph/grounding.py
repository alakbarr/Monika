# ==============================================================================
# File: graph/grounding.py
# Monika Pre-Execution Market Grounding & Anti-Hallucination Engine
# ==============================================================================

"""
Pre-Execution Market Grounding:
Fetches 30 days of verified OHLCV bars from the primary broker / database before the graph runs.
Generates a markdown table of empirical ground truth and injects it into agent system prompts,
eliminating training data cutoff hallucinations and grounding AI agents in live prices.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV

logger = logging.getLogger("TradingAgent.Grounding")


class MarketGroundingEngine:
    """Extracts empirical market realities and constructs Ground Truth prompt context."""

    @classmethod
    async def build_grounding_table(
        cls,
        session: AsyncSession,
        symbols: List[str],
        days_back: int = 30,
    ) -> str:
        """Constructs Markdown Ground Truth section for prompt injection."""
        if not symbols:
            return ""

        sections: List[str] = [
            "## Ground Truth — Empirical Market Context (Strict Anchor)",
            f"*Generated at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
            "You MUST treat the prices below as absolute ground truth. Do not invent or assume historical prices.\n",
        ]

        for symbol in symbols:
            norm_sym = symbol.upper().replace("/", "")
            stmt = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == norm_sym, PriceOHLCV.timeframe == "D1")
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(days_back)
            )
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                # Try H4 if D1 is sparse
                stmt_h4 = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == norm_sym, PriceOHLCV.timeframe == "H4")
                    .order_by(PriceOHLCV.timestamp.desc())
                    .limit(min(days_back * 6, 120))
                )
                rows = (await session.execute(stmt_h4)).scalars().all()
                if not rows:
                    continue

            rows = list(reversed(rows))
            closes = [float(r.close) for r in rows]
            highs = [float(r.high) for r in rows]
            lows = [float(r.low) for r in rows]

            last_close = closes[-1]
            period_high = max(highs)
            period_low = min(lows)
            total_range = period_high - period_low
            range_pos_pct = round(((last_close - period_low) / max(total_range, 1e-9)) * 100.0, 1)

            # Trend direction over 30 days
            pct_30d = round(((last_close - closes[0]) / closes[0]) * 100.0, 2)
            trend_str = f"+{pct_30d}% (BULLISH)" if pct_30d > 0 else f"{pct_30d}% (BEARISH)"

            sections.append(f"### {norm_sym} (Last 30-Day Regime)")
            sections.append(
                f"- **Current Reference Price**: `{last_close:,.4f}`\n"
                f"- **30-Day Range**: `{period_low:,.4f}` — `{period_high:,.4f}` (Span: `{total_range:,.4f}`)\n"
                f"- **Position in Range**: `{range_pos_pct}%` from 30d low\n"
                f"- **30-Day Net Return**: `{trend_str}`"
            )

            # Mini OHLC table of the last 5 days
            recent_rows = rows[-5:]
            table_lines = [
                "| Date | Open | High | Low | Close | Volume |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
            for r in recent_rows:
                d_str = r.timestamp.strftime("%Y-%m-%d") if r.timestamp else "N/A"
                table_lines.append(
                    f"| {d_str} | {float(r.open):.4f} | {float(r.high):.4f} | "
                    f"{float(r.low):.4f} | {float(r.close):.4f} | {float(r.volume or 0):,.0f} |"
                )
            sections.append("\n".join(table_lines) + "\n")

        return "\n".join(sections)

    @classmethod
    def format_grounding_from_df(cls, symbol: str, df: pd.DataFrame) -> str:
        """Constructs Markdown Ground Truth section directly from an OHLCV DataFrame."""
        if df is None or df.empty:
            return ""
        norm_sym = symbol.upper().replace("/", "")
        closes = [float(x) for x in df["close"]]
        highs = [float(x) for x in df["high"]]
        lows = [float(x) for x in df["low"]]
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
            vol_val = float(row.get("volume", 0.0) or 0.0)
            sections.append(
                f"| {d_str} | {float(row['open']):.4f} | {float(row['high']):.4f} | "
                f"{float(row['low']):.4f} | {float(row['close']):.4f} | {vol_val:,.0f} |"
            )
        return "\n".join(sections)

