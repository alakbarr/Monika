# ==============================================================================
# File: indicators/pattern_similarity/scanner.py
# ==============================================================================

"""
High-performance vectorized pattern similarity scanning using pure NumPy.
Implements Z-normalized Euclidean sliding window distance and constrained DTW.
Zero external library dependencies.
"""

from typing import List
import numpy as np

from .models import PatternMatch
from .normalizer import PriceNormalizer


class SimilarityScanner:
    """Vectorized pattern similarity scanning engine."""

    def find_similar_patterns(
        self,
        current_bars: np.ndarray,     # shape (W, 6): [timestamp, O, H, L, C, V]
        historical_bars: np.ndarray,  # shape (N, 6): [timestamp, O, H, L, C, V]
        window_size: int,
        top_k: int = 20,
        min_similarity: float = 0.75,
        method: str = "euclidean",    # "euclidean", "dtw", "hybrid"
    ) -> List[PatternMatch]:
        """
        Scans entire historical array for segments matching current_bars.
        Returns top-K non-overlapping matches meeting min_similarity.
        """
        n_hist = len(historical_bars)
        if n_hist < window_size * 2 or len(current_bars) < window_size:
            return []

        close_hist = historical_bars[:, 4].astype(float)
        close_curr = current_bars[-window_size:, 4].astype(float)

        curr_z = PriceNormalizer.z_normalize(close_curr)
        curr_std = float(np.std(close_curr))

        # Vectorized sliding window view (zero-copy strided array)
        windows = np.lib.stride_tricks.sliding_window_view(close_hist, window_size)
        n_windows = len(windows)

        # Batch Z-normalization across all sliding windows
        means = windows.mean(axis=1, keepdims=True)
        stds = windows.std(axis=1, keepdims=True)
        stds_safe = np.where(stds < 1e-8, 1.0, stds)
        windows_z = (windows - means) / stds_safe

        # Vectorized Euclidean distance calculation (broadcasts curr_z)
        diff = windows_z - curr_z[np.newaxis, :]
        distances = np.sqrt(np.sum(diff ** 2, axis=1)) / np.sqrt(window_size)

        # Transform distance to similarity score in range (0.0, 1.0]
        similarities = 1.0 / (1.0 + distances)

        # -------------------------------------------------------------
        # Filters:
        # 1. Exclusion Zone: Exclude the last 2x window_size bars (prevent self-match)
        # -------------------------------------------------------------
        exclusion_zone = min(window_size * 2, n_windows)
        similarities[-exclusion_zone:] = 0.0

        # 2. Flat Window Filter: Ignore windows with negligible volatility
        flat_threshold = curr_std * 0.30 if curr_std > 1e-6 else 1e-4
        flat_mask = stds.squeeze() < flat_threshold
        similarities[flat_mask] = 0.0

        # 3. Minimum Similarity Threshold Filter
        similarities[similarities < min_similarity] = 0.0

        # Extract top-K non-overlapping matches greedily
        matches = self._extract_non_overlapping_topk(
            similarities=similarities,
            window_size=window_size,
            top_k=top_k,
            historical_bars=historical_bars,
        )

        # Optional DTW refinement for top matches if hybrid method requested
        if method == "hybrid" and matches:
            for m in matches:
                cand_close = close_hist[m.start_index:m.end_index]
                cand_z = PriceNormalizer.z_normalize(cand_close)
                dtw_dist = self.compute_dtw_distance(curr_z, cand_z, sakoe_chiba_radius=4)
                dtw_sim = float(1.0 / (1.0 + dtw_dist))
                # Blended similarity: 70% Euclidean + 30% DTW
                m.similarity = float(0.70 * m.similarity + 0.30 * dtw_sim)

            matches.sort(key=lambda x: x.similarity, reverse=True)

        return matches

    def _extract_non_overlapping_topk(
        self,
        similarities: np.ndarray,
        window_size: int,
        top_k: int,
        historical_bars: np.ndarray,
    ) -> List[PatternMatch]:
        """Greedily extracts the best non-overlapping pattern matches."""
        sims = similarities.copy()
        matches: List[PatternMatch] = []

        while len(matches) < top_k:
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim < 0.01:
                break

            match = PatternMatch(
                start_index=best_idx,
                end_index=best_idx + window_size,
                similarity=best_sim,
                start_time=float(historical_bars[best_idx, 0]),
                end_time=float(historical_bars[best_idx + window_size - 1, 0]),
            )
            matches.append(match)

            # Zero out the overlapping interval in the similarity array
            left = max(0, best_idx - window_size + 1)
            right = min(len(sims), best_idx + window_size)
            sims[left:right] = 0.0

        return matches

    def compute_dtw_distance(
        self,
        series_a: np.ndarray,
        series_b: np.ndarray,
        sakoe_chiba_radius: int = 5,
    ) -> float:
        """
        Computes Dynamic Time Warping (DTW) distance with Sakoe-Chiba constraint band.
        Pure NumPy implementation with O(N * 2R) time complexity.
        """
        n = len(series_a)
        m = len(series_b)
        r = sakoe_chiba_radius

        dtw = np.full((n + 1, m + 1), np.inf, dtype=float)
        dtw[0, 0] = 0.0

        for i in range(1, n + 1):
            j_lo = max(1, i - r)
            j_hi = min(m, i + r) + 1
            for j in range(j_lo, j_hi):
                cost = (series_a[i - 1] - series_b[j - 1]) ** 2
                dtw[i, j] = cost + min(
                    dtw[i - 1, j],      # insertion
                    dtw[i, j - 1],      # deletion
                    dtw[i - 1, j - 1],  # match
                )

        return float(np.sqrt(dtw[n, m]) / np.sqrt(max(1, n)))
