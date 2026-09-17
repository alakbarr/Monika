"""
Schmitt-Trigger Regime Detector: Stateful hysteresis-based market regime classification.
Eliminates regime classification whipsaw at boundary crossings.
Source: Vibe-Trading backtest/regime.py
"""
from enum import Enum
import logging
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.SchmittRegimeDetector")


class RegimeState(str, Enum):
    DIVERSIFIED = "diversified"       # Normal market: full position sizing & multi-pair diversification
    TRANSITIONING = "transitioning"   # Hysteresis band: maintain previous state, caution
    FUSED = "fused"                   # Systemic crisis/high contagion: reduce heat, widen SL, limit concurrent


class SchmittRegimeDetector:
    """
    Hysteresis-based regime detector preventing classification whipsaw.

    Uses dual-threshold Schmitt trigger on cross-asset correlation edge density:
    - DIVERSIFIED -> FUSED: density crosses UP through enter_fused (default 0.65).
    - FUSED -> DIVERSIFIED: density crosses DOWN through exit_fused (default 0.45).
    - Between 0.45 and 0.65: maintains current state (hysteresis band).
    """

    def __init__(
        self,
        enter_fused: float = 0.65,
        exit_fused: float = 0.45,
        correlation_window: int = 60,
        pair_threshold: float = 0.70,
    ):
        self.enter_fused = enter_fused
        self.exit_fused = exit_fused
        self.corr_window = correlation_window
        self.pair_threshold = pair_threshold
        self._state: RegimeState = RegimeState.DIVERSIFIED
        self._last_density: float = 0.0

    @property
    def state(self) -> RegimeState:
        return self._state

    @property
    def last_density(self) -> float:
        return self._last_density

    def compute_edge_density(self, returns_matrix: pd.DataFrame) -> float:
        """Compute proportion of unique asset pairs exceeding correlation threshold."""
        if returns_matrix is None or len(returns_matrix) < min(10, self.corr_window):
            return 0.0

        n_assets = returns_matrix.shape[1]
        if n_assets < 2:
            return 0.0

        recent = returns_matrix.iloc[-self.corr_window:]
        corr_matrix = recent.corr().fillna(0.0).values

        # Extract upper triangle excluding diagonal
        mask = np.triu(np.ones((n_assets, n_assets), dtype=bool), k=1)
        pair_corrs = np.abs(corr_matrix[mask])

        total_pairs = len(pair_corrs)
        if total_pairs == 0:
            return 0.0

        high_corr_count = int(np.sum(pair_corrs >= self.pair_threshold))
        density = float(high_corr_count / total_pairs)
        self._last_density = density
        return density

    def update(self, returns_matrix: pd.DataFrame) -> RegimeState:
        """Update regime state from returns matrix via Schmitt trigger."""
        density = self.compute_edge_density(returns_matrix)
        prev_state = self._state

        if self._state == RegimeState.DIVERSIFIED and density >= self.enter_fused:
            self._state = RegimeState.FUSED
            logger.warning(
                f"[SchmittRegime] Regime transition: DIVERSIFIED -> FUSED (density={density:.2f} >= {self.enter_fused})"
            )
        elif self._state == RegimeState.FUSED and density <= self.exit_fused:
            self._state = RegimeState.DIVERSIFIED
            logger.info(
                f"[SchmittRegime] Regime transition: FUSED -> DIVERSIFIED (density={density:.2f} <= {self.exit_fused})"
            )

        return self._state


_GLOBAL_SCHMITT_DETECTOR: Optional[SchmittRegimeDetector] = None


def get_schmitt_regime_detector() -> SchmittRegimeDetector:
    global _GLOBAL_SCHMITT_DETECTOR
    if _GLOBAL_SCHMITT_DETECTOR is None:
        _GLOBAL_SCHMITT_DETECTOR = SchmittRegimeDetector()
    return _GLOBAL_SCHMITT_DETECTOR
