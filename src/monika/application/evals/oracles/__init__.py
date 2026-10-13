# ==============================================================================
# File: evals/oracles/__init__.py
# Description: Programmatic mechanical zero-LLM ground-truth oracles.
# ==============================================================================

from .macro_regime_oracle import evaluate_macro_regime
from .risk_compliance_oracle import evaluate_risk_compliance
from .smc_geometry_oracle import evaluate_smc_geometry
from .trade_discipline_oracle import evaluate_trade_discipline

__all__ = [
    "evaluate_smc_geometry",
    "evaluate_risk_compliance",
    "evaluate_trade_discipline",
    "evaluate_macro_regime",
]
