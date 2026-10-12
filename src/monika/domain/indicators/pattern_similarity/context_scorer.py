# ==============================================================================
# File: indicators/pattern_similarity/context_scorer.py
# ==============================================================================

"""
4-Tier Resilient Market Context Scorer.
Evaluates historical macroeconomic and market regime compatibility even during cold start.
Pure NumPy and SQLAlchemy queries with zero external package dependencies.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PatternMatch, MarketContext, ContextAnnotation

logger = logging.getLogger("TradingAgent.PatternContext")


class ContextScorer:
    """
    Evaluates how closely the macro environment of historical pattern matches
    aligns with current conditions.
    """

    BASE_WEIGHTS = {
        "volatility_similarity": 0.25,
        "usd_trend_similarity": 0.20,
        "regime_similarity": 0.25,
        "rate_cycle_similarity": 0.15,
        "asset_trend_similarity": 0.15,
    }

    VIX_THRESHOLDS = {
        "low": 16.0,
        "normal": 24.0,
        "elevated": 34.0,
    }

    def __init__(self, session: AsyncSession, settings: Optional[dict] = None):
        self.session = session
        self.settings = settings or {}
        self._current_context: Optional[MarketContext] = None

    async def score_matches(
        self,
        matches: List[PatternMatch],
        symbol: str,
        timeframe: str,
        historical_bars: np.ndarray,
    ) -> None:
        """
        Calculates context similarity scores for a list of pattern matches.
        Mutates PatternMatch objects in-place.
        """
        if not matches:
            return

        if self._current_context is None:
            self._current_context = await self._fetch_or_compute_context(
                symbol=symbol, match_date=None, bars_slice=historical_bars[-60:] if len(historical_bars) >= 60 else historical_bars
            )

        for match in matches:
            match_date = datetime.fromtimestamp(match.end_time, tz=timezone.utc)
            # Slice historical bars up to the match endpoint for OHLCV proxies
            slice_start = max(0, match.start_index - 30)
            bars_slice = historical_bars[slice_start:match.end_index]

            hist_ctx = await self._fetch_or_compute_context(
                symbol=symbol, match_date=match_date, bars_slice=bars_slice
            )

            sim_score, coverage_ratio = self._compute_adaptive_similarity(
                self._current_context, hist_ctx
            )

            match.context_score = float(sim_score)
            match.context_coverage = float(coverage_ratio)
            match.context_label = (
                "HIGH" if sim_score >= 0.70 and coverage_ratio >= 0.60 else
                "MEDIUM" if sim_score >= 0.40 and coverage_ratio >= 0.40 else
                "LOW" if coverage_ratio >= 0.40 else
                "UNVERIFIED"
            )

    async def _fetch_or_compute_context(
        self,
        symbol: str,
        match_date: Optional[datetime],
        bars_slice: Optional[np.ndarray],
    ) -> MarketContext:
        """Tier 1 DB query with Tier 2 OHLCV proxy fallback."""
        data_sources: Dict[str, str] = {}

        # 1. Volatility (VIX from DB or Yang-Zhang Realized Volatility Proxy)
        vix_val, vix_src = await self._get_vix_or_proxy(match_date, bars_slice)
        data_sources["vix"] = vix_src

        # 2. USD Strength / DXY Trend (DXY from DB or Multi-Pair USD Proxy)
        dxy_trend, dxy_src = await self._get_dxy_trend_or_proxy(match_date)
        data_sources["dxy"] = dxy_src

        # 3. Market Regime (ADX + ATR from OHLCV)
        regime = self._compute_regime_from_bars(bars_slice)
        data_sources["regime"] = "ohlcv"

        # 4. Central Bank Interest Rate Cycle
        rate_cycle, rate_src = await self._get_rate_cycle(match_date)
        data_sources["rate_cycle"] = rate_src

        # 5. Asset Trend vs Long-Term Moving Average (from OHLCV)
        asset_trend = self._compute_trend_from_bars(bars_slice)
        data_sources["asset_trend"] = "ohlcv"

        return MarketContext(
            vix_level=vix_val,
            vix_category=self._categorize_vix(vix_val),
            dxy_trend=dxy_trend,
            market_regime=regime,
            rate_cycle=rate_cycle,
            asset_trend=asset_trend,
            data_sources=data_sources,
        )

    async def _get_vix_or_proxy(
        self, match_date: Optional[datetime], bars_slice: Optional[np.ndarray]
    ) -> Tuple[float, str]:
        """Fetches VIX from DB or falls back to Yang-Zhang Realized Volatility."""
        try:
            from database.models import VIXData

            stmt = select(VIXData)
            if match_date:
                stmt = stmt.where(VIXData.date <= match_date)
            stmt = stmt.order_by(desc(VIXData.date)).limit(1)

            res = await self.session.execute(stmt)
            row = res.scalar_one_or_none()

            if row and row.close and row.close > 0:
                # Check that date is reasonably close (within 10 days)
                if match_date and abs((match_date - row.date.replace(tzinfo=timezone.utc if row.date.tzinfo is None else row.date.tzinfo)).days) > 14:
                    pass  # Fall through to OHLCV proxy
                else:
                    return float(row.close), "db"
        except Exception as e:
            logger.debug(f"VIX DB lookup error: {e}")

        # Fallback to Yang-Zhang Realized Volatility from OHLCV
        if bars_slice is not None and len(bars_slice) >= 10:
            proxy_val = self._compute_yang_zhang_proxy(bars_slice)
            return float(proxy_val), "ohlcv_proxy"

        return 20.0, "default"

    async def _get_dxy_trend_or_proxy(
        self, match_date: Optional[datetime]
    ) -> Tuple[str, str]:
        """Fetches DXY trend from DB or falls back to compute_usd_strength_proxy."""
        try:
            from database.models import DXYData

            stmt = select(DXYData)
            if match_date:
                stmt = stmt.where(DXYData.date <= match_date)
            stmt = stmt.order_by(desc(DXYData.date)).limit(15)

            res = await self.session.execute(stmt)
            rows = res.scalars().all()

            if len(rows) >= 5:
                # Verify recency of the latest row
                latest_dt = rows[0].date
                if latest_dt.tzinfo is None:
                    latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                if match_date is None or abs((match_date - latest_dt).days) <= 14:
                    prices = [r.close for r in reversed(rows)]
                    diff = prices[-1] - prices[0]
                    pct = (diff / prices[0]) * 100.0 if prices[0] > 0 else 0.0
                    trend = "bullish" if pct > 0.5 else ("bearish" if pct < -0.5 else "flat")
                    return trend, "db"
        except Exception as e:
            logger.debug(f"DXY DB lookup error: {e}")

        # Fallback: compute USD strength proxy from Forex basket
        try:
            from utils.market.usd_strength_proxy import compute_usd_strength_proxy
            proxy_res = await compute_usd_strength_proxy(
                self.session, lookback_bars=20, timeframe="D1", as_of=match_date
            )
            score = proxy_res.get("composite_usd_score", 0.0)
            trend = "bullish" if score > 0.4 else ("bearish" if score < -0.4 else "flat")
            return trend, "usd_basket_proxy"
        except Exception:
            return "unknown", "missing"

    async def _get_rate_cycle(self, match_date: Optional[datetime]) -> Tuple[str, str]:
        """Determines monetary policy cycle from interest_rates table."""
        try:
            from database.models import InterestRate

            stmt = select(InterestRate).where(InterestRate.bank == "FED")
            if match_date:
                stmt = stmt.where(InterestRate.effective_date <= match_date)
            stmt = stmt.order_by(desc(InterestRate.effective_date)).limit(2)

            res = await self.session.execute(stmt)
            rows = res.scalars().all()

            if len(rows) >= 2:
                rate_diff = rows[0].rate_percent - rows[1].rate_percent
                if rate_diff > 0.1:
                    return "hiking", "db"
                elif rate_diff < -0.1:
                    return "cutting", "db"
                else:
                    return "pause", "db"
            elif len(rows) == 1:
                return "pause", "db"
        except Exception:
            pass

        return "unknown", "missing"

    def _compute_regime_from_bars(self, bars: Optional[np.ndarray]) -> str:
        """Computes market regime directly from OHLCV bars using trend & range."""
        if bars is None or len(bars) < 14:
            return "trend"

        closes = bars[:, 4]
        highs = bars[:, 2]
        lows = bars[:, 3]

        # ATR computation
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
        )
        atr = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)

        # Net displacement over 14 bars
        displacement = abs(closes[-1] - closes[-14]) if len(closes) >= 14 else abs(closes[-1] - closes[0])
        efficiency_ratio = displacement / (atr * 14.0 + 1e-8)

        if efficiency_ratio > 0.45:
            return "trend"
        elif efficiency_ratio < 0.20:
            return "range"
        else:
            return "volatile_chop"

    def _compute_trend_from_bars(self, bars: Optional[np.ndarray]) -> str:
        """Determines price position relative to exponential moving average."""
        if bars is None or len(bars) < 20:
            return "neutral"

        closes = bars[:, 4]
        # Fast EMA proxy over available bars
        period = min(50, len(closes))
        alpha = 2.0 / (period + 1.0)
        ema = closes[0]
        for c in closes[1:]:
            ema = alpha * c + (1.0 - alpha) * ema

        if closes[-1] > ema * 1.002:
            return "above_ema"
        elif closes[-1] < ema * 0.998:
            return "below_ema"
        return "neutral"

    def _compute_yang_zhang_proxy(self, bars: np.ndarray) -> float:
        """
        Computes Yang-Zhang Realized Volatility as an annualized percentage VIX proxy.
        Formula: Yang, D., & Zhang, Q. (2000). Drift-Independent Volatility Estimation.
        """
        if len(bars) < 10:
            return 20.0

        opens = bars[:, 1]
        highs = bars[:, 2]
        lows = bars[:, 3]
        closes = bars[:, 4]

        log_co = np.log(np.maximum(opens[1:] / np.maximum(closes[:-1], 1e-8), 1e-8))
        log_oc = np.log(np.maximum(closes[1:] / np.maximum(opens[1:], 1e-8), 1e-8))
        log_ho = np.log(np.maximum(highs[1:] / np.maximum(opens[1:], 1e-8), 1e-8))
        log_lo = np.log(np.maximum(lows[1:] / np.maximum(opens[1:], 1e-8), 1e-8))

        rs = log_ho * (log_ho - log_oc) + log_lo * (log_lo - log_oc)
        n = len(log_co)
        k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0)) if n > 1 else 0.5

        sigma_o = float(np.var(log_co, ddof=1)) if n > 1 else 0.0001
        sigma_c = float(np.var(log_oc, ddof=1)) if n > 1 else 0.0001
        sigma_rs = float(np.mean(rs))

        var_yz = max(1e-8, sigma_o + k * sigma_c + (1.0 - k) * sigma_rs)
        annualized = np.sqrt(var_yz) * np.sqrt(252) * 100.0
        return float(np.clip(annualized, 8.0, 75.0))

    def _categorize_vix(self, vix: float) -> str:
        if vix < self.VIX_THRESHOLDS["low"]:
            return "low"
        elif vix < self.VIX_THRESHOLDS["normal"]:
            return "normal"
        elif vix < self.VIX_THRESHOLDS["elevated"]:
            return "elevated"
        return "crisis"

    def _compute_adaptive_similarity(
        self, current: MarketContext, historical: MarketContext
    ) -> Tuple[float, float]:
        """
        Tier 3: Dynamic Adaptive Weight Re-normalization.
        Only active/available dimensions contribute; total active weight scales to 1.0.
        """
        active_weights: Dict[str, float] = {}
        sub_scores: Dict[str, float] = {}

        # 1. Volatility
        sub_scores["volatility_similarity"] = (
            1.0 if current.vix_category == historical.vix_category else
            0.5 if abs(current.vix_level - historical.vix_level) <= 8.0 else 0.0
        )
        active_weights["volatility_similarity"] = self.BASE_WEIGHTS["volatility_similarity"]

        # 2. USD Trend
        if historical.dxy_trend != "unknown" and current.dxy_trend != "unknown":
            sub_scores["usd_trend_similarity"] = (
                1.0 if current.dxy_trend == historical.dxy_trend else 0.0
            )
            active_weights["usd_trend_similarity"] = self.BASE_WEIGHTS["usd_trend_similarity"]

        # 3. Market Regime
        sub_scores["regime_similarity"] = (
            1.0 if current.market_regime == historical.market_regime else
            0.5 if self._regimes_compatible(current.market_regime, historical.market_regime) else 0.0
        )
        active_weights["regime_similarity"] = self.BASE_WEIGHTS["regime_similarity"]

        # 4. Rate Cycle
        if historical.rate_cycle != "unknown" and current.rate_cycle != "unknown":
            sub_scores["rate_cycle_similarity"] = (
                1.0 if current.rate_cycle == historical.rate_cycle else 0.0
            )
            active_weights["rate_cycle_similarity"] = self.BASE_WEIGHTS["rate_cycle_similarity"]

        # 5. Asset Trend
        sub_scores["asset_trend_similarity"] = (
            1.0 if current.asset_trend == historical.asset_trend else 0.0
        )
        active_weights["asset_trend_similarity"] = self.BASE_WEIGHTS["asset_trend_similarity"]

        # Normalization
        tot_active = sum(active_weights.values())
        tot_base = sum(self.BASE_WEIGHTS.values())
        coverage = float(tot_active / tot_base) if tot_base > 0 else 1.0

        if tot_active > 0:
            weighted_score = sum(
                sub_scores[k] * (w / tot_active) for k, w in active_weights.items()
            )
            weighted_score = min(1.0, max(0.0, weighted_score))
        else:
            weighted_score = 0.5

        return float(weighted_score), coverage

    def _regimes_compatible(self, r1: str, r2: str) -> bool:
        """Determines if two regimes are directionally compatible."""
        if r1 == r2:
            return True
        compatible_pairs = [
            ("trend", "volatile_chop"),
            ("volatile_chop", "trend"),
            ("range", "squeeze"),
            ("squeeze", "range"),
        ]
        return (r1, r2) in compatible_pairs

    async def annotate_top_matches(
        self, matches: List[PatternMatch], limit: int = 5
    ) -> List[ContextAnnotation]:
        """Tier 2: Annotates top matches with historical narrative from MarketChronicle."""
        from database.models import MarketChronicle

        annotations: List[ContextAnnotation] = []
        top_slice = sorted(matches, key=lambda m: m.similarity, reverse=True)[:limit]

        for match in top_slice:
            match_dt = datetime.fromtimestamp(match.end_time, tz=timezone.utc)
            start_window = match_dt - timedelta(days=7)
            end_window = match_dt + timedelta(days=7)

            stmt = select(MarketChronicle).where(
                MarketChronicle.event_date.between(start_window, end_window)
            ).order_by(desc(MarketChronicle.severity)).limit(3)

            res = await self.session.execute(stmt)
            chronicles = res.scalars().all()

            annotations.append(ContextAnnotation(
                match=match,
                chronicle_events=[f"[{c.category.upper()}] {c.headline}" for c in chronicles],
                context_label=match.context_label,
                context_score=match.context_score,
            ))

        return annotations
