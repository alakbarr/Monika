# ==============================================================================
# File: indicators/alpha_zoo/meta.py
# Monika Quantitative Factor Metadata Schema
# ==============================================================================

"""
Alpha Factor Metadata & Schema Definitions.

Provides immutable, strictly validated schema definitions for quantitative
alpha factors in Monika's Alpha Zoo.
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


AlphaCategory = Literal[
    "momentum",
    "mean_reversion",
    "volatility",
    "volume",
    "liquidity",
    "trend",
    "structural",
]

AlphaDirection = Literal[
    "positive_bullish",
    "positive_bearish",
    "neutral_volatility",
]


class AlphaMeta(BaseModel):
    """
    Immutable metadata descriptor for an institutional alpha factor.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., description="Unique alphanumeric identifier of factor (e.g. qlib_wvma10)")
    category: AlphaCategory = Field(..., description="Economic hypothesis category")
    lookback: int = Field(gt=0, description="Primary parameter window size in bars")
    columns_required: List[str] = Field(default_factory=lambda: ["close"], description="Required input series (open, high, low, close, volume)")
    min_warmup_bars: int = Field(gt=0, description="Minimum bars needed before output becomes statistically valid")
    decay_horizon: int = Field(default=5, gt=0, description="Expected signal decay horizon in bars")
    direction: AlphaDirection = Field(default="positive_bullish", description="Directionality of positive factor values")
    formula_latex: str = Field(default="", description="LaTeX formulation of the quantitative mathematical model")
    description: str = Field(default="", description="Human-readable description of factor mechanism")

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "lookback": self.lookback,
            str(self.lookback): self.lookback,
            "window": self.lookback,
            "decay_horizon": self.decay_horizon,
        }

