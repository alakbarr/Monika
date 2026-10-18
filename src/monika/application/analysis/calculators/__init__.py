"""
Monika Enterprise Statistical & Econometric Calculators Package.

Exposes quantitative engines for volatility forecasting (GARCH), regime classification
(HMM), tail-risk modeling (EVT, Copula), time-series forecasting (TimesFM),
and confluence verification.
"""

from monika.application.analysis.calculators.confluence_calculator import (
    calculate_confluence,
    calculate_priced_in_subscores,
)
from monika.application.analysis.calculators.copula_tail_risk import (
    clayton_copula_cdf,
    evaluate_joint_tail_risk,
    fit_clayton_copula,
    fit_copula_from_tau,
    gumbel_copula_cdf,
)
from monika.application.analysis.calculators.evt_tail_calculator import (
    TailRiskProfile,
    fit_evt_peaks_over_threshold,
    fit_gpd_tail,
)
from monika.application.analysis.calculators.garch_volatility import (
    GarchForecastResult,
    GarchVolatilityEngine,
)
from monika.application.analysis.calculators.hmm_regime import (
    HMMRegimeClassifier,
)
from monika.application.analysis.calculators.quantlib_core import (
    DeflatedSharpeResult,
    PBOResult,
    QuantLibCore,
    combinatorial_purged_splits,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)
from monika.application.analysis.calculators.timesfm_alpha import (
    TimesFMAlphaCalculator,
)
from monika.application.analysis.calculators.timesfm_residual_validator import (
    ResidualValidationResult,
    TimesFMResidualValidator,
)

__all__ = [
    "calculate_confluence",
    "calculate_priced_in_subscores",
    "GarchVolatilityEngine",
    "GarchForecastResult",
    "HMMRegimeClassifier",
    "TailRiskProfile",
    "fit_evt_peaks_over_threshold",
    "fit_gpd_tail",
    "fit_clayton_copula",
    "fit_copula_from_tau",
    "evaluate_joint_tail_risk",
    "clayton_copula_cdf",
    "gumbel_copula_cdf",
    "TimesFMAlphaCalculator",
    "TimesFMResidualValidator",
    "ResidualValidationResult",
    "QuantLibCore",
    "deflated_sharpe_ratio",
    "probability_of_backtest_overfitting",
    "combinatorial_purged_splits",
    "DeflatedSharpeResult",
    "PBOResult",
]
