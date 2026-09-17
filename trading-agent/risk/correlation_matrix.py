"""
Dynamic Correlation Matrix and Portfolio Covariance Engine (Phase 8 - M7).
Calculates rolling returns correlation and covariance matrices to evaluate portfolio heat.
"""

from datetime import datetime, timezone
import logging
import math
from typing import Dict, List, Optional, Tuple, Any

from risk.portfolio_correlation_gate import (
    compute_portfolio_correlation_matrix,
    filter_correlated_proposals,
    _get_usd_directional_delta,
)

logger = logging.getLogger("TradingAgent.Risk.CorrelationMatrix")


class DynamicCorrelationMatrix:
    """Calculates rolling cross-asset return correlations and portfolio risk concentration."""

    def __init__(self, rolling_days: int = 30, correlation_threshold: float = 0.65):
        self.rolling_days = rolling_days
        self.correlation_threshold = correlation_threshold

    @staticmethod
    def calculate_pearson_correlation(series_a: List[float], series_b: List[float]) -> float:
        """Calculate Pearson correlation coefficient between two equal-length return series."""
        if not series_a or not series_b or len(series_a) != len(series_b) or len(series_a) < 2:
            return 0.0

        n = len(series_a)
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        diff_a = [x - mean_a for x in series_a]
        diff_b = [y - mean_b for y in series_b]

        cov = sum(da * db for da, db in zip(diff_a, diff_b))
        var_a = sum(da * da for da in diff_a)
        var_b = sum(db * db for db in diff_b)

        denom = math.sqrt(var_a * var_b)
        if denom == 0.0:
            return 0.0

        corr = cov / denom
        return max(-1.0, min(1.0, round(corr, 4)))

    async def get_matrix(
        self,
        session: Any,
        symbols: List[str],
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Compute full N x N correlation matrix for the given active instruments."""
        if not symbols:
            return {}
        return await compute_portfolio_correlation_matrix(session, symbols, as_of=as_of)

    def calculate_portfolio_heat(
        self,
        positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """Compute aggregate correlated exposure and concentration score for open positions."""
        if not positions:
            return {"portfolio_heat": 0.0, "correlated_pairs": [], "status": "safe"}

        correlated_pairs = []
        total_heat_score = 0.0

        for i, pos1 in enumerate(positions):
            sym1 = pos1.get("symbol", "").upper()
            dir1 = pos1.get("direction", "BUY").upper()
            vol1 = float(pos1.get("volume", 0.01))

            for pos2 in positions[i + 1:]:
                sym2 = pos2.get("symbol", "").upper()
                dir2 = pos2.get("direction", "BUY").upper()
                vol2 = float(pos2.get("volume", 0.01))

                corr = correlation_matrix.get(sym1, {}).get(sym2, 0.0)
                same_dir = (dir1 == dir2)

                # High positive correlation in same direction or high negative in opposite direction
                effective_corr = corr if same_dir else -corr

                if abs(effective_corr) >= self.correlation_threshold:
                    weight = math.sqrt(vol1 * vol2) * abs(effective_corr)
                    total_heat_score += weight
                    correlated_pairs.append({
                        "pair": f"{sym1}/{sym2}",
                        "correlation": corr,
                        "effective_risk": effective_corr,
                        "weight": round(weight, 4),
                    })

        return {
            "portfolio_heat": round(total_heat_score, 4),
            "correlated_pairs": correlated_pairs,
            "status": "elevated" if total_heat_score > 2.0 else "normal",
        }
