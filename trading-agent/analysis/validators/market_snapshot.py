"""
Deterministic Market Data Ground-Truth Snapshot.

Computes exact OHLCV + key indicators from raw data WITHOUT LLM involvement.
Injected into analysis context as immutable ground truth that overrides
any conflicting LLM-generated metrics.
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from database.models import PriceOHLCV, TechnicalIndicator

logger = logging.getLogger("TradingAgent.MarketSnapshot")


class VerifiedMarketSnapshot:
    """Compute deterministic price/indicator ground truth."""

    async def compute(
        self,
        symbol: str,
        session: AsyncSession,
        as_of: Optional[datetime] = None,
        timeframe: str = "H1",
    ) -> Dict[str, Any]:
        """
        Compute verified snapshot from raw DB data.
        No LLM, no estimation, no hallucination possible.
        """
        now = as_of or datetime.now(timezone.utc)
        sym = symbol.strip().upper().replace("/", "")

        # Latest OHLCV (filtered by timeframe with fallback)
        ohlcv_q = (
            select(PriceOHLCV)
            .where(
                PriceOHLCV.symbol == sym,
                PriceOHLCV.timeframe == timeframe,
                PriceOHLCV.timestamp <= now,
            )
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(1)
        )
        ohlcv_row = (await session.execute(ohlcv_q)).scalar_one_or_none()
        if ohlcv_row is None:
            ohlcv_q_fallback = (
                select(PriceOHLCV)
                .where(PriceOHLCV.symbol == sym, PriceOHLCV.timestamp <= now)
                .order_by(desc(PriceOHLCV.timestamp))
                .limit(1)
            )
            ohlcv_row = (await session.execute(ohlcv_q_fallback)).scalar_one_or_none()

        # Latest indicators (filtered by timeframe with fallback)
        ind_q = (
            select(TechnicalIndicator)
            .where(
                TechnicalIndicator.symbol == sym,
                TechnicalIndicator.timeframe == timeframe,
                TechnicalIndicator.timestamp <= now,
            )
            .order_by(desc(TechnicalIndicator.timestamp))
            .limit(20)
        )
        ind_rows = (await session.execute(ind_q)).scalars().all()
        if not ind_rows:
            ind_q_fallback = (
                select(TechnicalIndicator)
                .where(TechnicalIndicator.symbol == sym, TechnicalIndicator.timestamp <= now)
                .order_by(desc(TechnicalIndicator.timestamp))
                .limit(20)
            )
            ind_rows = (await session.execute(ind_q_fallback)).scalars().all()

        snapshot = {
            "symbol": sym,
            "verified_at": now.isoformat(),
            "_ground_truth": True,
            "note": (
                "GROUND TRUTH — computed from raw data, no LLM involvement. "
                "If ANY of your generated values conflict with these, "
                "you MUST use these values instead."
            ),
        }

        if ohlcv_row:
            snapshot.update({
                "latest_close": float(ohlcv_row.close) if ohlcv_row.close is not None else None,
                "latest_high": float(ohlcv_row.high) if ohlcv_row.high is not None else None,
                "latest_low": float(ohlcv_row.low) if ohlcv_row.low is not None else None,
                "latest_open": float(ohlcv_row.open) if ohlcv_row.open is not None else None,
                "bar_timestamp": ohlcv_row.timestamp.isoformat() if ohlcv_row.timestamp else None,
            })

        for ind in ind_rows:
            try:
                name_key = ind.indicator_name.lower()
                val = json.loads(ind.value_json) if isinstance(ind.value_json, str) else ind.value_json
                if isinstance(val, (int, float)):
                    snapshot[name_key] = round(float(val), 5)
                elif isinstance(val, dict):
                    for subk, subv in val.items():
                        if isinstance(subv, (int, float)):
                            snapshot[f"{name_key}_{subk}"] = round(float(subv), 5)
                        else:
                            snapshot[f"{name_key}_{subk}"] = subv
                else:
                    snapshot[name_key] = val
            except Exception:
                pass

        # On-the-fly fallback: compute basic indicators if missing in DB and OHLCV exists
        has_rsi = any(k.startswith("rsi") for k in snapshot)
        has_atr = any(k.startswith("atr") for k in snapshot)
        if (not has_rsi or not has_atr) and ohlcv_row is not None:
            try:
                await self._compute_fallback_indicators(session, sym, timeframe, now, snapshot)
            except Exception as ex:
                logger.debug(f"Indicator fallback computation skipped: {ex}")

        return snapshot

    async def _compute_fallback_indicators(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        now: datetime,
        snapshot: Dict[str, Any]
    ) -> None:
        """Compute deterministic RSI and ATR if not present in database."""
        recent_bars_q = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe, PriceOHLCV.timestamp <= now)
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(30)
        )
        try:
            bars = (await session.execute(recent_bars_q)).scalars().all()
        except Exception:
            return

        if len(bars) < 15:
            return

        # Sort chronologically
        bars = sorted(bars, key=lambda b: b.timestamp)
        closes = [float(b.close) for b in bars if b.close is not None]
        highs = [float(b.high) for b in bars if b.high is not None]
        lows = [float(b.low) for b in bars if b.low is not None]

        # ATR 14
        if "atr_14" not in snapshot and len(highs) >= 15:
            trs = []
            for i in range(1, len(highs)):
                hl = highs[i] - lows[i]
                hc = abs(highs[i] - closes[i - 1])
                lc = abs(lows[i] - closes[i - 1])
                trs.append(max(hl, hc, lc))
            if len(trs) >= 14:
                atr_val = sum(trs[-14:]) / 14.0
                snapshot["atr_14"] = round(atr_val, 5)

        # RSI 14
        if "rsi_14" not in snapshot and len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                if diff >= 0:
                    gains.append(diff)
                    losses.append(0.0)
                else:
                    gains.append(0.0)
                    losses.append(abs(diff))
            if len(gains) >= 14:
                avg_gain = sum(gains[-14:]) / 14.0
                avg_loss = sum(losses[-14:]) / 14.0
                if avg_loss == 0:
                    snapshot["rsi_14"] = 100.0
                else:
                    rs = avg_gain / avg_loss
                    snapshot["rsi_14"] = round(100.0 - (100.0 / (1.0 + rs)), 2)

    @staticmethod
    def format_as_markdown(snapshot: Dict[str, Any]) -> str:
        """Format snapshot menjadi block markdown terstruktur untuk prompt injeksi."""
        sym = snapshot.get("symbol", "N/A")
        ts = snapshot.get("bar_timestamp", snapshot.get("verified_at", "N/A"))
        c = snapshot.get("latest_close", "N/A")
        h = snapshot.get("latest_high", "N/A")
        l = snapshot.get("latest_low", "N/A")
        o = snapshot.get("latest_open", "N/A")
        rsi = snapshot.get("rsi_14", "N/A")
        atr = snapshot.get("atr_14", "N/A")

        lines = [
            "### DETERMINISTIC MARKET GROUND TRUTH (DO NOT OVERRIDE)",
            f"- **Symbol**: {sym} | **Bar Timestamp**: {ts}",
            f"- **Price Action**: Close={c}, High={h}, Low={l}, Open={o}",
            f"- **Verified Indicators**: RSI(14)={rsi}, ATR(14)={atr}",
            "**Rule**: Any LLM statement conflicting with these values is strictly invalid.",
        ]
        return "\n".join(lines)

    @staticmethod
    def validate_plan_against_snapshot(
        plan: Dict[str, Any],
        snapshot: Dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """
        Validasi matematis trade plan terhadap snapshot pasar.
        Mencegah error halusinasi harga entry, SL, dan TP yang tidak masuk akal.
        """
        issues = []
        close = snapshot.get("latest_close")
        if close is None:
            return True, []

        action = str(plan.get("action", plan.get("decision", ""))).upper()
        if action not in ("BUY", "SELL"):
            return True, []

        entry = plan.get("entry_price") or close
        sl = plan.get("stop_loss")
        tp = plan.get("take_profit")

        # Entry divergence check (> 10% drift for market order is suspicious)
        order_type = str(plan.get("order_type", "MARKET")).upper()
        if "MARKET" in order_type and abs(entry - close) / close > 0.10:
            issues.append(f"Market order entry {entry} diverges >10% from current price {close}")

        # SL / TP directional consistency
        if action == "BUY":
            if sl is not None and sl >= entry:
                issues.append(f"BUY order SL ({sl}) must be below entry price ({entry})")
            if tp is not None and tp <= entry:
                issues.append(f"BUY order TP ({tp}) must be above entry price ({entry})")
        elif action == "SELL":
            if sl is not None and sl <= entry:
                issues.append(f"SELL order SL ({sl}) must be above entry price ({entry})")
            if tp is not None and tp >= entry:
                issues.append(f"SELL order TP ({tp}) must be below entry price ({entry})")

        return len(issues) == 0, issues
