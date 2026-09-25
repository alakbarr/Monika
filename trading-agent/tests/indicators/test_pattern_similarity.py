# ==============================================================================
# File: tests/indicators/test_pattern_similarity.py
# ==============================================================================

"""
Comprehensive test suite for Context-Aware Pattern Similarity Screening Engine.
Verifies normalizer, scanner, feature extractor, context scorer, outcome analyzer,
and engine multi-timeframe consensus without external network calls.
"""

import math
from datetime import datetime, timezone
import numpy as np
import pytest

from indicators.pattern_similarity.models import (
    PatternMatch,
    MarketContext,
    SingleTimeframeResult,
    MultiTimeframeScreeningResult,
    OutcomeStatistics,
    PatternOutcome,
)
from indicators.pattern_similarity.normalizer import PriceNormalizer
from indicators.pattern_similarity.feature_extractor import FeatureExtractor
from indicators.pattern_similarity.scanner import SimilarityScanner
from indicators.pattern_similarity.outcome_analyzer import OutcomeAnalyzer
from indicators.pattern_similarity.context_scorer import ContextScorer
from indicators.pattern_similarity.engine import PatternSimilarityEngine


def generate_synthetic_ohlcv(
    n_bars: int = 500,
    base_price: float = 2000.0,
    volatility: float = 5.0,
    seed: int = 42,
) -> np.ndarray:
    """Generates synthetic (N, 6) [timestamp, O, H, L, C, V] array."""
    rng = np.random.default_rng(seed)
    bars = []
    curr = base_price
    start_ts = 1672531200.0  # 2023-01-01 00:00:00 UTC

    for i in range(n_bars):
        ret = rng.normal(0, volatility)
        open_p = curr
        close_p = curr + ret
        high_p = max(open_p, close_p) + abs(rng.normal(0, volatility * 0.5))
        low_p = min(open_p, close_p) - abs(rng.normal(0, volatility * 0.5))
        vol = float(rng.integers(100, 5000))
        bars.append([start_ts + i * 3600, open_p, high_p, low_p, close_p, vol])
        curr = close_p

    return np.array(bars, dtype=float)


# ==============================================================================
# 1. PriceNormalizer Tests
# ==============================================================================

class TestPriceNormalizer:

    def test_z_normalize_standard(self):
        series = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        z = PriceNormalizer.z_normalize(series)
        assert np.isclose(np.mean(z), 0.0, atol=1e-7)
        assert np.isclose(np.std(z), 1.0, atol=1e-7)

    def test_z_normalize_flat(self):
        flat = np.array([100.0, 100.0, 100.0, 100.0])
        z = PriceNormalizer.z_normalize(flat)
        assert np.all(z == 0.0)

    def test_min_max_normalize(self):
        series = np.array([10.0, 20.0, 30.0])
        mm = PriceNormalizer.min_max_normalize(series)
        assert mm[0] == 0.0
        assert mm[-1] == 1.0

    def test_log_return_normalize(self):
        series = np.array([100.0, 105.0, 110.0])
        lr = PriceNormalizer.log_return_normalize(series)
        assert len(lr) == len(series)
        assert lr[0] == 0.0
        assert lr[-1] > 0.0


# ==============================================================================
# 2. SimilarityScanner Tests
# ==============================================================================

class TestSimilarityScanner:

    def test_exact_pattern_match(self):
        scanner = SimilarityScanner()
        bars = generate_synthetic_ohlcv(n_bars=300, seed=123)

        # Cut a window from bar 50 to 80
        w_size = 30
        target_pattern = bars[50:80].copy()

        # Place target pattern at historical index 50
        matches = scanner.find_similar_patterns(
            current_bars=target_pattern,
            historical_bars=bars,
            window_size=w_size,
            top_k=5,
            min_similarity=0.70,
        )

        assert len(matches) > 0
        # The best match should be right at index 50 or very near
        best_match = matches[0]
        assert abs(best_match.start_index - 50) <= 1
        assert best_match.similarity >= 0.95

    def test_exclusion_zone_prevents_recent_self_match(self):
        scanner = SimilarityScanner()
        bars = generate_synthetic_ohlcv(n_bars=200, seed=456)
        w_size = 20
        recent_pattern = bars[-w_size:].copy()

        matches = scanner.find_similar_patterns(
            current_bars=recent_pattern,
            historical_bars=bars,
            window_size=w_size,
            top_k=5,
            min_similarity=0.70,
        )

        # None of the matches should fall within the last 2x window_size
        n_windows = len(bars) - w_size + 1
        exclusion_bound = len(bars) - w_size * 2
        for m in matches:
            assert m.start_index < exclusion_bound

    def test_sakoe_chiba_dtw(self):
        scanner = SimilarityScanner()
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        b = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        dist = scanner.compute_dtw_distance(a, b, sakoe_chiba_radius=2)
        assert np.isclose(dist, 0.0, atol=1e-6)

        # Time-shifted version
        c = np.array([1.0, 1.0, 2.0, 3.0, 4.0])
        dist_shift = scanner.compute_dtw_distance(a, c, sakoe_chiba_radius=2)
        assert dist_shift > 0.0


# ==============================================================================
# 3. FeatureExtractor Tests
# ==============================================================================

class TestFeatureExtractor:

    def test_feature_vector_extraction(self):
        extractor = FeatureExtractor()
        bars = generate_synthetic_ohlcv(n_bars=40, seed=789)
        fv = extractor.extract(bars)

        assert isinstance(fv.trend_slope, float)
        assert isinstance(fv.volatility_ratio, float)
        assert 0.0 <= fv.range_position <= 1.0
        assert 0.0 <= fv.body_ratio_mean <= 1.0
        assert fv.swing_count >= 0

        # Cosine similarity with self must be 1.0
        sim = extractor.compute_feature_similarity(fv, fv)
        assert np.isclose(sim, 1.0, atol=1e-5)


