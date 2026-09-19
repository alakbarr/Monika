# ==============================================================================
# File: evals/oracles/__init__.py
# Description: Programmatic mechanical zero-LLM ground-truth oracles.
# ==============================================================================

from .smc_geometry_oracle import evaluate_smc_geometry
from .risk_compliance_oracle import evaluate_risk_compliance
from .trade_discipline_oracle import evaluate_trade_discipline

__all__ = [
    "evaluate_smc_geometry",
    "evaluate_risk_compliance",
    "evaluate_trade_discipline",
]
