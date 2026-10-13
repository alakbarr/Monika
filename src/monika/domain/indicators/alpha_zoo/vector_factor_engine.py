# ==============================================================================
# File: indicators/alpha_zoo/vector_factor_engine.py
# Monika Enterprise Vectorized Alpha Factor Engine
# ==============================================================================

"""
Vectorized Alpha Factor Engine.

High-performance in-memory batch execution engine that evaluates institutional
alpha factors from the alpha catalog (data/alpha_catalog/factors.json) on asset OHLCV
data, producing regime-aware z-score signals and composite alpha scores.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from monika.domain.indicators.alpha_zoo.meta import AlphaCategory
from monika.domain.indicators.alpha_zoo.registry import FactorRegistry

logger = logging.getLogger("TradingAgent.Indicators.VectorFactorEngine")


@dataclass
class FactorSignal:
    """Individual alpha factor evaluation result."""

    factor_id: str
    name: str
    category: str
    raw_value: float
    z_score: float
    signal: float  # Normalized to [-1.0, 1.0]
    direction: str  # "positive_bullish", "positive_bearish", "neutral_volatility"
    formula_latex: str = ""
    description: str = ""


@dataclass
class VectorFactorResult:
    """Aggregated multi-factor consensus output for an asset bar."""

    symbol: str
    regime: str
    composite_alpha_score: float  # Weighted consensus in [-1.0, 1.0]
    factor_count: int
    top_factors: List[FactorSignal] = field(default_factory=list)
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_prompt_context(self) -> str:
        """Format quantitative alpha findings into a clean prompt injection block."""
        if not self.top_factors:
            return f"Quantitative Alpha Consensus for {self.symbol}: Insufficient data for factor evaluation."

        sentiment = (
            "BULLISH"
            if self.composite_alpha_score > 0.15
            else ("BEARISH" if self.composite_alpha_score < -0.15 else "NEUTRAL")
        )
        lines = [
            f"--- [QUANTITATIVE ALPHA FACTOR ENGINE: {self.symbol}] ---",
            f"Market Regime: {self.regime.upper()} | Composite Alpha Score: {self.composite_alpha_score:+.3f} ({sentiment})",
            "Top Evaluated Institutional Factors:",
        ]
        for f in self.top_factors:
            sig_str = f"{f.signal:+.2f}"
            lines.append(f"  * {f.name} ({f.category}): z-score={f.z_score:+.2f}, signal={sig_str} | {f.description}")
        lines.append("-------------------------------------------------------------")
        return "\n".join(lines)


class VectorFactorEngine:
    """
    In-memory batch execution engine for quantitative alpha factors.
    """

    # Regime to category mapping
    REGIME_CATEGORY_MAP: Dict[str, List[AlphaCategory]] = {
        "trending": ["momentum", "trend", "structural"],
        "trend": ["momentum", "trend", "structural"],
        "ranging": ["mean_reversion", "liquidity"],
        "mean_reversion": ["mean_reversion", "liquidity"],
        "volatile": ["volatility", "volume", "microstructure"],
        "volatility": ["volatility", "volume", "microstructure"],
        "breakout": ["momentum", "volatility", "structural"],
    }

    _instance: Optional[VectorFactorEngine] = None

    def __init__(self, catalog_path: Optional[Path | str] = None) -> None:
        if catalog_path is None:
            from monika.core.paths import DATA_DIR

            self.catalog_path = DATA_DIR / "alpha_catalog" / "factors.json"
        else:
            self.catalog_path = Path(catalog_path)

        self._catalog: Dict[str, Any] = {}
        self._load_catalog()

    @classmethod
    def get_instance(cls) -> VectorFactorEngine:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def _load_catalog(self) -> None:
        """Load factor metadata catalog from JSON file."""
        if self.catalog_path.exists():
            try:
                data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
                self._catalog = data.get("factors", {})
                logger.info(f"Loaded {len(self._catalog)} alpha factors from {self.catalog_path}")
            except Exception as e:
                logger.warning(f"Failed to read alpha factor catalog from {self.catalog_path}: {e}")
                self._catalog = {}
        else:
            logger.info("Alpha factor catalog file not found; falling back to registered in-memory factors.")
            self._catalog = {}

    def get_available_factors(self, category: Optional[str] = None) -> List[str]:
        """Return factor IDs filtered by category."""
        if self._catalog:
            factors = []
            for fid, meta in self._catalog.items():
                if category is None or meta.get("category") == category:
                    factors.append(fid)
            return sorted(factors)
        return [m.name for m in FactorRegistry.list_factors(category=category)]

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        regime: str = "trending",
        top_k: int = 5,
        lookback_window: int = 30,
    ) -> VectorFactorResult:
        """
        Evaluate relevant alpha factors on the provided OHLCV DataFrame.

        Args:
            df: OHLCV DataFrame with lowercase column names (open, high, low, close, volume).
            symbol: Financial asset symbol (e.g. EURUSD, XAUUSD).
            regime: Current market regime ("trending", "ranging", "volatile", "breakout").
            top_k: Number of highest-conviction factors to return.
            lookback_window: Rolling window length for z-score normalization.

        Returns:
            VectorFactorResult with ranked factor signals and composite score.
        """
        if df.empty or len(df) < 10:
            return VectorFactorResult(
                symbol=symbol,
                regime=regime,
                composite_alpha_score=0.0,
                factor_count=0,
                top_factors=[],
            )

        # Standardize column names
        df_eval = df.copy()
        df_eval.columns = [c.lower() for c in df_eval.columns]

        # Determine target categories based on market regime
        target_cats = self.REGIME_CATEGORY_MAP.get(regime.lower(), ["momentum", "volatility", "mean_reversion"])

        # Collect candidate factor names registered in FactorRegistry
        registered_metas = FactorRegistry.list_factors()
        candidate_metas = [m for m in registered_metas if m.category in target_cats]

        # If not enough in target categories, expand to all registered
        if len(candidate_metas) < top_k:
            candidate_metas = registered_metas

        factor_signals: List[FactorSignal] = []

        for meta in candidate_metas:
            # Check required columns
            if not all(col in df_eval.columns for col in meta.columns_required):
                continue

            try:
                series = FactorRegistry.compute(meta.name, df_eval, strict_masking=False)
                clean_series = series.dropna()
                if len(clean_series) < 3:
                    continue

                # Compute rolling z-score of the latest value
                latest_val = float(np.asarray(clean_series.iloc[-1]).item())
                recent_window = clean_series.tail(lookback_window)
                mean_val = float(np.asarray(recent_window.mean()).item())
                std_val = float(np.asarray(recent_window.std()).item())

                if std_val > 1e-8:
                    z_score = float(np.clip((latest_val - mean_val) / std_val, -3.0, 3.0))
                else:
                    z_score = 0.0

                # Direction adjustment
                if meta.direction == "positive_bearish":
                    signal = float(-np.tanh(z_score / 1.5))
                elif meta.direction == "neutral_volatility":
                    signal = float(np.abs(np.tanh(z_score / 1.5)))
                else:
                    signal = float(np.tanh(z_score / 1.5))

                factor_signals.append(
                    FactorSignal(
                        factor_id=meta.name,
                        name=meta.name,
                        category=meta.category,
                        raw_value=latest_val,
                        z_score=z_score,
                        signal=signal,
                        direction=meta.direction,
                        formula_latex=meta.formula_latex,
                        description=meta.description,
                    )
                )
            except Exception:
                continue

        # Sort factors by absolute conviction |signal|
        factor_signals.sort(key=lambda s: abs(s.signal), reverse=True)
        top_factors = factor_signals[:top_k]

        # Composite score: mean signal across top factors
        if top_factors:
            composite_score = float(np.clip(np.mean([f.signal for f in top_factors]), -1.0, 1.0))
        else:
            composite_score = 0.0

        return VectorFactorResult(
            symbol=symbol,
            regime=regime,
            composite_alpha_score=composite_score,
            factor_count=len(top_factors),
            top_factors=top_factors,
        )


def get_vector_factor_engine() -> VectorFactorEngine:
    """Return process singleton VectorFactorEngine."""
    return VectorFactorEngine.get_instance()
