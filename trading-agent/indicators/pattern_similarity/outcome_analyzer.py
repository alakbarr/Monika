# ==============================================================================
# File: indicators/pattern_similarity/outcome_analyzer.py
# ==============================================================================

"""
Forward price trajectory and outcome analyzer for historical pattern matches.
Computes forward returns, MFE, MAE, directional bias, and binomial significance.
Pure Python and NumPy implementation. Zero external statistical package dependencies.
"""

import math
from typing import List, Dict, Optional
import numpy as np

from .models import PatternMatch, PatternOutcome, OutcomeStatistics


class OutcomeAnalyzer:
    """Evaluates what occurred after each matched historical chart pattern."""

    # Forward horizon mapping in bars per timeframe
    FORWARD_HORIZONS = {
        "D1": {"1d": 1, "2d": 2, "5d": 5, "10d": 10},
        "H4": {"4h": 1, "8h": 2, "1d": 6, "2d": 12, "5d": 30},
        "H1": {"1h": 1, "4h": 4, "8h": 8, "1d": 24, "2d": 48},
    }

    def analyze_outcomes(
        self,
        matches: List[PatternMatch],
        historical_bars: np.ndarray,
        timeframe: str,
        atr_period: int = 14,
    ) -> List[PatternOutcome]:
        """
        Calculates forward outcomes for all matches.
        historical_bars: shape (N, 6) with columns [timestamp, O, H, L, C, V]
        """
        horizons = self.FORWARD_HORIZONS.get(timeframe, self.FORWARD_HORIZONS["H4"])
        max_horizon_bars = max(horizons.values())
        n_bars = len(historical_bars)
        outcomes: List[PatternOutcome] = []

        for match in matches:
            end_idx = match.end_index

            # Skip match if there are insufficient forward bars to evaluate outcome
            if end_idx + max_horizon_bars >= n_bars:
                continue

            entry_price = float(historical_bars[end_idx, 1])  # Open of bar after pattern
            if entry_price <= 1e-8:
                continue

            # Compute local ATR for normalization
            atr_slice = historical_bars[max(0, end_idx - atr_period):end_idx]
            atr = self._compute_atr(atr_slice)
            if atr <= 1e-8:
                continue

            # Forward returns at each designated horizon
            forward_returns: Dict[str, float] = {}
            for h_label, h_bars in horizons.items():
                target_idx = end_idx + h_bars
                if target_idx < n_bars:
                    future_close = float(historical_bars[target_idx, 4])
                    ret_atr = (future_close - entry_price) / atr
                    forward_returns[h_label] = float(ret_atr)

            # Max Favorable Excursion (MFE) & Max Adverse Excursion (MAE)
            forward_slice = historical_bars[end_idx:end_idx + max_horizon_bars]
            highs = forward_slice[:, 2].astype(float)
            lows = forward_slice[:, 3].astype(float)

            mfe = float((np.max(highs) - entry_price) / atr)
            mae = float((np.min(lows) - entry_price) / atr)

            # Directional classification based on primary 1-day (or equivalent) forward move
            ret_1d = forward_returns.get("1d", forward_returns.get("5d", 0.0))
            if ret_1d >= 0.25:
                direction = "bullish"
            elif ret_1d <= -0.25:
                direction = "bearish"
            else:
                direction = "neutral"

            outcomes.append(PatternOutcome(
                match=match,
                forward_returns=forward_returns,
                mfe_atr=mfe,
                mae_atr=mae,
                direction=direction,
                entry_price=entry_price,
                atr_at_entry=atr,
            ))

        return outcomes

    def compute_context_weighted_statistics(
        self,
        outcomes: List[PatternOutcome],
        min_matches: int = 5,
        significance_threshold: float = 0.10,
    ) -> OutcomeStatistics:
        """
        Aggregates outcomes into statistics using composite weights.
        Composite weight = similarity * context_score * coverage_penalty * cross_symbol_weight.
        """
        n = len(outcomes)
        if n < min_matches:
            return OutcomeStatistics(
                is_significant=False,
                match_count=n,
                reason="insufficient_matches",
            )

        weights = []
        directions_arr = []
        returns_1d = []
        mfes = []
        maes = []

        for o in outcomes:
            m = o.match
            cov_penalty = 1.0 if m.context_coverage >= 0.50 else 0.50
            w = max(0.01, m.similarity * m.context_score * cov_penalty * m.weight)
            weights.append(w)

            dir_code = 1 if o.direction == "bullish" else (-1 if o.direction == "bearish" else 0)
            directions_arr.append(dir_code)
            returns_1d.append(o.forward_returns.get("1d", 0.0))
            mfes.append(o.mfe_atr)
            maes.append(abs(o.mae_atr))

        weights = np.array(weights, dtype=float)
        weights /= (np.sum(weights) + 1e-10)

        directions_arr = np.array(directions_arr)
        returns_1d = np.array(returns_1d, dtype=float)
        mfes = np.array(mfes, dtype=float)
        maes = np.array(maes, dtype=float)

        weighted_bull = float(np.sum(weights[directions_arr > 0]))
        weighted_bear = float(np.sum(weights[directions_arr < 0]))
        weighted_neutral = float(np.sum(weights[directions_arr == 0]))

        weighted_avg_ret = float(np.sum(weights * returns_1d))
        weighted_mfe = float(np.sum(weights * mfes))
        weighted_mae = float(np.sum(weights * maes))

        # Pure Python Binomial Test on raw non-neutral directional counts
        bull_raw = int(np.sum(directions_arr > 0))
        bear_raw = int(np.sum(directions_arr < 0))
        dominant_count = max(bull_raw, bear_raw)
        total_directional = bull_raw + bear_raw

        if total_directional >= 4:
            p_val = self._binomial_test(dominant_count, total_directional, p=0.5)
        else:
            p_val = 1.0

        is_sig = (p_val <= significance_threshold) and (max(weighted_bull, weighted_bear) >= 0.60)

        if weighted_bull >= 0.60 and is_sig:
            bias = "bullish"
        elif weighted_bear >= 0.60 and is_sig:
            bias = "bearish"
        else:
            bias = "neutral"

        # R-Multiple win rates
        win_1r = float(np.mean(mfes >= 1.0))
        win_2r = float(np.mean(mfes >= 2.0))
        win_3r = float(np.mean(mfes >= 3.0))

        implied_rr = float(weighted_mfe / (weighted_mae + 1e-6))

        return OutcomeStatistics(
            is_significant=is_sig,
            match_count=n,
            bullish_pct=weighted_bull,
            bearish_pct=weighted_bear,
            neutral_pct=weighted_neutral,
            avg_return_1d_atr=weighted_avg_ret,
            std_return_1d_atr=float(np.std(returns_1d)),
            median_return_1d_atr=float(np.median(returns_1d)),
            avg_mfe_atr=weighted_mfe,
            avg_mae_atr=weighted_mae,
            implied_rr=implied_rr,
            win_rate_1r=win_1r,
            win_rate_2r=win_2r,
            win_rate_3r=win_3r,
            p_value=float(p_val),
            directional_bias=bias,
        )

    @staticmethod
    def _compute_atr(bars: np.ndarray) -> float:
        """Computes true range average over a slice of bars."""
        if len(bars) < 2:
            return 1.0
        highs = bars[:, 2].astype(float)
        lows = bars[:, 3].astype(float)
        closes = bars[:, 4].astype(float)

        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
        )
        return float(np.mean(tr)) if len(tr) > 0 else 1.0

    @staticmethod
    def _binomial_test(k: int, n: int, p: float = 0.5) -> float:
        """
        Pure Python one-sided Binomial Test: P(X >= k) under H0: p=0.5.
        Exact combinatoric computation for n <= 30; normal approximation for n > 30.
        """
        if k > n or n == 0:
            return 1.0
        if k <= 0:
            return 1.0

        if n <= 30:
            # Exact sum of binomial probabilities
            p_val = sum(
                math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
                for i in range(k, n + 1)
            )
            return float(min(1.0, max(0.0, p_val)))
        else:
            # Normal approximation with continuity correction
            mu = n * p
            sigma = math.sqrt(n * p * (1.0 - p))
            if sigma < 1e-8:
                return 1.0
            z = (k - 0.5 - mu) / sigma
            # Complementary error function approximation for standard normal tail: 0.5 * erfc(z / sqrt(2))
            return float(0.5 * math.erfc(z / math.sqrt(2.0)))