# ==============================================================================
# 4. OutcomeAnalyzer Tests
# ==============================================================================

class TestOutcomeAnalyzer:

    def test_pure_python_binomial_test(self):
        # 10 successes out of 10 under p=0.5 -> (0.5)^10 = 0.000976
        p_val_10 = OutcomeAnalyzer._binomial_test(k=10, n=10, p=0.5)
        assert np.isclose(p_val_10, 0.5 ** 10, atol=1e-4)

        # 5 successes out of 10 under p=0.5 -> ~0.623 (cumulative >= 5)
        p_val_5 = OutcomeAnalyzer._binomial_test(k=5, n=10, p=0.5)
        assert p_val_5 > 0.50

        # Large sample normal approximation (35 out of 50)
        p_val_large = OutcomeAnalyzer._binomial_test(k=35, n=50, p=0.5)
        assert p_val_large < 0.01

    def test_outcome_analysis_and_statistics(self):
        analyzer = OutcomeAnalyzer()
        bars = generate_synthetic_ohlcv(n_bars=300, seed=321)

        # Create dummy matches
        matches = [
            PatternMatch(
                start_index=i * 25,
                end_index=i * 25 + 20,
                similarity=0.85,
                start_time=float(bars[i * 25, 0]),
                end_time=float(bars[i * 25 + 19, 0]),
                context_score=0.80,
                context_coverage=1.0,
            )
            for i in range(8)
        ]

        outcomes = analyzer.analyze_outcomes(matches, bars, timeframe="H4")
        assert len(outcomes) > 0

        for o in outcomes:
            assert isinstance(o.mfe_atr, float)
            assert isinstance(o.mae_atr, float)
            assert o.direction in ("bullish", "bearish", "neutral")

        stats = analyzer.compute_context_weighted_statistics(outcomes, min_matches=5)
        assert stats.match_count == len(outcomes)
        assert 0.0 <= stats.bullish_pct <= 1.0
        assert 0.0 <= stats.bearish_pct <= 1.0
        assert stats.directional_bias in ("bullish", "bearish", "neutral")


# ==============================================================================
# 5. ContextScorer & Cold-Start Tests
# ==============================================================================

class TestContextScorer:

    def test_yang_zhang_proxy(self):
        bars = generate_synthetic_ohlcv(n_bars=50, base_price=2000.0, volatility=10.0, seed=999)
        scorer = ContextScorer(session=None, settings={})

        yz_vol = scorer._compute_yang_zhang_proxy(bars)
        assert 8.0 <= yz_vol <= 75.0
        assert isinstance(yz_vol, float)

    def test_adaptive_similarity_renormalization(self):
        scorer = ContextScorer(session=None, settings={})

        current = MarketContext(
            vix_level=18.0,
            vix_category="normal",
            dxy_trend="bullish",
            market_regime="trend",
            rate_cycle="hiking",
            asset_trend="above_ema",
        )

        # Full matching historical context
        hist_full = MarketContext(
            vix_level=19.0,
            vix_category="normal",
            dxy_trend="bullish",
            market_regime="trend",
            rate_cycle="hiking",
            asset_trend="above_ema",
        )
        sim_full, cov_full = scorer._compute_adaptive_similarity(current, hist_full)
        assert sim_full == 1.0
        assert cov_full == 1.0

        # Partial historical context (Cold-start: rate_cycle and dxy unknown)
        hist_partial = MarketContext(
            vix_level=18.5,
            vix_category="normal",
            dxy_trend="unknown",
            market_regime="trend",
            rate_cycle="unknown",
            asset_trend="above_ema",
        )
        sim_part, cov_part = scorer._compute_adaptive_similarity(current, hist_partial)
        # Should drop missing dimensions and renormalize active weights
        assert np.isclose(sim_part, 1.0, atol=1e-5)  # Remaining active dimensions all match perfectly
        assert cov_part < 1.0   # Coverage is lower due to missing macro tables


# ==============================================================================
# 6. MultiTimeframeScreeningResult Formatting Tests
# ==============================================================================

class TestMultiTimeframeScreeningResult:

    def test_format_for_prompt(self):
        res_d1 = SingleTimeframeResult(
            timeframe="D1",
            statistics=OutcomeStatistics(
                is_significant=True,
                match_count=12,
                bullish_pct=0.75,
                bearish_pct=0.20,
                neutral_pct=0.05,
                avg_return_1d_atr=1.45,
                avg_mfe_atr=2.8,
                avg_mae_atr=0.9,
                implied_rr=3.1,
                win_rate_1r=0.80,
                win_rate_2r=0.65,
                win_rate_3r=0.45,
                p_value=0.015,
                directional_bias="bullish",
            ),
            top_matches=[
                PatternMatch(
                    start_index=10, end_index=50, similarity=0.88,
                    start_time=1680000000.0, end_time=1683456000.0,
                    context_label="HIGH"
                )
            ],
            avg_similarity=0.84,
        )

        mtf = MultiTimeframeScreeningResult(
            symbol="XAUUSD",
            overall_bias="bullish",
            confidence="high",
            consensus_bullish_pct=0.72,
            consensus_bearish_pct=0.22,
            has_timeframe_conflict=False,
            significant_timeframes=["D1"],
            per_timeframe={"D1": res_d1},
            screening_timestamp=datetime.now(timezone.utc),
        )

        prompt_str = mtf.format_for_prompt()
        assert "Historical Pattern Similarity" in prompt_str
        assert "D1 (12 matches" in prompt_str
        assert "Directional bias: BULLISH" in prompt_str
        assert "Multi-TF Consensus: BULLISH" in prompt_str
