# ==============================================================================
# File: indicators/pattern_similarity/engine.py
# ==============================================================================

"""
Main Pattern Similarity Screening Engine.
Orchestrates multi-timeframe scanning, resilient context scoring, cross-symbol matching,
forward outcome analysis, and multi-timeframe consensus aggregation.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import numpy as np
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    PatternMatch,
    SingleTimeframeResult,
    MultiTimeframeScreeningResult,
    MarketContext,
)
from .normalizer import PriceNormalizer
from .feature_extractor import FeatureExtractor
from .scanner import SimilarityScanner
from .context_scorer import ContextScorer
from .outcome_analyzer import OutcomeAnalyzer
from .context_verifier import PatternContextVerifier

logger = logging.getLogger("TradingAgent.PatternSimilarityEngine")


class PatternSimilarityEngine:
    """
    Context-aware, multi-timeframe historical chart pattern similarity engine.
    Finds historical patterns similar to current, scores macro context, and computes
    a probabilistic outcome forecast.
    """

    DEFAULT_WINDOW_SIZES = {"D1": 40, "H4": 30, "H1": 24}
    DEFAULT_LOOKBACK_YEARS = {"D1": 4.0, "H4": 3.0, "H1": 1.5}
    TF_WEIGHTS = {"D1": 0.40, "H4": 0.35, "H1": 0.25}

    def __init__(self, session: AsyncSession, settings: Optional[dict] = None):
        self.session = session
        self.settings = settings or {}

        self.normalizer = PriceNormalizer()
        self.feature_extractor = FeatureExtractor()
        self.scanner = SimilarityScanner()
        self.context_scorer = ContextScorer(session, self.settings)
        self.outcome_analyzer = OutcomeAnalyzer()
        self.context_verifier = PatternContextVerifier(self.settings)

        # Config extraction
        ps_cfg = self.settings.get("pattern_similarity", {})
        self.enabled = ps_cfg.get("enabled", True)
        self.top_k = ps_cfg.get("top_k", 20)
        self.min_similarity = ps_cfg.get("min_similarity", 0.75)
        self.min_matches = ps_cfg.get("min_matches_for_signal", 5)
        self.cross_symbol_enabled = ps_cfg.get("cross_symbol_enabled", True)
        self.cross_symbol_weight = ps_cfg.get("cross_symbol_weight", 0.5)
        self.cross_symbol_max_symbols = ps_cfg.get("cross_symbol_max_symbols", 3)
        self.llm_context_verify = ps_cfg.get("llm_context_verify", True)
        self.window_sizes = ps_cfg.get("window_sizes", self.DEFAULT_WINDOW_SIZES)
        self.lookback_years = ps_cfg.get("lookback_years", self.DEFAULT_LOOKBACK_YEARS)

    async def screen(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
        llm_client: Optional[Any] = None,
    ) -> MultiTimeframeScreeningResult:
        """
        Executes end-to-end multi-timeframe pattern similarity screening for a symbol.
        """
        if not self.enabled:
            return MultiTimeframeScreeningResult.empty(symbol)

        tfs = timeframes or ["D1", "H4", "H1"]
        per_tf_results: Dict[str, SingleTimeframeResult] = {}

        # 1. Screen each timeframe independently
        for tf in tfs:
            tf_res = await self._screen_single_tf(symbol, tf)
            per_tf_results[tf] = tf_res

        # 2. Add cross-symbol bonus matches if primary has few matches
        if self.cross_symbol_enabled:
            await self._add_cross_symbol_matches(symbol, per_tf_results)

        # 3. Aggregate multi-timeframe consensus
        aggregated = self._aggregate_multi_tf(symbol, per_tf_results)

        # 4. Optional LLM context verification for top matches
        if self.llm_context_verify and aggregated.has_significant_results():
            await self._verify_contexts_with_llm(symbol, aggregated, llm_client)

        return aggregated

    async def _screen_single_tf(self, symbol: str, timeframe: str) -> SingleTimeframeResult:
        """Screens a single timeframe for similar patterns."""
        w_size = int(self.window_sizes.get(timeframe, self.DEFAULT_WINDOW_SIZES.get(timeframe, 30)))
        lb_years = float(self.lookback_years.get(timeframe, self.DEFAULT_LOOKBACK_YEARS.get(timeframe, 2.0)))

        # Fetch recent current bars
        current_bars = await self._fetch_recent_bars(symbol, timeframe, w_size)
        if current_bars is None or len(current_bars) < w_size:
            return SingleTimeframeResult.empty(timeframe)

        # Fetch historical bar archive
        historical_bars = await self._fetch_historical_bars(symbol, timeframe, lb_years)
        if historical_bars is None or len(historical_bars) < w_size * 2:
            return SingleTimeframeResult.empty(timeframe)

        # Run vectorized pattern matching in thread pool (CPU bound)
        matches = await asyncio.to_thread(
            self.scanner.find_similar_patterns,
            current_bars,
            historical_bars,
            w_size,
            self.top_k,
            self.min_similarity,
            "euclidean",
        )

        if not matches:
            return SingleTimeframeResult.empty(timeframe)

        # Resilient context scoring
        await self.context_scorer.score_matches(
            matches=matches,
            symbol=symbol,
            timeframe=timeframe,
            historical_bars=historical_bars,
        )

        # Analyze forward outcomes
        outcomes = self.outcome_analyzer.analyze_outcomes(
            matches=matches,
            historical_bars=historical_bars,
            timeframe=timeframe,
        )

        # Aggregate context-weighted statistics
        stats = self.outcome_analyzer.compute_context_weighted_statistics(
            outcomes=outcomes,
            min_matches=self.min_matches,
            significance_threshold=0.10,
        )

        avg_sim = float(np.mean([m.similarity for m in matches])) if matches else 0.0

        return SingleTimeframeResult(
            timeframe=timeframe,
            statistics=stats,
            top_matches=sorted(matches, key=lambda m: m.similarity, reverse=True)[:5],
            avg_similarity=avg_sim,
        )

    async def _add_cross_symbol_matches(
        self, primary_symbol: str, per_tf: Dict[str, SingleTimeframeResult]
    ) -> None:
        """Injects cross-symbol matches with 0.5x weight when same-symbol has few matches."""
        universe = self.settings.get("trading", {}).get("asset_universe", [])
        other_symbols = [s for s in universe if s != primary_symbol][:self.cross_symbol_max_symbols]

        for tf, res in per_tf.items():
            if res.match_count >= self.top_k:
                continue

            needed = self.top_k - res.match_count
            w_size = int(self.window_sizes.get(tf, 30))
            lb_years = float(self.lookback_years.get(tf, 2.0))

            current_bars = await self._fetch_recent_bars(primary_symbol, tf, w_size)
            if current_bars is None or len(current_bars) < w_size:
                continue

            for other_sym in other_symbols:
                other_hist = await self._fetch_historical_bars(other_sym, tf, lb_years)
                if other_hist is None or len(other_hist) < w_size * 2:
                    continue

                cross_matches = await asyncio.to_thread(
                    self.scanner.find_similar_patterns,
                    current_bars,
                    other_hist,
                    w_size,
                    min(4, needed),
                    self.min_similarity + 0.05,  # Higher threshold for cross-symbol
                )

                for m in cross_matches:
                    m.is_cross_symbol = True
                    m.source_symbol = other_sym
                    m.weight = self.cross_symbol_weight

                res.add_cross_symbol_matches(cross_matches)

    def _aggregate_multi_tf(
        self, symbol: str, per_tf: Dict[str, SingleTimeframeResult]
    ) -> MultiTimeframeScreeningResult:
        """Weighted aggregation across all timeframes."""
        weighted_bull = 0.0
        weighted_bear = 0.0
        total_weight = 0.0
        sig_tfs: List[str] = []
        biases: Dict[str, str] = {}

        for tf, res in per_tf.items():
            if not res.statistics.is_significant:
                continue

            w = self.TF_WEIGHTS.get(tf, 0.25)
            weighted_bull += w * res.statistics.bullish_pct
            weighted_bear += w * res.statistics.bearish_pct
            total_weight += w
            sig_tfs.append(tf)
            biases[tf] = res.statistics.directional_bias

        if total_weight > 0:
            consensus_bull = weighted_bull / total_weight
            consensus_bear = weighted_bear / total_weight
        else:
            consensus_bull = 0.5
            consensus_bear = 0.5

        if consensus_bull >= 0.60:
            overall_bias = "bullish"
        elif consensus_bear >= 0.60:
            overall_bias = "bearish"
        else:
            overall_bias = "neutral"

        active_biases = [b for b in biases.values() if b != "neutral"]
        has_conflict = len(set(active_biases)) > 1

        if len(sig_tfs) >= 3 and not has_conflict:
            confidence = "high"
        elif len(sig_tfs) >= 2 and not has_conflict:
            confidence = "medium"
        elif len(sig_tfs) >= 1:
            confidence = "low"
        else:
            confidence = "none"

        return MultiTimeframeScreeningResult(
            symbol=symbol,
            overall_bias=overall_bias,
            confidence=confidence,
            consensus_bullish_pct=float(consensus_bull),
            consensus_bearish_pct=float(consensus_bear),
            has_timeframe_conflict=has_conflict,
            significant_timeframes=sig_tfs,
            per_timeframe=per_tf,
            screening_timestamp=datetime.now(timezone.utc),
        )

    async def _verify_contexts_with_llm(
        self,
        symbol: str,
        result: MultiTimeframeScreeningResult,
        llm_client: Optional[Any],
    ) -> None:
        """Invokes LLM context verifier on top matches."""
        if not llm_client:
            try:
                from analysis.providers.llm_factory import get_client_for_task
                llm_client = get_client_for_task("pattern_context_verifier", self.settings)
            except Exception:
                return

        curr_ctx = self.context_scorer._current_context
        if not curr_ctx:
            return

        web_search_enabled = self.settings.get("pattern_similarity", {}).get("web_search_fallback", True)
        verdicts = await self.context_verifier.verify_top_matches(
            symbol=symbol,
            result=result,
            current_context=curr_ctx,
            session=self.session,
            llm_client=llm_client,
            web_search_enabled=web_search_enabled,
            limit=3,
        )
        result.context_verdicts = verdicts

    async def _fetch_recent_bars(
        self, symbol: str, timeframe: str, count: int
    ) -> Optional[np.ndarray]:
        """Fetches recent closed bars from DB or MT5."""
        from database.models import PriceOHLCV

        stmt = (
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
            .order_by(desc(PriceOHLCV.timestamp))
            .limit(count)
        )
        res = await self.session.execute(stmt)
        rows = list(reversed(res.scalars().all()))

        if len(rows) < count:
            return None

        # Build numpy array [timestamp, O, H, L, C, V]
        data = []
        for r in rows:
            ts = r.timestamp.timestamp() if r.timestamp else 0.0
            data.append([ts, r.open, r.high, r.low, r.close, r.volume])

        return np.array(data, dtype=float)

    async def _fetch_historical_bars(
        self, symbol: str, timeframe: str, lookback_years: float
    ) -> Optional[np.ndarray]:
        """Fetches historical price bars up to lookback_years."""
        from database.models import PriceOHLCV

        since = datetime.now(timezone.utc) - timedelta(days=int(lookback_years * 365))
        stmt = (
            select(PriceOHLCV)
            .where(
                PriceOHLCV.symbol == symbol,
                PriceOHLCV.timeframe == timeframe,
                PriceOHLCV.timestamp >= since,
            )
            .order_by(PriceOHLCV.timestamp.asc())
        )
        res = await self.session.execute(stmt)
        rows = res.scalars().all()

        if len(rows) < 40:
            return None

        data = []
        for r in rows:
            ts = r.timestamp.timestamp() if r.timestamp else 0.0
            data.append([ts, r.open, r.high, r.low, r.close, r.volume])

        return np.array(data, dtype=float)
